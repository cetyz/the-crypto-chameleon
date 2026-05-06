-- The Crypto Chameleon — Supabase schema.
-- Apply by pasting into the Supabase SQL Editor (or psql) on a fresh project.
-- Companion: database_instructions.md.

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
-- client_oid is the idempotency key — set deterministically before the order is
-- placed so a retry produces the same value and trips UNIQUE instead of
-- double-placing. cdc_order_id is returned by Crypto.com after acceptance and
-- is therefore nullable. raw stores the full API response for audit.
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

-- ========== valuation_snapshots ==========
-- One row per (account, run) capturing the on-exchange balance and the BTC
-- price used to value it. Source of truth for the dashboard's "Current value"
-- tile. run_id is nullable to allow future ad-hoc snapshots outside a run.
create table public.valuation_snapshots (
  id              uuid primary key default gen_random_uuid(),
  account         text not null references public.accounts(key) on delete restrict,
  run_id          uuid references public.runs(id) on delete set null,
  snapshot_at     timestamptz not null default now(),
  btc_qty         numeric(38, 18) not null check (btc_qty >= 0),
  stable_usd      numeric(20, 8)  not null check (stable_usd >= 0),
  btc_price_usd   numeric(20, 8)  not null check (btc_price_usd > 0),
  total_value_usd numeric(20, 8)  not null check (total_value_usd >= 0),
  raw             jsonb,
  unique (account, run_id)
);
create index valuation_snapshots_account_snapshot_at_idx
  on public.valuation_snapshots (account, snapshot_at desc);

-- ========== Row Level Security ==========
-- Anon role gets SELECT-only across all tables. service_role bypasses RLS by
-- design, so writes (the Python job) need no policy.
alter table public.accounts             enable row level security;
alter table public.capital_events       enable row level security;
alter table public.runs                 enable row level security;
alter table public.transactions         enable row level security;
alter table public.valuation_snapshots  enable row level security;

create policy "anon reads accounts"
  on public.accounts             for select to anon using (true);
create policy "anon reads capital_events"
  on public.capital_events       for select to anon using (true);
create policy "anon reads runs"
  on public.runs                 for select to anon using (true);
create policy "anon reads transactions"
  on public.transactions         for select to anon using (true);
create policy "anon reads valuation_snapshots"
  on public.valuation_snapshots  for select to anon using (true);
