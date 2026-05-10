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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Literal, Optional

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

CADENCE_DAYS = 7
ORDER_POLL_TIMEOUT_S = 30
ORDER_POLL_INTERVAL_S = 1

CONTROL_DCA: Dict[str, Any] = {
    "enabled": False,
    "instrument": "BTC_USD",
    "notional": Decimal("0"),
}


# ----------------------------------------------------------------------
# 3-4. Schedule
# ----------------------------------------------------------------------


def compute_scheduled_for(now: datetime) -> datetime:
    """Snap `now` to the most recent Monday 12:00 UTC at or before now."""
    candidate = (now - timedelta(days=now.weekday())).replace(
        hour=12, minute=0, second=0, microsecond=0
    )
    if candidate > now:
        candidate -= timedelta(days=7)
    return candidate


def compute_next_run(scheduled_for: datetime) -> datetime:
    return scheduled_for + timedelta(days=CADENCE_DAYS)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def decide_chameleon(cdc: CryptoComAPI) -> Optional[OrderSpec]:
    return None  # TODO: implement strategy


def decide_control(cdc: CryptoComAPI) -> Optional[OrderSpec]:
    if not CONTROL_DCA["enabled"]:
        return None
    return OrderSpec(
        instrument=CONTROL_DCA["instrument"],
        side="BUY",
        purpose="dca",
        notional=CONTROL_DCA["notional"],
    )


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


def capture_balance(cdc: CryptoComAPI) -> Dict[str, Any]:
    """Read on-exchange balance + live BTC price for one account."""
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

    total = btc_qty * btc_price_usd + stable_usd
    return {
        "btc_qty": btc_qty,
        "stable_usd": stable_usd,
        "btc_price_usd": btc_price_usd,
        "total_value_usd": total,
        "raw": {"balance": bal, "ticker": ticker},
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

        scheduled_for = compute_scheduled_for(datetime.now(timezone.utc))
        run_id = upsert_run(sb, scheduled_for)
        print(
            f"run started: scheduled_for={scheduled_for.isoformat()} "
            f"run_id={run_id} dry_run={DRY_RUN}"
        )

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
        insert_next_pending_run(sb, compute_next_run(scheduled_for))
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
