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

- [ ] Chameleon strategy logic (decide_chameleon body).
- [ ] Control DCA params (asset, frequency). _Notional resolved: $50 seed per account — see "Capital seeding & live valuation" below._
- [ ] Whether to denominate DCA in a stablecoin pair (`BTC_USDT`) vs USD (`BTC_USD`) — depends on what's tradable from each account; check with `get_instruments()` once.
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

- Switching the equity chart and sparklines from transaction-walked to snapshot-history-based — needs ~12 weeks of accumulated snapshots first.
- Higher-frequency snapshots (a second cron line) for a more responsive dashboard.
