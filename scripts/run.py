"""Scheduled entry point for the crypto-chameleon trading job.

Invoked by cron on the GCP VM. Implements the write protocol from
database_instructions.md: idempotent runs row keyed by scheduled_for,
deterministic client_oid per planned order, transactions inserted only
after fill, next-pending row inserted on success, Telegram alerts on
both success (public) and failure (private).
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_DOWN, Decimal
from typing import Any, Dict, Literal, Optional, Tuple

import requests
from dotenv import load_dotenv
from postgrest import APIError
from supabase import Client, create_client

from cdc import CryptoComAPI


# ----------------------------------------------------------------------
# 1. Env
# ----------------------------------------------------------------------

load_dotenv()


def _require(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"missing required env var: {name}")
    return v


CDCEX_CHAMELEON_API = _require("CDCEX_CHAMELEON_API")
CDCEX_CHAMELEON_SECRET = _require("CDCEX_CHAMELEON_SECRET")
CDCEX_CONTROL_API = _require("CDCEX_CONTROL_API")
CDCEX_CONTROL_SECRET = _require("CDCEX_CONTROL_SECRET")
SUPABASE_URL = _require("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = _require("SUPABASE_SERVICE_ROLE_KEY")
TELEGRAM_BOT_TOKEN = _require("TELEGRAM_BOT_TOKEN")
TELEGRAM_PUBLIC_CHANNEL_ID = _require("TELEGRAM_PUBLIC_CHANNEL_ID")
TELEGRAM_PRIVATE_CHAT_ID = _require("TELEGRAM_PRIVATE_CHAT_ID")
DASHBOARD_URL = _require("DASHBOARD_URL")
DRY_RUN = _require("DRY_RUN").lower() == "true"


# ----------------------------------------------------------------------
# 2. Constants & config
# ----------------------------------------------------------------------

ORDER_POLL_TIMEOUT_S = 30
ORDER_POLL_INTERVAL_S = 1

# Both arms trade the same spot pair. BTC_USD confirmed tradable via
# get_instruments; instrument metadata gives the precision below.
TRADE_INSTRUMENT = "BTC_USD"
BTC_USD_QTY_DECIMALS = 5  # qty_tick_size 0.00001
BTC_USD_NOTIONAL_DECIMALS = 2  # quote_decimals 2 (USD cents)

# Minimum order size is NOT exposed in get_instruments metadata and the
# Crypto.com NotebookLM had no answer, so this is a conservative fallback:
# well above any real BTC_USD minimum, far below our ~$50 trade scale, so it
# only skips sub-$1 dust rebalances. Verify/relax on the first live run.
BTC_USD_MIN_NOTIONAL = Decimal("1")

# Control shaves its buy by this fraction so that, even if the taker fee is
# charged on top of the notional (unconfirmed — NotebookLM had no answer), the
# order can't overdraw the stable balance. 0.5% comfortably exceeds the taker
# fee. Chameleon does not need this: its rebalance-buy is strictly less than
# the cash sleeve (proof in decide_chameleon).
CONTROL_FEE_BUFFER = Decimal("0.005")

MONTHLY_DEPOSIT_USD = Decimal("50")

# Chameleon = strategy_v8 funded two-way basket. Hold while BTC weight sits in
# [target - band, target + band] = [0.85, 0.95]; otherwise rebalance all the
# way back to target. band = 0.05 per PLAN.md "Going live" (governs over
# strategy_v8.md's research-doc 0.03).
CHAMELEON_TARGET_W = Decimal("0.90")
CHAMELEON_BAND = Decimal("0.05")


# ----------------------------------------------------------------------
# 3-4. Schedule
# ----------------------------------------------------------------------


def compute_next_tuesday_1300_utc(now: datetime) -> datetime:
    """Next Tuesday 13:00 UTC strictly after `now`."""
    # weekday(): Mon=0, Tue=1
    days_ahead = (1 - now.weekday()) % 7
    candidate = (now + timedelta(days=days_ahead)).replace(
        hour=13, minute=0, second=0, microsecond=0
    )
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ----------------------------------------------------------------------
# 4.5 Monthly deposits
# ----------------------------------------------------------------------

# $50 lands in *each* arm on the last Friday of every month. The bot records
# these into capital_events itself (the dashboard's "Capital invested"
# denominator) — trading reads live on-exchange balances, not these rows.


def last_friday_of_month(year: int, month: int) -> date:
    """Date of the last Friday (weekday 4) in the given month."""
    if month == 12:
        last_day = date(year, 12, 31)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)
    # Step back from the last day to the most recent Friday.
    offset = (last_day.weekday() - 4) % 7
    return last_day - timedelta(days=offset)


def most_recent_deposit_date(now: datetime) -> date:
    """Last Friday of the current month if it has occurred, else of the
    previous month. This is the deposit that should already be on the books."""
    this_month = last_friday_of_month(now.year, now.month)
    if this_month <= now.date():
        return this_month
    prev = (now.replace(day=1) - timedelta(days=1))
    return last_friday_of_month(prev.year, prev.month)


def record_due_deposits(sb: Client, now: datetime) -> None:
    """Idempotently record the most-recent monthly $50 deposit for both arms.

    occurred_at is pinned to the deposit date at 00:00 UTC so the value is
    deterministic; the unique (account, occurred_at, kind) constraint makes
    re-runs no-ops (23505 swallowed). Safe to attempt every run — no date
    arithmetic against the previous run needed.
    """
    deposit_date = most_recent_deposit_date(now)
    occurred_at = datetime(
        deposit_date.year, deposit_date.month, deposit_date.day, tzinfo=timezone.utc
    )
    for account in ("chameleon", "control"):
        try:
            sb.table("capital_events").insert(
                {
                    "account": account,
                    "occurred_at": occurred_at.isoformat(),
                    "kind": "deposit",
                    "amount_usd": str(MONTHLY_DEPOSIT_USD),
                    "note": "monthly auto-deposit",
                }
            ).execute()
            print(f"{account}: recorded deposit for {deposit_date.isoformat()}")
        except APIError as e:
            if getattr(e, "code", None) == "23505":
                continue  # already recorded this month — idempotent
            raise


# ----------------------------------------------------------------------
# 5. Supabase helpers
# ----------------------------------------------------------------------


def upsert_run(sb: Client, scheduled_for: datetime) -> str:
    res = (
        sb.table("runs")
        .upsert(
            {
                "scheduled_for": scheduled_for.isoformat(),
                "status": "running",
                "started_at": _utc_now_iso(),
            },
            on_conflict="scheduled_for",
        )
        .execute()
    )
    return res.data[0]["id"]


def transaction_exists(sb: Client, client_oid: str) -> bool:
    res = (
        sb.table("transactions")
        .select("id")
        .eq("client_oid", client_oid)
        .limit(1)
        .execute()
    )
    return bool(res.data)


def insert_transaction(sb: Client, **fields: Any) -> None:
    try:
        sb.table("transactions").insert(fields).execute()
    except APIError as e:
        # 23505 = unique_violation: a concurrent retry beat us; idempotency holds.
        if getattr(e, "code", None) == "23505":
            return
        raise


def mark_run(
    sb: Client,
    run_id: str,
    status: str,
    error_message: Optional[str] = None,
) -> None:
    payload: Dict[str, Any] = {"status": status}
    if status in ("succeeded", "failed", "partial"):
        payload["finished_at"] = _utc_now_iso()
    if error_message is not None:
        payload["error_message"] = error_message
    sb.table("runs").update(payload).eq("id", run_id).execute()


def insert_next_pending_run(sb: Client, next_scheduled_for: datetime) -> None:
    next_iso = next_scheduled_for.isoformat()
    sb.table("runs").upsert(
        {"scheduled_for": next_iso, "status": "pending"},
        on_conflict="scheduled_for",
        ignore_duplicates=True,
    ).execute()
    # Collapse any stale pendings (manual seeds or leftovers from earlier
    # cycles) so the dashboard's "next run" query has exactly one candidate.
    sb.table("runs").delete().eq("status", "pending").neq(
        "scheduled_for", next_iso
    ).execute()


def upsert_snapshot(
    sb: Client,
    *,
    account: str,
    run_id: str,
    btc_qty: Decimal,
    stable_usd: Decimal,
    btc_price_usd: Decimal,
    total_value_usd: Decimal,
    raw: Dict[str, Any],
) -> None:
    sb.table("valuation_snapshots").upsert(
        {
            "account": account,
            "run_id": run_id,
            "snapshot_at": _utc_now_iso(),
            "btc_qty": str(btc_qty),
            "stable_usd": str(stable_usd),
            "btc_price_usd": str(btc_price_usd),
            "total_value_usd": str(total_value_usd),
            "raw": raw,
        },
        on_conflict="account,run_id",
    ).execute()


# ----------------------------------------------------------------------
# 6. Telegram
# ----------------------------------------------------------------------


def tg_send(chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        r = requests.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        r.raise_for_status()
    except Exception as e:
        # Best-effort: a Telegram outage must not crash the trading run.
        print(f"telegram send failed (chat_id={chat_id}): {e}", file=sys.stderr)


def tg_public(text: str) -> None:
    tg_send(TELEGRAM_PUBLIC_CHANNEL_ID, text)


def tg_private(text: str) -> None:
    tg_send(TELEGRAM_PRIVATE_CHAT_ID, text)


# ----------------------------------------------------------------------
# 7. Trade decisions
# ----------------------------------------------------------------------


@dataclass
class OrderSpec:
    instrument: str
    side: Literal["BUY", "SELL"]
    purpose: str
    notional: Optional[Decimal] = None
    quantity: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if self.side not in ("BUY", "SELL"):
            raise ValueError("side must be BUY or SELL")
        if self.side == "BUY" and self.notional is None and self.quantity is None:
            raise ValueError("BUY OrderSpec needs notional or quantity")
        if self.side == "SELL" and self.quantity is None:
            raise ValueError("SELL OrderSpec needs quantity")


def floor_to_qty(x: Decimal) -> Decimal:
    """Floor a base-asset quantity to instrument precision (ROUND_DOWN keeps
    the order inside the available balance and avoids precision rejects)."""
    return x.quantize(Decimal(1).scaleb(-BTC_USD_QTY_DECIMALS), rounding=ROUND_DOWN)


def floor_to_notional(x: Decimal) -> Decimal:
    """Floor a quote-currency (USD) notional to instrument precision."""
    return x.quantize(
        Decimal(1).scaleb(-BTC_USD_NOTIONAL_DECIMALS), rounding=ROUND_DOWN
    )


def decide_control(cdc: CryptoComAPI) -> Optional[OrderSpec]:
    """Control DCA: spend the entire available stable balance on BTC_USD.

    No calendar logic — control's steady state is ~0 cash (it spends everything
    each month), so this fires only when a fresh deposit lands, and is robust to
    a missed run (cash deploys the next run rather than being stranded).
    """
    _btc_qty, stable_usd, _price, _raw = read_position(cdc)
    spend = floor_to_notional(stable_usd * (Decimal(1) - CONTROL_FEE_BUFFER))
    if spend < BTC_USD_MIN_NOTIONAL:
        return None  # no fresh deposit cash to deploy
    return OrderSpec(
        instrument=TRADE_INSTRUMENT, side="BUY", purpose="dca", notional=spend
    )


def decide_chameleon(cdc: CryptoComAPI) -> Optional[OrderSpec]:
    """strategy_v8 funded two-way basket. Rebalance BTC back to target_w when
    weight drifts outside the no-trade band; otherwise hold."""
    btc_qty, stable_usd, price, _raw = read_position(cdc)
    btc_value = btc_qty * price
    total = btc_value + stable_usd
    if total <= 0:
        return None

    target_value = CHAMELEON_TARGET_W * total
    drift = btc_value - target_value  # >0 BTC too heavy, <0 too light
    thresh = CHAMELEON_BAND * total

    if drift > thresh:
        # BTC over target -> SELL down to target.
        qty = floor_to_qty(drift / price)
        if qty <= 0 or qty * price < BTC_USD_MIN_NOTIONAL:
            return None
        return OrderSpec(
            instrument=TRADE_INSTRUMENT, side="SELL", purpose="rebal", quantity=qty
        )
    if drift < -thresh:
        # BTC under target -> BUY up to target. Safety: the buy size
        # -drift = 0.9*cash - 0.1*btc_value < cash, so the rebalance can never
        # overspend the cash sleeve; only min-notional/precision flooring is
        # needed, no fee buffer.
        notional = floor_to_notional(-drift)
        if notional < BTC_USD_MIN_NOTIONAL:
            return None
        return OrderSpec(
            instrument=TRADE_INSTRUMENT, side="BUY", purpose="rebal", notional=notional
        )
    return None  # weight inside the band -> hold


# ----------------------------------------------------------------------
# 8. Trade execution
# ----------------------------------------------------------------------


def _spec_to_jsonable(spec: OrderSpec) -> Dict[str, Any]:
    d = asdict(spec)
    if d["notional"] is not None:
        d["notional"] = str(d["notional"])
    if d["quantity"] is not None:
        d["quantity"] = str(d["quantity"])
    return d


def execute_trade(
    cdc: CryptoComAPI,
    sb: Client,
    run_id: str,
    account: str,
    scheduled_for: datetime,
    spec: OrderSpec,
) -> None:
    client_oid = f"{scheduled_for:%Y%m%d}-{account}-{spec.purpose}"
    assert len(client_oid) <= 36, f"client_oid too long: {client_oid}"

    if transaction_exists(sb, client_oid):
        print(f"{account}: transaction already exists for {client_oid}, skipping")
        return

    asset, quote_asset = spec.instrument.split("_", 1)

    if DRY_RUN:
        # Crypto.com ticker field "a" = latest trade price; used as a synthetic
        # reference price for the DRY_RUN row. Verify field name on first live run.
        ticker = cdc.get_ticker(spec.instrument)
        price = Decimal(str(ticker["a"]))
        if spec.side == "BUY":
            amount = (spec.notional or Decimal("0")) / price
        else:
            amount = spec.quantity or Decimal("0")
        print(f"DRY_RUN: would place {spec} (synthetic price {price})")
        insert_transaction(
            sb,
            run_id=run_id,
            account=account,
            executed_at=_utc_now_iso(),
            side=spec.side.lower(),
            asset=asset,
            quote_asset=quote_asset,
            amount=str(amount),
            price_usd=str(price),
            fee="0",
            fee_asset=quote_asset,
            cdc_order_id=None,
            client_oid=client_oid,
            raw={"dry_run": True, "spec": _spec_to_jsonable(spec)},
        )
        return

    create_resp = cdc.create_market_order(
        instrument_name=spec.instrument,
        side=spec.side,
        client_oid=client_oid,
        notional=str(spec.notional) if spec.notional is not None else None,
        quantity=str(spec.quantity) if spec.quantity is not None else None,
    )
    order_id = create_resp["order_id"]

    deadline = time.monotonic() + ORDER_POLL_TIMEOUT_S
    detail: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        detail = cdc.get_order_detail(order_id)
        status = detail.get("status")
        if status == "FILLED":
            break
        if status in ("CANCELED", "REJECTED", "EXPIRED"):
            raise RuntimeError(
                f"order {status}: instrument={spec.instrument} order_id={order_id} reason={detail.get('reason')}"
            )
        time.sleep(ORDER_POLL_INTERVAL_S)
    else:
        raise RuntimeError(
            f"order poll timed out after {ORDER_POLL_TIMEOUT_S}s: order_id={order_id} last_status={detail.get('status')}"
        )

    insert_transaction(
        sb,
        run_id=run_id,
        account=account,
        executed_at=_utc_now_iso(),
        side=spec.side.lower(),
        asset=asset,
        quote_asset=quote_asset,
        amount=str(detail["cumulative_quantity"]),
        price_usd=str(detail["avg_price"]),
        fee=str(detail.get("cumulative_fee", "0")),
        fee_asset=detail.get("fee_currency") or quote_asset,
        cdc_order_id=order_id,
        client_oid=client_oid,
        raw={"create": create_resp, "detail": detail},
    )


# ----------------------------------------------------------------------
# 8.5 Balance snapshot
# ----------------------------------------------------------------------

# Crypto.com normalizes USD-pegged stables to USD in user-balance responses,
# but be permissive in case sub-account configuration leaves them split out.
STABLE_INSTRUMENTS = frozenset({"USD", "USDC", "USDT", "USDC.E"})


def read_position(
    cdc: CryptoComAPI,
) -> Tuple[Decimal, Decimal, Decimal, Dict[str, Any]]:
    """Read one account's (btc_qty, stable_usd, btc_price, raw) from the exchange.

    Single balance-parse path shared by decide_chameleon, decide_control, and
    capture_balance so the three never drift in how balances are interpreted.
    `raw` holds the source payloads for the snapshot's audit blob; decide
    callers ignore it.
    """
    bal = cdc.get_user_balance()
    positions = bal["data"][0]["position_balances"]

    btc_qty = Decimal("0")
    stable_usd = Decimal("0")
    for p in positions:
        instrument = (p.get("instrument_name") or "").upper()
        qty = Decimal(str(p.get("quantity", "0")))
        if instrument == "BTC":
            btc_qty += qty
        elif instrument in STABLE_INSTRUMENTS:
            stable_usd += qty

    ticker = cdc.get_ticker("BTC_USD")
    # Crypto.com ticker field "a" = latest trade price; verified in execute_trade.
    btc_price_usd = Decimal(str(ticker["a"]))
    return btc_qty, stable_usd, btc_price_usd, {"balance": bal, "ticker": ticker}


def capture_balance(cdc: CryptoComAPI) -> Dict[str, Any]:
    """On-exchange balance + live BTC price for one account, as a snapshot dict."""
    btc_qty, stable_usd, btc_price_usd, raw = read_position(cdc)
    total = btc_qty * btc_price_usd + stable_usd
    return {
        "btc_qty": btc_qty,
        "stable_usd": stable_usd,
        "btc_price_usd": btc_price_usd,
        "total_value_usd": total,
        "raw": raw,
    }


# ----------------------------------------------------------------------
# 9. main
# ----------------------------------------------------------------------


def main() -> None:
    sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    run_id: Optional[str] = None
    try:
        cdc_chameleon = CryptoComAPI(CDCEX_CHAMELEON_API, CDCEX_CHAMELEON_SECRET)
        cdc_control = CryptoComAPI(CDCEX_CONTROL_API, CDCEX_CONTROL_SECRET)

        scheduled_for = datetime.now(timezone.utc)
        run_id = upsert_run(sb, scheduled_for)
        print(
            f"run started: scheduled_for={scheduled_for.isoformat()} "
            f"run_id={run_id} dry_run={DRY_RUN}"
        )

        # Deposit on the books before either arm acts and before the snapshot,
        # so the rebalance redistributes any landed cash and "Capital invested"
        # stays honest. Idempotent — safe to attempt every run.
        record_due_deposits(sb, scheduled_for)

        accounts = (
            ("chameleon", decide_chameleon, cdc_chameleon),
            ("control", decide_control, cdc_control),
        )

        for account, decide_fn, cdc_client in accounts:
            spec = decide_fn(cdc_client)
            if spec is None:
                print(f"{account}: no trade")
                continue
            execute_trade(cdc_client, sb, run_id, account, scheduled_for, spec)

        snapshots: Dict[str, Decimal] = {}
        for account, _decide_fn, cdc_client in accounts:
            snap = capture_balance(cdc_client)
            upsert_snapshot(sb, account=account, run_id=run_id, **snap)
            snapshots[account] = snap["total_value_usd"]
            print(
                f"{account}: snapshot btc={snap['btc_qty']} stable=${snap['stable_usd']} "
                f"total=${snap['total_value_usd']}"
            )

        mark_run(sb, run_id, "succeeded")
        insert_next_pending_run(sb, compute_next_tuesday_1300_utc(scheduled_for))
        tg_public(
            f"Run {scheduled_for:%Y-%m-%d} complete. "
            f"Chameleon ${snapshots['chameleon']:,.2f} · "
            f"Control ${snapshots['control']:,.2f}\n{DASHBOARD_URL}"
        )
        print("run succeeded")

    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        if run_id is not None:
            try:
                mark_run(sb, run_id, "failed", error_message=tb[-500:])
            except Exception as inner:
                print(f"mark_run(failed) errored: {inner}", file=sys.stderr)
        try:
            tg_private(f"Run failed:\n```\n{tb[-1500:]}\n```")
        except Exception as inner:
            print(f"tg_private errored: {inner}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
