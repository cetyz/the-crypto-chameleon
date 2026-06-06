"""High-resolution valuation-snapshot job (hourly cron on the GCP VM).

Additive, read-only sibling of run.py: between weekly trading runs it reads each
arm's on-exchange balance + the BTC ticker and inserts an intermediate
`valuation_snapshots` row with `run_id = NULL` so the dashboard equity chart has
more than one point per week. It moves no money, touches no `runs` row, and
applies no schema migration.

It deliberately reuses run.py's exact balance-parse path (`capture_balance` →
`read_position`) and failure channel (`tg_private`) by importing run.py, so the
two jobs can never drift in how a balance is interpreted. Importing run.py
re-runs its module-level `_require(...)` for every env var it needs; the VM's
single `.env` defines them all, so that is fine here.
"""

from __future__ import annotations

import os
import sys
import traceback
from decimal import Decimal
from typing import Any

# run.py lives in this package dir and does `from cdc import CryptoComAPI`, where
# cdc.py sits at the repo root. Put both on sys.path so `from run import ...`
# (and run.py's own `from cdc import ...`) resolve regardless of how cron invokes
# this file (`python -m scripts.snapshot`, `python scripts/snapshot.py`, etc.).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_SCRIPT_DIR)
for _p in (_SCRIPT_DIR, _REPO_ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from supabase import Client, create_client

from cdc import CryptoComAPI
from run import (
    CDCEX_CHAMELEON_API,
    CDCEX_CHAMELEON_SECRET,
    CDCEX_CONTROL_API,
    CDCEX_CONTROL_SECRET,
    SUPABASE_SERVICE_ROLE_KEY,
    SUPABASE_URL,
    capture_balance,
    tg_private,
)


def insert_standalone_snapshot(
    sb: Client,
    *,
    account: str,
    btc_qty: Decimal,
    stable_usd: Decimal,
    btc_price_usd: Decimal,
    total_value_usd: Decimal,
    raw: Any = None,  # accepted but intentionally not persisted (see below)
) -> None:
    """Insert one intermediate snapshot row.

    `run_id` is omitted (→ NULL): Postgres treats NULLs as distinct under the
    `unique (account, run_id)` constraint, so these never conflict with each
    other or with run.py's per-run rows — a plain INSERT, no upsert needed.
    `snapshot_at` is omitted (→ DB `default now()`). `raw` is dropped to keep the
    table lean; the dashboard never reads it and only run.py's weekly snapshot
    keeps the audit blob.
    """
    sb.table("valuation_snapshots").insert(
        {
            "account": account,
            "btc_qty": str(btc_qty),
            "stable_usd": str(stable_usd),
            "btc_price_usd": str(btc_price_usd),
            "total_value_usd": str(total_value_usd),
        }
    ).execute()


def main() -> None:
    try:
        sb: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        accounts = (
            ("chameleon", CryptoComAPI(CDCEX_CHAMELEON_API, CDCEX_CHAMELEON_SECRET)),
            ("control", CryptoComAPI(CDCEX_CONTROL_API, CDCEX_CONTROL_SECRET)),
        )

        for account, cdc in accounts:
            snap = capture_balance(cdc)
            insert_standalone_snapshot(sb, account=account, **snap)
            print(
                f"{account}: snapshot btc={snap['btc_qty']} "
                f"stable=${snap['stable_usd']} total=${snap['total_value_usd']}"
            )

        print("snapshot succeeded")

    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        try:
            tg_private(f"Snapshot job failed:\n```\n{tb[-1500:]}\n```")
        except Exception as inner:
            print(f"tg_private errored: {inner}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
