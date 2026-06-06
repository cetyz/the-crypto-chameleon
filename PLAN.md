# The Crypto Chameleon — build status

The system is built and live: a weekly cron on the GCP VM fires [scripts/run.py](scripts/run.py),
which records due monthly deposits, runs each arm's trade decision (chameleon v8 rebalance,
control DCA), writes `runs` / `transactions` / `valuation_snapshots` to Supabase, and posts
to the public Telegram channel (failures go to the private one). The dashboard under
[webapp/](webapp/) reads snapshots from Supabase. Architecture and conventions live in
[CLAUDE.md](CLAUDE.md); what follows is just the achieved-vs-remaining status.

## Outstanding / to verify

### Higher-resolution valuation snapshots (separate 12-hourly cron)

**Intent.** Today the weekly trading job ([scripts/run.py](scripts/run.py)) is the only writer
of `valuation_snapshots`, so the dashboard equity chart has a resolution of one point per week
and hides intra-week movement. Add a **second, 12-hourly cron** that snapshots balances between
weekly runs for a smoother chart. The change is **additive and read-only** (reads on-exchange
balances + the BTC ticker, inserts valuation rows) — **no trades, no schema migration, no
dashboard code change.**

**Decisions (locked with the user).**
- Keep run.py's own post-trade snapshot; the new job only *adds* intermediate `run_id = NULL`
  snapshots (lowest risk, fully additive).
- Cadence: **12-hourly** (~4 rows/day across both arms, ~1.5k/year — trivial vs. Supabase free
  tier and Crypto.com read-only rate limits).
- On failure: **private Telegram alert + non-zero exit**, mirroring run.py's failure policy.

**Why it's low-risk.**
- `valuation_snapshots.run_id` is **already nullable** ([schema.sql](schema.sql):69,
  `on delete set null`; the schema comment explicitly allows "ad-hoc snapshots outside a run").
- The unique constraint is `unique (account, run_id)` ([schema.sql](schema.sql):76). Postgres
  treats NULLs as distinct in a UNIQUE constraint, so multiple `(account, NULL)` rows are
  allowed — a plain `INSERT` with `run_id` omitted never conflicts.
- The dashboard reads snapshots **purely by `snapshot_at`**, never selecting or filtering on
  `run_id` (`getSnapshotHistory` / `buildEquitySeriesFromSnapshots` in
  [webapp/src/lib/data/index.ts](webapp/src/lib/data/index.ts) /
  [webapp/src/lib/metrics.ts](webapp/src/lib/metrics.ts)). Extra rows = more chart points.
- The job uses the service-role key (bypasses RLS) like run.py — no RLS change.

**Design — new `scripts/snapshot.py` (built later, no code in this task).**
- Reuse run.py's exact balance-parse path by importing from it (no edits to the live money
  script): `capture_balance(cdc)` ([scripts/run.py](scripts/run.py):530) and `tg_private`
  ([scripts/run.py](scripts/run.py):292), plus the already-validated env constants
  (`CDCEX_*`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`). Importing run.py re-runs its
  module-level `_require(...)` for all its env vars (incl. `DASHBOARD_URL`, `DRY_RUN`,
  `TELEGRAM_PUBLIC_CHANNEL_ID`) — fine on the VM, which defines them in the same `.env`.
- `main()`: create the Supabase client + both `CryptoComAPI` clients; for each account
  `snap = capture_balance(cdc)` then a small `insert_standalone_snapshot` doing a plain
  `valuation_snapshots` insert of `account, btc_qty, stable_usd, btc_price_usd,
  total_value_usd` (Decimals → `str`) with **`run_id` omitted (→ NULL)**, **`snapshot_at`
  omitted (→ DB `default now()`)**, and **`raw` omitted** to keep the table lean (dashboard
  never reads `raw`; only run.py's weekly snapshot keeps the audit blob). Wrap in a try/except
  mirroring run.py:598–610 (print traceback, `tg_private(...)`, `sys.exit(1)`); it touches no
  `runs` row. Do **not** reuse `upsert_snapshot` — it requires a `run_id` via
  `on_conflict="account,run_id"`.
- No idempotency key needed (moves no money; a near-duplicate row is just an extra chart
  point). Safe to overlap the weekly run — different rows (NULL vs. real run_id).

**VM wiring (lives on the VM, not the repo).** Add a 12-hourly crontab entry (e.g.
`0 */12 * * *`, firing 00:00 and 12:00) invoking `scripts/snapshot.py` with the **venv**
interpreter and the **same working dir / module invocation run.py already uses** (`scripts/`
is a package; confirm `python -m scripts.run` vs `python scripts/run.py` and mirror it so
`from cdc import ...` and the `from run import ...` reuse both resolve). Reuse the existing
`.env`; log output for cron verification.

Commands to set it up on the VM (run as the same user run.py's cron runs under):
- [x] Open the crontab for editing: `crontab -e`
- [x] Add the entry, mirroring run.py's invocation style and absolute paths (adjust
  `<REPO>`/venv path to match the existing run.py line):
  ```
  0 */12 * * * cd /home/<user>/<REPO> && /home/<user>/<REPO>/venv/bin/python -m scripts.snapshot >> /home/<user>/<REPO>/snapshot.log 2>&1
  ```
- [x] Save and confirm it registered: `crontab -l` shows the new `0 */12 * * *` line.
- [x] Smoke-test the exact command by hand once (without waiting for cron): run the part after
  the timestamp and check exit 0 + two rows land.
- [x] After the first scheduled fire, tail the log: `tail -f /home/<user>/<REPO>/snapshot.log`.

To verify (when built):
- [x] **Snapshot insert** — run `scripts/snapshot.py` once: two rows land with `run_id IS NULL`,
  `raw IS NULL`, `snapshot_at ≈ now`, `total_value_usd = btc_qty*btc_price_usd + stable_usd`.
- [x] **Dashboard** — equity chart shows the new intermediate point(s); headline tiles
  (`getLatestSnapshots`) pick up the freshest row; no errors.
- [ ] **Failure drill** — break a Crypto.com key / `SUPABASE_URL` → private Telegram alert +
  non-zero exit; public channel silent.
- [ ] **No run.py regression** — run.py is untouched; its weekly invocation still imports and
  runs (it does not import snapshot.py).
- [ ] **Cron firing** — `grep CRON /var/log/syslog` shows the 12-hourly entry; `valuation_snapshots`
  grows ~2 rows per fire (~4/day).

### Others

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
