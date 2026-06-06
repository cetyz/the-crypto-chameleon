# The Crypto Chameleon — build status

The system is built and live: a weekly cron on the GCP VM fires [scripts/run.py](scripts/run.py),
which records due monthly deposits, runs each arm's trade decision (chameleon v8 rebalance,
control DCA), writes `runs` / `transactions` / `valuation_snapshots` to Supabase, and posts
to the public Telegram channel (failures go to the private one). The dashboard under
[webapp/](webapp/) reads snapshots from Supabase. Architecture and conventions live in
[CLAUDE.md](CLAUDE.md); what follows is just the achieved-vs-remaining status.

## Outstanding / to verify

- [ ] **Fee charge model** — confirm whether the taker fee is taken from or charged on top
  of `notional` on the first smallest live BUY; adjust `CONTROL_FEE_BUFFER` (0.5% fallback)
  if needed. ([scripts/run.py](scripts/run.py))
- [ ] **First live Tuesday** (`DRY_RUN=false`): control spends ~full stable balance (snapshot
  `stable_usd ≈ 0`, `btc_qty` up); chameleon rebalances to ≈0.90 weight if outside the
  0.85–0.95 band, else no trade; orders polled to `FILLED`, `raw` stored, public Telegram
  success, private silent.
- [ ] **Dashboard after a deposit run** — "Capital invested" rises $50/arm; % return recomputes
  against the new denominator.
- [ ] **Idempotency re-runs** — re-run same `scheduled_for`: no duplicate `transactions`, one
  snapshot per `(account, run_id)`; `record_due_deposits` twice → one `capital_events` row per
  account (23505 swallowed).
- [ ] **Failure drill** — break a key/URL temporarily → private Telegram alert + non-zero exit.
- [ ] **Cron firing** — `grep CRON /var/log/syslog` confirms the entry fires at the scheduled slot.
- [ ] **Live balance precheck** — confirm both sub-accounts hold the expected stable balance
  before/at the first live run.
- [ ] *(Optional, deferred)* post-deposit balance-shortfall warning to private Telegram
  (phantom-deposit guard).

## Done

1. **Infrastructure, schema & secrets** — GCP `e2-micro` VM with static IP whitelisted at
   Crypto.com (withdraw disabled, both keys); Supabase schema applied with RLS verified (anon
   read-only), `accounts` seeded, `$50` capital seeded per arm; `valuation_snapshots` table +
   `capital_events` idempotency constraint added; all VM `.env` vars (Crypto.com ×2, Supabase,
   Telegram public/private, dashboard URL, `DRY_RUN`) set; both Telegram channels created with
   bot admin. ([schema.sql](schema.sql), [database_instructions.md](database_instructions.md))

2. **Scheduled job — [scripts/run.py](scripts/run.py)** — single-file pipeline the cron invokes
   weekly: weekly-slot scheduling, `runs` upsert, deterministic `client_oid`, idempotent
   transaction inserts, run status + next-pending row, dual-channel Telegram, per-account
   pluggable trade decisions, `DRY_RUN` short-circuit, and balance snapshots (`read_position` /
   `capture_balance` / `upsert_snapshot`). DRY_RUN pipeline verified end-to-end on the VM
   (exit 0, rows land, idempotent re-run, public post).

3. **Dashboard equity from snapshots** — equity chart and sparklines read `valuation_snapshots`
   history (`getSnapshotHistory` + `buildEquitySeriesFromSnapshots`); the old transaction-walk +
   price-backfill path (`buildEquitySeries`, `fetchPrices`, `prices.ts`, helpers) deleted;
   `npm run check`/`build` clean, grep sweep zero; "Capital invested" tile reads $50/arm.
   ([webapp/src/lib/data/index.ts](webapp/src/lib/data/index.ts),
   [webapp/src/lib/metrics.ts](webapp/src/lib/metrics.ts))

4. **Going live — code complete** — monthly deposits ($50/arm, last Friday, auto-recorded
   idempotently via `record_due_deposits`), control DCA (deploy full available stable balance to
   `BTC_USD`), and chameleon v8 funded basket (`target_w=0.90`, `band=0.05`, rebalance to target
   on breach) all implemented and unit-checked against synthetic balances; `DRY_RUN=false` set,
   VM pulled. Remaining confirmation is the live-run checklist above.
   ([scripts/run.py](scripts/run.py), [analysis/strategies/strategy_v8.md](analysis/strategies/strategy_v8.md))

## Decisions locked

- Trade instrument `BTC_USD` (`tradable: true`; `quantity_decimals=5`, `quote_decimals=2`).
- Chameleon: v8 two-way rebalance, `target_w=0.90`, no-trade `band=0.05`, rebalance **to target**
  on breach.
- Control: spends its **entire** available stable balance (when ≥ min notional), not a fixed $50.
- Deposits: $50/arm, last Friday of month, bot auto-records to `capital_events` idempotently
  (calendar-driven, not transfer-detected).
- Conservative fallbacks (not exposed in API metadata): `BTC_USD_MIN_NOTIONAL = $1`,
  `CONTROL_FEE_BUFFER = 0.5%` — flagged in-code, confirm on first live BUY.
- Rollout: go live immediately on merge/pull.

## Honest caveats

- **Phantom-deposit risk** — deposits are recorded from the calendar, not a confirmed transfer;
  a skipped manual deposit overstates invested capital until the row is removed (trades still
  operate on the real balance).
- **Small-scale precision** — at ~$50, rebalance trades may fall below `BTC_USD` min notional and
  are skipped (intended) rather than rejected.
- **v8 strategy caveats** — permanent cash drag at `cash_yield=0`, ambiguous dip-buying drawdown
  effect, taxes unmodelled, single mostly-up cycle. These bound expectations, not correctness.
  ([analysis/strategies/strategy_v8.md](analysis/strategies/strategy_v8.md))
