# Supabase Plan

Step-by-step guide to standing up the Supabase project that backs the Crypto Chameleon. Companion to [dashboard_plan.md](dashboard_plan.md) and the principles in [CLAUDE.md](CLAUDE.md).

## What Supabase holds

Four tables — nothing else:

- `accounts` — metadata for the two accounts (`chameleon`, `control`).
- `capital_events` — deposits/withdrawals per account. Summing gives net capital invested.
- `runs` — one row per scheduled job execution, including the next `pending` run.
- `transactions` — one row per order placed on Crypto.com.

Prices are **not** stored. The dashboard fetches them live from Crypto.com's public candlestick endpoint.

## Prerequisites

- A Supabase account (free tier is fine). Create a new project, pick the region closest to the GitHub Actions runner (`us-east-1` is a safe default).
- Three secrets, noted from **Project Settings → API**:
  - `SUPABASE_URL` — the project URL.
  - `SUPABASE_ANON_KEY` — public key. Goes into Vercel (dashboard reads).
  - `SUPABASE_SERVICE_ROLE_KEY` — secret key. Goes into GitHub Actions Secrets only. **Never commit, never expose to the browser.**

## Step 1 — Run the schema migration

Open the Supabase **SQL Editor** → New query → paste the block below → Run.

```sql
-- ========== accounts ==========
create table public.accounts (
  key            text primary key check (key in ('chameleon', 'control')),
  label          text not null,
  inception_date date not null
);

-- ========== capital_events ==========
create table public.capital_events (
  id          uuid primary key default gen_random_uuid(),
  account     text not null references public.accounts(key) on delete restrict,
  occurred_at timestamptz not null,
  kind        text not null check (kind in ('deposit', 'withdrawal')),
  amount_usd  numeric(20, 2) not null check (amount_usd > 0),
  note        text
);
create index capital_events_account_occurred_at_idx
  on public.capital_events (account, occurred_at);

-- ========== runs ==========
create table public.runs (
  id            uuid primary key default gen_random_uuid(),
  scheduled_for timestamptz not null unique,
  started_at    timestamptz,
  finished_at   timestamptz,
  status        text not null check (status in ('pending','running','succeeded','failed','partial')),
  error_message text
);
create index runs_status_scheduled_for_idx
  on public.runs (status, scheduled_for);

-- ========== transactions ==========
create table public.transactions (
  id           uuid primary key default gen_random_uuid(),
  run_id       uuid not null references public.runs(id) on delete restrict,
  account      text not null references public.accounts(key) on delete restrict,
  executed_at  timestamptz not null,
  side         text not null check (side in ('buy', 'sell')),
  asset        text not null,
  quote_asset  text not null default 'USD',
  amount       numeric(38, 18) not null check (amount > 0),
  price_usd    numeric(20, 8)  not null check (price_usd > 0),
  fee          numeric(38, 18) not null default 0,
  fee_asset    text not null default 'USD',
  cdc_order_id text unique,
  client_oid   text not null unique,
  raw          jsonb
);
create index transactions_account_executed_at_idx
  on public.transactions (account, executed_at desc);
create index transactions_run_id_idx
  on public.transactions (run_id);
```

### Column notes

- `client_oid` is the idempotency key — the Python job derives it deterministically from the run context so a retry produces the same value and trips the `UNIQUE` constraint instead of double-placing an order. See "Idempotency protocol" below.
- `cdc_order_id` comes back from Crypto.com after the order is accepted; it is nullable because we set `client_oid` before we know the exchange ID.
- `raw` stores the full API response for audit. Free-tier row size is not a concern at weekly cadence.
- Amounts use `numeric(38, 18)` — big enough for any crypto size, exact (not floating-point).

## Step 2 — Enable Row Level Security

Paste and run:

```sql
alter table public.accounts        enable row level security;
alter table public.capital_events  enable row level security;
alter table public.runs            enable row level security;
alter table public.transactions    enable row level security;

create policy "anon reads accounts"
  on public.accounts        for select to anon using (true);
create policy "anon reads capital_events"
  on public.capital_events  for select to anon using (true);
create policy "anon reads runs"
  on public.runs            for select to anon using (true);
create policy "anon reads transactions"
  on public.transactions    for select to anon using (true);
```

`service_role` bypasses RLS — no write policies are needed. The dashboard uses the anon key; the GitHub Actions job uses the service role key.

## Step 3 — Seed rows

Paste and run. Adjust the inception date and starting capital to whatever you intend to fund.

```sql
insert into public.accounts (key, label, inception_date) values
  ('chameleon', 'Chameleon',     '2025-10-22'),
  ('control',   'Control (DCA)', '2025-10-22');

insert into public.capital_events (account, occurred_at, kind, amount_usd, note) values
  ('chameleon', '2025-10-22T00:00:00Z', 'deposit', 10000, 'inception'),
  ('control',   '2025-10-22T00:00:00Z', 'deposit', 10000, 'inception');

-- One pending run so the dashboard's "next run" query returns something before the first job runs.
-- Replace with the real first cron slot.
insert into public.runs (scheduled_for, status) values
  ('2026-04-29T14:00:00Z', 'pending');
```

## Step 4 — Verify RLS with the anon key

In the SQL Editor, switch role to `anon` (top-right role selector) and run:

```sql
select * from public.transactions;  -- should succeed (returns 0 rows for now)
insert into public.accounts (key, label, inception_date)
  values ('hacker', 'nope', '2026-01-01');  -- should FAIL with "new row violates row-level security policy"
```

Both outcomes confirm the policies are live.

## Step 5 — Store the keys

- **Vercel** → project → Settings → Environment Variables:
  - `PUBLIC_SUPABASE_URL` = `SUPABASE_URL`
  - `PUBLIC_SUPABASE_ANON_KEY` = `SUPABASE_ANON_KEY`
- **GitHub** → repo → Settings → Secrets and variables → Actions:
  - `SUPABASE_URL`
  - `SUPABASE_SERVICE_ROLE_KEY`
- Local `.env` (git-ignored) mirrors the Vercel entries for dev.

## How the dashboard reads each section

Computed in `webapp/src/routes/+page.server.ts` from four SQL reads + live Crypto.com prices:

| Dashboard piece                   | Query / source                                                                                           |
|-----------------------------------|----------------------------------------------------------------------------------------------------------|
| Headline tile: capital invested   | `select sum(case kind when 'deposit' then amount_usd else -amount_usd end) from capital_events where account = ?` |
| Headline tile: portfolio USD      | walk `transactions` forward → holdings, value each asset at live Crypto.com ticker price                 |
| Headline tile: portfolio BTC      | portfolio_usd / live BTC price                                                                           |
| Headline tile: % return           | `(portfolio_usd - net_capital) / net_capital`                                                            |
| Sparkline + equity chart          | walk `transactions` forward at each sample timestamp, value via Crypto.com `public/get-candlestick`      |
| Next-run countdown                | `select scheduled_for from runs where status='pending' order by scheduled_for asc limit 1`               |
| Last-updated                      | `select max(finished_at) from runs where status='succeeded'`                                             |
| Transaction tables                | `select … from transactions where account=? order by executed_at desc limit ?`                            |

## Idempotency protocol (how the Python job writes safely)

Each scheduled run:

1. Compute `scheduled_for` by snapping "now" onto the weekly cadence.
2. `insert into runs (scheduled_for, status, started_at) values (?, 'running', now()) on conflict (scheduled_for) do update set status='running', started_at=now() returning id` — survives retries.
3. For each planned order, compute `client_oid` deterministically, e.g. `f"{scheduled_for:%Y%m%d}-{account}-{purpose}"`.
4. `select 1 from transactions where client_oid = ?` — if present, the order was already placed on a prior attempt; skip.
5. Place the order on Crypto.com passing that `client_oid`.
6. Poll for fill, then `insert into transactions (...)`. If a concurrent retry inserted first, the `UNIQUE(client_oid)` constraint raises — catch and move on.
7. On success: `update runs set status='succeeded', finished_at=now() where id=?`, then insert the next `runs` row with `status='pending'` and the next cadence slot.
8. On failure: `update runs set status='failed', error_message=?`, then send a Telegram alert to the **private** channel (per [CLAUDE.md](CLAUDE.md)).

## Deferred (flagged for later, not schema-blocking)

- **% return formula under top-ups.** Simple return understates performance when a deposit lands mid-period. Time-weighted or money-weighted return is a metrics-layer choice; the schema supports either.
- **Delisted assets.** Historical candlestick fetch may fail for a pair that has been delisted; fall back to the last known price.
- **Fixture cleanup.** `webapp/src/lib/data/fixtures/` can be deleted once live reads are green.

## Webapp edits to apply after Supabase is live

These are deferred to a follow-up session — do not apply until the migration above has been run and verified.

### Install + env

- `cd webapp && npm install @supabase/supabase-js`
- Add `PUBLIC_SUPABASE_URL` and `PUBLIC_SUPABASE_ANON_KEY` to `webapp/.env` (git-ignored).

### New files

- **`webapp/src/lib/supabase.ts`** — export a singleton `createClient(PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY)`.
- **`webapp/src/lib/prices.ts`** — given a set of assets and a time range, call Crypto.com `public/get-candlestick` per asset and return a `PriceMap` compatible with [webapp/src/lib/metrics.ts](webapp/src/lib/metrics.ts). Use SvelteKit's `event.fetch` so SSR can cache the response.

### Edits to [webapp/src/lib/data/index.ts](webapp/src/lib/data/index.ts)

Replace the JSON-fixture reads with Supabase calls. Each current function gets a live-data body:

- `getAccounts()` → `supabase.from('accounts').select('*')`, then for each account attach `starting_capital_usd = SUM(capital_events)` (one extra query) so the existing `Account` type in [webapp/src/lib/types.ts:3](webapp/src/lib/types.ts#L3) keeps working.
- `getTransactions(account?)` → `supabase.from('transactions').select('id, account, executed_at, side, asset, amount, price_usd').order('executed_at', { ascending: false })`. Map `executed_at` → `timestamp` when constructing the `Transaction` object to match the existing type.
- `getNextRun()` → two queries: `scheduled_for` from the earliest `pending` run + `max(finished_at)` from succeeded runs.
- `getEquityCurve()` → replace `pricesFixture` with `await fetchPrices(heldAssets, range)` from `prices.ts`; otherwise keep `buildEquitySeries` unchanged — it already works on a `PriceMap`.
- `getAccountSummaries()` → same substitution; keep the existing derivation via [metrics.ts](webapp/src/lib/metrics.ts).

### Edits to [webapp/src/lib/types.ts](webapp/src/lib/types.ts)

No shape changes needed if `starting_capital_usd` is attached server-side (see `getAccounts` above). Revisit only if the dashboard ever needs to show the raw event history.

### Do not touch

- `webapp/src/lib/components/*.svelte` — the components are dumb renderers. They consume the same types and need no changes.
- `webapp/src/lib/metrics.ts` — the math is `PriceMap`-agnostic and works unchanged against live prices.
