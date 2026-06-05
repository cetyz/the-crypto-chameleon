# Plan: First end-to-end scheduled run

## Context

Infrastructure pieces are in place: GCP `e2-micro` VM has a static IP, [cdc.py](cdc.py) authenticates against Crypto.com, the dashboard shell exists under [webapp/](webapp/), and the Supabase schema is designed in [schema.sql](schema.sql) with a documented write protocol in [database_instructions.md](database_instructions.md).

What's missing is the **scheduled Python job** itself — the script that cron actually invokes. Without it, nothing flows end-to-end: no rows appear in Supabase, the dashboard has nothing to render, and the Telegram channel stays silent.

The intended outcome of this plan is one shakedown run executed end-to-end on the VM, with rows visible in Supabase and messages posted to both Telegram channels — without placing any real trades. Both trading strategies (chameleon analysis, control DCA params) are deliberately deferred per discussion; the script supports a `DRY_RUN` flag so the full pipeline can be exercised first, and a tiny real trade enabled afterwards by config.

## Approach

One Python entry script (`scripts/run.py`) plus thin helpers, invoked by a single cron line on the VM. The script implements the write protocol from [database_instructions.md](database_instructions.md) verbatim — including deterministic `client_oid` and `runs` upsert — but each account's trade decision is a pluggable function returning either `None` (no trade) or an order spec. v1: chameleon returns `None`, control reads from a config block but defaults to disabled. `DRY_RUN=true` short-circuits the actual `create_market_order` call; everything else (run rows, transaction inserts with synthetic data, Telegram posts, next-run scheduling) still happens so we can verify the pipeline.

Single file rather than a package. Per CLAUDE.md ("keep it barebones") and the refactoring note about preferring large modules with simple interfaces over scattered silos. We can split if it grows.

## Pre-flight verification (manual, before code)

These are checks, not code changes — but they belong in the plan because the script depends on them.

### 1. Confirm Supabase schema is applied + seed accounts

- [x] In Supabase Dashboard → SQL Editor, run `select * from public.accounts;` and handle one of three outcomes:
  - [x] **Two rows (`chameleon`, `control`) returned** → done.
  - [ ] **Empty result, no error** → schema applied, just seed:
    ```sql
    insert into public.accounts (key, label, inception_date) values
      ('chameleon', 'Chameleon', current_date),
      ('control',   'Control',   current_date);
    ```
  - [ ] **Error: relation does not exist** → paste the entire contents of [schema.sql](schema.sql) into the SQL Editor and run, then run the seed insert above.
- [x] Verify RLS gate per [database_instructions.md](database_instructions.md): switch SQL Editor role to `anon`. `select * from public.transactions;` should succeed (0 rows). `insert into public.accounts (...)` should fail with an RLS error.

### 2. Create Telegram channels and capture IDs

- [x] Create a **public** Telegram channel (the announcement channel — visitors of the dashboard will see this). Add the existing bot as admin with "post messages" permission.
- [x] Create a **private** chat or channel for failure alerts. Add the bot.
- [x] Capture both chat IDs. Easiest method: send a message to each from your account, then GET `https://api.telegram.org/bot<TOKEN>/getUpdates` and read `chat.id` from the JSON. Public channel IDs are negative integers like `-1001234567890`.

### 3. Capture VM env vars

The VM `.env` already has the chameleon Crypto.com keys (`CDCEX_API`, `CDCEX_SECRET`) since `cdc.py` runs. Add:

- [x] Rename existing chameleon keys:
  ```
  CDCEX_CHAMELEON_API=...
  CDCEX_CHAMELEON_SECRET=...
  ```
- [x] Add control keys (separate API key from Crypto.com sub-account):
  ```
  CDCEX_CONTROL_API=...
  CDCEX_CONTROL_SECRET=...
  ```
- [x] Add Supabase vars:
  ```
  SUPABASE_URL=https://<project-ref>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY=...
  ```
- [x] Add Telegram vars:
  ```
  TELEGRAM_BOT_TOKEN=...
  TELEGRAM_PUBLIC_CHANNEL_ID=-100...
  TELEGRAM_PRIVATE_CHAT_ID=...
  ```
- [x] Add dashboard URL (linked from Telegram messages):
  ```
  DASHBOARD_URL=https://<vercel-deployment>.vercel.app
  ```
- [x] Add safety flag:
  ```
  DRY_RUN=true
  ```
- [x] Confirm both Crypto.com API keys whitelist the VM's static IP and have **withdraw permission disabled**.

## Code changes

### Files to create/modify

- [x] `requirements.txt` — edit: add `supabase` (supabase-py). Telegram uses the existing `requests` dep — no SDK needed.
- [x] `scripts/__init__.py` — create: empty, marks package.
- [x] `scripts/run.py` — create: the entry script. ~200 lines.
- [x] `database_instructions.md` — edit: replace "GitHub Actions" references with "VM + cron"; correct the env-vars location (VM `.env`, not GitHub Secrets).

### `scripts/run.py` — structure

Single file, top-to-bottom readable. Sections in order:

- [x] **1. Imports + env load** — `dotenv.load_dotenv()`, then read all required vars; raise immediately if any are missing (fail fast at startup, not mid-trade).
- [x] **2. Constants** — `CADENCE_DAYS = 7`, `DRY_RUN = os.environ["DRY_RUN"].lower() == "true"`, control-DCA config block (asset, notional, enabled bool — defaults to `enabled=False`).
- [x] **3. `compute_scheduled_for(now) -> datetime`** — snap `now` to the weekly UTC slot (e.g. Monday 12:00 UTC). Pure function, easy to unit-test later.
- [x] **4. `compute_next_run(scheduled_for) -> datetime`** — `scheduled_for + timedelta(days=CADENCE_DAYS)`.
- [x] **5. Supabase helpers** (inline functions, not a class):
  - [x] `upsert_run(sb, scheduled_for) -> run_id` — implements the `INSERT ... ON CONFLICT (scheduled_for) DO UPDATE` from [database_instructions.md](database_instructions.md) step 2. supabase-py's `.upsert(..., on_conflict='scheduled_for')` does this.
  - [x] `transaction_exists(sb, client_oid) -> bool`
  - [x] `insert_transaction(sb, **fields)` — catches the `UNIQUE(client_oid)` violation and returns silently (per protocol step 6).
  - [x] `mark_run(sb, run_id, status, error_message=None)`
  - [x] `insert_next_pending_run(sb, next_scheduled_for)`
- [x] **6. Telegram helpers**:
  - [x] `tg_send(chat_id, text)` — single function, posts to `https://api.telegram.org/bot<TOKEN>/sendMessage` with `parse_mode='Markdown'`.
  - [x] `tg_public(text)` / `tg_private(text)` — thin wrappers passing the right chat ID.
- [x] **7. Trade decision functions** (the "pluggable" part):
  - [x] `decide_chameleon(cdc_chameleon) -> Optional[OrderSpec]` — for v1, returns `None`. Comment placeholder: `# TODO: implement strategy`.
  - [x] `decide_control(cdc_control) -> Optional[OrderSpec]` — reads config block; if `enabled=False`, returns `None`; else returns `OrderSpec(side='BUY', instrument='BTC_USD', notional=...)`.
  - [x] `OrderSpec` is a dataclass with `instrument`, `side`, `notional` (for buys) or `quantity` (for sells), `purpose` (string for the client_oid).
- [x] **8. `execute_trade(cdc, sb, run_id, account, scheduled_for, spec)`**:
  - [x] Compute `client_oid = f"{scheduled_for:%Y%m%d}-{account}-{spec.purpose}"` (≤36 chars — verify).
  - [x] Pre-check `transaction_exists(sb, client_oid)` → return early if true (retry-safe).
  - [x] If `DRY_RUN`: log "would place order: ..." and `insert_transaction` with synthetic price (current ticker), `cdc_order_id=None`, `raw={'dry_run': True, 'spec': asdict(spec)}`. This proves the DB path end-to-end.
  - [x] Else: `cdc.create_market_order(...)` → poll `get_order_detail(order_id)` until status is `FILLED` (with timeout, e.g. 30s) → `insert_transaction` with real fields and `raw=full_response`.
- [x] **9. `main()`**:
  - [x] Wrap entire body in try/except.
  - [x] Build two `CryptoComAPI` instances: chameleon, control. (Master not needed for v1.)
  - [x] Build Supabase client with service role key.
  - [x] `scheduled_for = compute_scheduled_for(now_utc)`
  - [x] `run_id = upsert_run(sb, scheduled_for)`
  - [x] For each (account, decide_fn, cdc_client): `spec = decide_fn(cdc_client)`; if `spec`: `execute_trade(...)` else log "no trade".
  - [x] `mark_run(sb, run_id, 'succeeded')`
  - [x] `insert_next_pending_run(sb, compute_next_run(scheduled_for))`
  - [x] `tg_public(f"Run for {scheduled_for:%Y-%m-%d} complete. {DASHBOARD_URL}")`
  - [x] On exception: `mark_run(sb, run_id, 'failed', error_message=traceback)`, `tg_private(f"❌ Run failed:\n```\n{traceback}\n```")`, `sys.exit(1)`.

### What NOT to add in v1

- No retry loop around `main()` itself (cron + idempotency handle this).
- No structured logging framework — `print` to stdout, cron captures into a log file.
- No tests (defer until the script stabilizes).
- No `argparse` (one env-var gate, `DRY_RUN`, is enough).

## VM setup (after code merged + pulled)

- [x] 1. `cd ~/the-crypto-chameleon && git pull`
- [x] 2. `source venv/bin/activate && pip install -r requirements.txt`
- [x] 3. Update `~/the-crypto-chameleon/.env` per the env vars list above. **Confirm `DRY_RUN=true` for first run.**
- [x] 4. Manual dry-run: `python -m scripts.run`. Expect:
  - [x] Exit code 0.
  - [x] One new row in `runs` with `status='succeeded'`.
  - [x] One new row in `runs` with `status='pending'` for the next slot.
  - [x] Zero rows in `transactions` (since both decide functions return `None` in v1).
  - [x] One Telegram message in the public channel.
  - [x] No message in the private channel.
- [x] 5. If step 4 passes, install the cron entry. Edit `crontab -e`:
  ```
  0 13 * * 2 cd /home/<USER>/the-crypto-chameleon && /home/<USER>/the-crypto-chameleon/venv/bin/python -m scripts.run >> /home/<USER>/chameleon.log 2>&1
  ```
  (Tuesdays at 13:00 server time. TZ on the VM is UTC - checked.)

## Verification (end-to-end checklist)

- [x] `select * from public.accounts;` returns 2 rows.
- [x] Anon SQL `insert` into any table fails with RLS error.
- [x] Both Telegram channels exist; bot is admin.
- [x] All env vars set on VM; `python -c "import os, dotenv; dotenv.load_dotenv(); print(sorted(k for k in os.environ if k.startswith(('CDCEX','SUPABASE','TELEGRAM','DASHBOARD','DRY'))))"` lists every key from the table above.
- [x] Manual dry-run exits 0, run row + next-pending row visible in Supabase Table Editor, public Telegram message arrives.
- [x] Re-run the same script immediately. Same `scheduled_for` slot → second invocation upserts (does not create a duplicate `runs` row); next-pending row stays a single row. **This proves idempotency.**
- [ ] Force a failure (e.g. temporarily wrong `SUPABASE_URL`). Private Telegram channel receives an error message; script exits non-zero.
- [ ] Cron entry installed and `grep CRON /var/log/syslog` shows it firing at the next scheduled slot.

## Open items deferred (not blocking this plan)

- [x] Chameleon strategy logic (decide_chameleon body). _Resolved: v8 funded basket, `target_w = 0.90`, `band = 0.05` — see "Going live: monthly deposits + real trades" below._
- [x] Control DCA params (asset, frequency). _Resolved: spend entire available stable balance into `BTC_USD` on the post-deposit Tuesday — see "Going live" below._
- [ ] Whether to denominate DCA in a stablecoin pair (`BTC_USDT`) vs USD (`BTC_USD`) — depends on what's tradable from each account; check with `get_instruments()` once (folded into the "Going live" pre-flight below).
- [x] Dashboard deployment to Vercel — the webapp shell already exists; once the first run row lands in Supabase, this becomes the next priority.
- [x] Update `database_instructions.md`'s "GitHub Actions" references to "VM + cron + .env" (small, do alongside).

## Capital seeding & live valuation

The v1 plan above did not specify starting capital or a live valuation path. Without these, the dashboard's "Capital invested" tile reads $0 (no `capital_events` rows) and "Current value" sits at the seed amount indefinitely (no `transactions` while `decide_chameleon` returns `None`). Decision: $50 USD per account, plus a balance-snapshot table written by the VM script and read by the dashboard.

### Schema + seed

- [x] `schema.sql` — add `valuation_snapshots` table (`account`, `run_id`, `snapshot_at`, `btc_qty`, `stable_usd`, `btc_price_usd`, `total_value_usd`, `raw`) with `unique(account, run_id)` and an anon `select` policy.
- [x] `database_instructions.md` — document `valuation_snapshots` and the price-storage carve-out.
- [x] Apply the new table by pasting the `valuation_snapshots` block into the Supabase SQL Editor.
- [x] Seed starting capital in the SQL Editor:
  ```sql
  insert into public.capital_events (account, occurred_at, kind, amount_usd, note) values
    ('chameleon', now(), 'deposit', 50, 'initial seed'),
    ('control',   now(), 'deposit', 50, 'initial seed');
  ```
- [x] Confirm both Crypto.com sub-accounts hold ≥$50 in stable balance (USD/USDC/USDT) before the first run.

### Code

- [x] `scripts/run.py` — add `upsert_snapshot()` and `capture_balance()`; second pass in `main()` snapshots both accounts after trade decisions; public Telegram message includes both totals.
- [x] `webapp/src/lib/types.ts` — add `ValuationSnapshot` interface.
- [x] `webapp/src/lib/data/index.ts` — add `getLatestSnapshots()`; `getAccountSummaries()` prefers `total_value_usd` from the snapshot, falling back to the transaction-walked value when no snapshot exists yet.

### Verification

- [x] After seed: dashboard's "Capital invested" tile reads $50 for each account.
- [ ] Manual dry-run: two new `valuation_snapshots` rows (one per account); each `total_value_usd ≈ 50.00`. Dashboard's "Current value" tile reflects the snapshot.
- [ ] Re-run the script: one row per `(account, run_id)` (upsert, no duplicates).
- [ ] Manually buy a small BTC notional on one account, re-run: that account's snapshot shows `btc_qty > 0`, `stable_usd` reduced, `total_value_usd ≈ unchanged` (modulo fees/spread).

### Out of scope (follow-ups)

- Higher-frequency snapshots (a second cron line) for a more responsive dashboard.

## Snapshot-based equity series (webapp)

### Context

The VM side of valuation tracking is done: `scripts/run.py`'s `capture_balance()` (line 363) and `upsert_snapshot()` (line 161) write one `valuation_snapshots` row per `(account, run_id)` on every weekly run, and `main()` runs the snapshot loop after the trade-decision loop (lines 423-431). On the webapp side, [webapp/src/lib/data/index.ts](webapp/src/lib/data/index.ts) already exposes `getLatestSnapshots()` (line 103) and `getAccountSummaries()` (line 136) prefers snapshot `total_value_usd` for the "Current value" tile.

What's still transaction-walked:
- `getEquityCurve()` ([data/index.ts:129](webapp/src/lib/data/index.ts)) builds `EquityPoint[]` via `buildEquitySeries(transactions, …)`, which requires `fetchPrices()` to backfill historical OHLC per held asset to inception.
- The sparkline slice in `getAccountSummaries()` ([data/index.ts:172](webapp/src/lib/data/index.ts)) reads the same transaction-walked curve.

With no trades placed yet (`decide_chameleon` returns `None`, `CONTROL_DCA.enabled = False`), `transactions` is empty → `heldAssets` is empty → `fetchPrices` returns nothing → the chart and sparklines render blank. The earlier "needs ~12 weeks of snapshots first" note was overcautious: snapshots are the better source of truth for this dashboard regardless of trade activity (single computed value per run, no external price backfill, survives zero-trade weeks, reflects mark-to-market between runs).

Goal: switch the equity chart and sparklines to read `valuation_snapshots` history so the dashboard begins populating from the first weekly snapshot onward, with no changes to `scripts/run.py`. Then remove the now-dead transaction-replay path.

### Files to modify

Confirmed call-site scope: the **only** caller of `getEquityCurve()` / `getAccountSummaries()` is [webapp/src/routes/+page.server.ts](webapp/src/routes/+page.server.ts) (grep verified). `getAccountSummaries()` already prefers `snapshot.total_value_usd` for `portfolio_usd` / `cash_usd` / `btc_qty` ([data/index.ts:154-168](webapp/src/lib/data/index.ts)); only the sparkline slice and the `portfolioHoldings()` `else` fallback still depend on transactions + prices.

- [x] `webapp/src/lib/data/index.ts`
  - [x] Add `getSnapshotHistory(): Promise<ValuationSnapshot[]>` — selects `account, snapshot_at, btc_qty, stable_usd, btc_price_usd, total_value_usd` from `valuation_snapshots` ordered ascending by `snapshot_at`. Mirrors the column list in `getLatestSnapshots()` ([data/index.ts:103-127](webapp/src/lib/data/index.ts)); factor the row-mapping into a small `mapSnapshotRow(row)` helper shared by both to avoid drift.
  - [x] Rewrite `getEquityCurve()` ([data/index.ts:129-134](webapp/src/lib/data/index.ts)):
    - New signature: `export async function getEquityCurve(): Promise<EquityPoint[]>` — drop the `fetch` parameter.
    - Body: `const [accounts, history] = await Promise.all([getAccounts(), getSnapshotHistory()]); return buildEquitySeriesFromSnapshots(history, startingMap(accounts));`
  - [x] Rewrite `getAccountSummaries()` ([data/index.ts:136-175](webapp/src/lib/data/index.ts)):
    - New signature: `export async function getAccountSummaries(): Promise<AccountSummary[]>` — drop `fetch`.
    - Replace the `Promise.all` with `[accounts, snapshots, history]` (`getAccounts()` + `getLatestSnapshots()` + `getSnapshotHistory()`); drop `getTransactions()`, `fetchPrices()`, `buildEquitySeries()`, `heldAssets`.
    - Derive `curve` via `buildEquitySeriesFromSnapshots(history, startingMap(accounts))`. Sparkline tail logic (`SPARKLINE_POINTS = 12`) unchanged.
    - Drop the `else` fallback to `portfolioHoldings(...)` — both accounts now write a snapshot every run, so the fallback is dead. Reduce to a single snapshot-driven path. If `snapshot` is unexpectedly missing, fall back to `{ portfolio_usd: account.starting_capital_usd, cash_usd: account.starting_capital_usd, btc_qty: 0 }` (pre-first-run zero-trade state).
    - Replace `portfolioValueBTC(portfolio_usd, prices)` with `snapshot && snapshot.btc_price_usd > 0 ? portfolio_usd / snapshot.btc_price_usd : 0`.
  - [x] Remove imports: `buildEquitySeries`, `portfolioHoldings`, `portfolioValueBTC` from `$lib/metrics`; `fetchPrices` from `$lib/prices`.
  - [x] Delete `earliestInception()` ([data/index.ts:91-94](webapp/src/lib/data/index.ts)) — its only caller was `fetchPrices`. Keep `startingMap()` — still used by both rewritten functions.

- [x] `webapp/src/lib/metrics.ts`
  - [x] Add `buildEquitySeriesFromSnapshots(snapshots: ValuationSnapshot[], starting: Record<AccountKey, number>): EquityPoint[]`. Snapshots arrive ordered ascending by `snapshot_at`; group by `snapshot_at` and emit one `EquityPoint` per unique timestamp:
    - `chameleon_usd` / `control_usd` = that account's `total_value_usd` at this timestamp, else the last carried-forward value (init = `starting[account]`).
    - `chameleon_btc` / `control_btc` = `total_value_usd / btc_price_usd` for that account at this timestamp, else carry forward (init = 0).
    - `chameleon_pct` / `control_pct` = `percentReturn(usd, starting[account])` reusing the existing helper at [metrics.ts:89-92](webapp/src/lib/metrics.ts).
    - Carry-forward keeps the chart honest if one account ever misses a snapshot (defensive — `scripts/run.py` writes both every run today).

- [x] `webapp/src/lib/types.ts` — no change. `ValuationSnapshot` and `EquityPoint` already cover every field used above.

- [x] `webapp/src/routes/+page.server.ts` — drop `fetch` from the two updated calls:
  ```ts
  getAccountSummaries(),
  getEquityCurve(),
  ```
  `fetch` itself can stay in the `load` destructure or be removed; SvelteKit is fine either way. No other call sites (`+layout.server.ts`, `+page.svelte`, components) reference these functions.

### Cleanup of redundant code

Same PR, after verifying the chart renders from real snapshot data. Delete in this order, grep-sweeping between steps:

- [x] `webapp/src/lib/metrics.ts`
  - [x] Delete `buildEquitySeries` ([metrics.ts:94-125](webapp/src/lib/metrics.ts)) — transaction-walking equity series.
  - [x] Delete `portfolioHoldings` ([metrics.ts:69-82](webapp/src/lib/metrics.ts)) — fallback branch is gone.
  - [x] Delete `portfolioValueUSD` ([metrics.ts:59-67](webapp/src/lib/metrics.ts)) — only consumer was the deleted equity path; verify with grep before removing.
  - [x] Delete `portfolioValueBTC` ([metrics.ts:84-87](webapp/src/lib/metrics.ts)) — replaced inline in `getAccountSummaries()`.
  - [x] Delete internal helpers `walk` ([metrics.ts:26-46](webapp/src/lib/metrics.ts)), `valueUSD` ([metrics.ts:48-57](webapp/src/lib/metrics.ts)), `priceAt` ([metrics.ts:5-13](webapp/src/lib/metrics.ts)), `currentPrice` ([metrics.ts:15-19](webapp/src/lib/metrics.ts)) — only used by the deleted public functions. Grep-confirm.
  - [x] **Keep** `percentReturn` — used by `buildEquitySeriesFromSnapshots` and `getAccountSummaries`.

- [x] `webapp/src/lib/prices.ts` — delete the entire file. The only consumer was `data/index.ts`; after the rewrite it has none. Also remove its `PriceMap` / `PricePoint` types (defined in this file; grep first to confirm no other importers).

- [x] `webapp/src/lib/data/index.ts` — confirm post-rewrite state: `earliestInception` deleted, `startingMap` kept, `buildEquitySeries` / `portfolioHoldings` / `portfolioValueBTC` / `fetchPrices` imports gone. The `Transaction` type import is still needed by `getTransactions()` — keep it.

- [x] Stale tests: none currently in `webapp/src/**/*.test.ts`; if any appear, delete or rewrite against the snapshot path.

- [x] **Final grep sweep** — each must return zero hits outside `git log`:
  - `buildEquitySeries\b` (the old name, not `FromSnapshots`)
  - `fetchPrices`
  - `earliestInception`
  - `portfolioHoldings`
  - `portfolioValueUSD`
  - `portfolioValueBTC`
  - `PriceMap`, `PricePoint`

The intent stays conservative: rewrite first, verify the chart populates from real snapshot data, then delete. A single follow-up commit for the cleanup is fine if it makes the diff easier to review.

### Verification

- [x] With at least one `valuation_snapshots` row per account in Supabase (already true if the weekly cron has fired), `npm run dev` in `webapp/` and load `/`: equity chart shows one point per run, both accounts plotted; sparklines on the account-summary cards show the same series.
- [x] Manually trigger another snapshot (`python -m scripts.run` on the VM with `DRY_RUN=true`) and reload: a second point appears on the chart and sparkline without any code change.
- [x] "Current value" tile still matches `total_value_usd` from the latest snapshot (no regression from the unchanged snapshot branch).
- [x] After cleanup commit: `npm run check` / `npm run build` succeed; no dead-code warnings; grepping for `buildEquitySeries`, `fetchPrices`, and `earliestInception` returns zero hits outside of git history.

### Out of scope (still)

- Higher-frequency snapshot cadence.
- Backfilling pre-snapshot equity (impossible by definition — both accounts started with the first snapshot).

## Going live: monthly deposits + real trades

### Context

The DRY_RUN pipeline is verified end-to-end: the weekly Tuesday cron fires
[scripts/run.py](scripts/run.py), `runs` / `transactions` / `valuation_snapshots`
rows land in Supabase, and both Telegram channels behave. What's still inert is the
money: `decide_chameleon` returns `None` and the `CONTROL_DCA` block is disabled, so
**no real buying or selling happens**. This section closes that last gap.

Three behaviours go live together:

- **Deposits.** $50 USD is deposited into *each* arm on the last Friday of every
  month. The bot records these into the existing `capital_events` table itself,
  idempotently, so the dashboard's "Capital invested" denominator stays honest and
  the % return isn't inflated by counting deposits as gains. (Trading does not
  depend on these rows — both arms read live on-exchange balances — they exist
  purely for accounting.)
- **Control arm.** On the first Tuesday after a deposit, it spends its entire
  available stable balance on `BTC_USD`. A simple DCA, robust to dust and to a
  missed run (cash deploys the next run rather than being stranded).
- **Chameleon arm.** Implements [analysis/strategies/strategy_v8.md](analysis/strategies/strategy_v8.md) —
  the funded two-way basket — at **`target_w = 0.90`, `band = 0.05` each side**: hold
  while BTC weight sits in 0.85–0.95, otherwise rebalance *all the way back* to 0.90
  (sell if over, buy if under). A landed deposit just shows up as cash that the next
  rebalance redistributes; no special-casing.

### Decisions locked

- Deposits auto-recorded by the bot into `capital_events`, idempotently (safe to re-run) — not manual, not balance-detected.
- Control buys with its **entire available stable balance** (when ≥ BTC_USD min notional) — not a fixed $50.
- Chameleon: v8 two-way rebalance, `target_w = 0.90`, no-trade `band = 0.05`; on breach, rebalance **to target**, not to the band edge.
- Rollout: **go live immediately** — flip `DRY_RUN=false` on merge + pull; the next Tuesday run places real trades.

### Schema change (apply once in Supabase SQL Editor)

- [ ] Add idempotency to `capital_events` so the bot can re-attempt the same monthly insert safely:
  ```sql
  alter table public.capital_events
    add constraint capital_events_account_occurred_kind_key
    unique (account, occurred_at, kind);
  ```
  Mirrors the `transactions.client_oid` discipline — a retry trips the unique and is swallowed (`23505`) instead of double-recording.
- [ ] No other schema change. Deposits feed the existing "Capital invested" sum and % return baseline; the webapp's `getAccounts()` already reads `capital_events`.

### Pre-flight (one-time, read-only, before code)

- [ ] Use the **notebooklm** skill against the Crypto.com notebook (per CLAUDE.md "NotebookLM-first") to confirm:
  - `create_market_order` market-BUY `notional` semantics — is the taker fee deducted *from* the notional or charged *on top*? (Drives `CONTROL_FEE_BUFFER` below.)
  - `BTC_USD` **min order size / min notional**, `quantity_decimals`, and notional precision.
- [ ] Call `get_instruments()` once and record `BTC_USD`'s min notional + decimals. Hardcode as constants (barebones — instrument metadata is stable). This also resolves the deferred `BTC_USD` vs `BTC_USDT` denomination question above.
- [ ] Confirm both sub-accounts currently hold the stable balance you expect (seed ± any deposits already made).

### Code — [scripts/run.py](scripts/run.py)

**Constants**
- [ ] `MONTHLY_DEPOSIT_USD = Decimal("50")`
- [ ] `CHAMELEON_TARGET_W = Decimal("0.90")`, `CHAMELEON_BAND = Decimal("0.05")`
- [ ] `BTC_USD_MIN_NOTIONAL`, `BTC_USD_QTY_DECIMALS`, `BTC_USD_NOTIONAL_DECIMALS` from pre-flight.
- [ ] `CONTROL_FEE_BUFFER = Decimal("0.005")` — shave the control buy so the fee doesn't overdraw the balance (final value pending the NotebookLM answer).
- [ ] Retire the `CONTROL_DCA` disabled block — replaced by balance-driven logic.

**Deposit helpers (new)**
- [ ] `last_friday_of_month(year, month) -> date`.
- [ ] `most_recent_deposit_date(now) -> date` — last Friday of the current month if `<= now.date()`, else last Friday of the previous month. Use that date at `00:00 UTC` as `occurred_at` so the value is deterministic and the unique constraint makes re-runs no-ops.
- [ ] `record_due_deposits(sb, now)` — for the most-recent deposit date, attempt `insert` into `capital_events` (`kind='deposit'`, `amount_usd=50`, `note='monthly auto-deposit'`) for **both** accounts; catch `APIError` code `23505` and continue (reuse the existing `insert_transaction` 23505 pattern). No date arithmetic against the previous run is needed — idempotency makes "attempt every run" safe.

**Shared balance read (refactor)**
- [ ] Factor the BTC/stable/price read out of `capture_balance` into `read_position(cdc) -> (btc_qty, stable_usd, btc_price)` so `decide_chameleon`, `decide_control`, and `capture_balance` share one code path (no drift in how balances are parsed). `capture_balance` keeps building the snapshot dict on top of it.

**Rounding helpers (new)**
- [ ] `floor_to_qty(x)` / `floor_to_notional(x)` — `Decimal.quantize(..., rounding=ROUND_DOWN)` to instrument precision. Flooring keeps orders inside the available balance and avoids precision rejects.

**`decide_control(cdc)`**
- [ ] `btc_qty, stable_usd, price = read_position(cdc)`
- [ ] `spend = floor_to_notional(stable_usd * (1 - CONTROL_FEE_BUFFER))`
- [ ] `if spend < BTC_USD_MIN_NOTIONAL: return None` (no fresh deposit cash to deploy)
- [ ] `return OrderSpec(instrument="BTC_USD", side="BUY", purpose="dca", notional=spend)`
- No calendar logic — control's steady state is ~0 cash (it spends everything monthly), so this fires only when a deposit lands, and is robust to a missed Tuesday.

**`decide_chameleon(cdc)` — v8 funded basket**
- [ ] `btc_qty, stable_usd, price = read_position(cdc)`
- [ ] `btc_value = btc_qty * price`; `total = btc_value + stable_usd`; `if total <= 0: return None`
- [ ] `target_value = CHAMELEON_TARGET_W * total`; `drift = btc_value - target_value`; `thresh = CHAMELEON_BAND * total`
- [ ] `if drift > thresh:` BTC too heavy → SELL down to target. `qty = floor_to_qty(drift / price)`; `if qty < min: return None`; `return OrderSpec(side="SELL", purpose="rebal", quantity=qty)`
- [ ] `elif drift < -thresh:` BTC too light → BUY up to target. `notional = floor_to_notional(-drift)`; `if notional < min: return None`; `return OrderSpec(side="BUY", purpose="rebal", notional=notional)`
- [ ] `else: return None` (weight inside 0.85–0.95 → hold; the fee-saving band)
- Code-comment the safety proof: the buy size `-drift = 0.9·cash − 0.1·btc_value < cash`, so the rebalance can never overspend the cash sleeve; only min-notional/precision flooring is needed, no fee buffer.

**`main()`**
- [ ] Call `record_due_deposits(sb, scheduled_for)` **right after `upsert_run`**, before the trade loop — deposit is on the books before either arm acts and before the snapshot.
- [ ] Trade loop and snapshot loop otherwise unchanged (`decide_fn` → `execute_trade`; then `capture_balance` → `upsert_snapshot`).
- [ ] (Optional safeguard) after snapshots, if a deposit was recorded this run but the post-trade combined balance is materially short of expected, `tg_private` a non-blocking warning.
- [ ] `client_oid` lengths fine: `20260630-chameleon-rebal` = 24 chars (≤36).

**No change** to `execute_trade` (BUY-by-notional / SELL-by-quantity, DRY_RUN, 30s fill polling, idempotent insert already correct) or to the Telegram / run-status plumbing.

### Config / VM

- [ ] `.env` on VM: set `DRY_RUN=false`. All other vars already present.
- [ ] `git pull` on the VM; `pip install -r requirements.txt` (no new deps). The existing Tuesday cron fires the first live run.

### Verification

- [ ] **Date helpers** (local): `last_friday_of_month` / `most_recent_deposit_date` against a few known months, including a Tuesday that falls *before* that month's last Friday (must pick the previous month's Friday).
- [ ] **Chameleon decision** (local, synthetic balances): weight 1.00 → SELL; weight ~0.50 (fresh deposit) → BUY; weight 0.90 → None; weight 0.93 → None (inside band).
- [ ] **Deposit idempotency**: run `record_due_deposits` twice for the same month → exactly one `capital_events` row per account (23505 swallowed).
- [ ] **Run idempotency**: re-run with the same `scheduled_for` → no duplicate `transactions` (unique `client_oid`), one snapshot per `(account, run_id)`.
- [ ] **Dashboard**: after a deposit run, "Capital invested" rises by $50 per account; % return recomputes against the new denominator.
- [ ] **First live Tuesday** (`DRY_RUN=false`):
  - control: one buy tx spending ~full stable balance; snapshot `stable_usd ≈ 0`, `btc_qty` up.
  - chameleon: if outside band, one rebal tx and snapshot weight ≈ 0.90; else no tx and weight within 0.85–0.95.
  - `get_order_detail` polled to `FILLED`; `raw` stored; public Telegram success post; private channel silent.
- [ ] **Failure drill**: temporarily break a key → private Telegram alert + non-zero exit (already handled by `main()`'s try/except).

### Honest caveats

- **Phantom-deposit risk** (accepted trade-off of auto-record): the bot records the scheduled $50 from the calendar, not from a confirmed transfer. If a manual deposit is skipped, `capital_events` overstates invested capital until the row is deleted; the optional balance warning flags it, and the trades simply operate on the real (smaller) balance.
- **Small-scale precision**: at ~$50, rebalance trades can be a few dollars — they must clear `BTC_USD` min-notional or they're skipped (intended) rather than rejected (the min-notional guards ensure this).
- **v8 strategy caveats still apply** ([strategy_v8.md](analysis/strategies/strategy_v8.md)): permanent cash drag with `cash_yield = 0`, dip-buying's ambiguous drawdown effect, taxes unmodelled, single mostly-up cycle. These bound expectations, not correctness.
