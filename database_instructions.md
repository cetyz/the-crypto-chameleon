# Database Instructions

How any code in this repo should interact with Supabase. The authoritative schema lives in [schema.sql](schema.sql). Project guiding principles are in [CLAUDE.md](CLAUDE.md).

If you're adding a new entry point — a new SvelteKit route, a new Python script, a one-off backfill — read this first.

## Clients & keys

| Caller | Key | Privileges | Where it lives |
|---|---|---|---|
| Webapp (browser + SSR) | `PUBLIC_SUPABASE_ANON_KEY` | RLS-restricted: `SELECT` only on all four tables | Vercel env vars + git-ignored `webapp/.env` |
| Python job (GitHub Actions) | `SUPABASE_SERVICE_ROLE_KEY` | Bypasses RLS — full read/write | GitHub Actions Secrets only |

The anon key is safe to ship to the browser because RLS guarantees read-only access. The service role key bypasses RLS and **must never** be committed, exposed to the browser, or set in Vercel.

## Tables

Authoritative schema is in [schema.sql](schema.sql). Quick reference:

- **`accounts`** — two rows, keyed by `'chameleon' | 'control'`. Stores label and inception date. `starting_capital_usd` is **not** a column; derive it by summing `capital_events`.
- **`capital_events`** — deposits and withdrawals per account. Sum (`deposit` as +, `withdrawal` as −) gives net capital invested.
- **`runs`** — one row per scheduled job execution, plus one `pending` row for the next slot. `scheduled_for` is `UNIQUE` so retries upsert cleanly.
- **`transactions`** — one row per order. Two idempotency-critical fields:
  - `client_oid` — deterministic key set **before** the order is placed; `UNIQUE` constraint catches retry double-placement.
  - `cdc_order_id` — exchange ID returned **after** acceptance; nullable, also `UNIQUE`.
  - `raw` — full API response, kept for audit.

Prices are not stored. See **Where prices come from** below.

## Read patterns (webapp)

The live source of truth for the dashboard's queries is [webapp/src/lib/data/index.ts](webapp/src/lib/data/index.ts). When adding new reads:

- Import the singleton client: `import { supabase } from '$lib/supabase'` ([webapp/src/lib/supabase.ts](webapp/src/lib/supabase.ts)).
- Run reads in `+page.server.ts` (server-side load), not in components. Components stay dumb renderers.
- Read public env vars via `$env/static/public` (SvelteKit inlines them at build time).
- Map column names to component-facing types **at the query boundary** — e.g. `executed_at → timestamp` in [webapp/src/lib/data/index.ts](webapp/src/lib/data/index.ts) — so [webapp/src/lib/types.ts](webapp/src/lib/types.ts) and the components don't need to track schema renames.
- Pass SvelteKit's `event.fetch` down to anything that hits an external API (e.g. [webapp/src/lib/prices.ts](webapp/src/lib/prices.ts)) so SSR gets HTTP-level caching.

## Write patterns (Python job)

All writes go through `service_role`. Real money is at stake and runs may be retried by GitHub Actions, so the protocol is built around two idempotency guarantees: one `runs` row per `scheduled_for` slot, and one `transactions` row per logical order (keyed by `client_oid`).

Each scheduled run does this:

1. **Compute `scheduled_for`** by snapping "now" onto the configured cadence (e.g. weekly).
2. **Upsert the run row.** Survives retries — same `scheduled_for` updates the existing row instead of creating a second.
   ```sql
   insert into runs (scheduled_for, status, started_at)
   values (?, 'running', now())
   on conflict (scheduled_for) do update
     set status = 'running', started_at = now()
   returning id;
   ```
3. **Compute `client_oid` deterministically** for each planned order. Same inputs must produce the same key — that's what makes a retry safe. Example format: `f"{scheduled_for:%Y%m%d}-{account}-{purpose}"`, e.g. `20260429-chameleon-rotate`.
4. **Pre-check** before hitting the exchange. Belt-and-braces alongside the `UNIQUE` constraint:
   ```sql
   select 1 from transactions where client_oid = ?;
   ```
   If a row exists, the order was placed on a prior attempt — skip.
5. **Place the order on Crypto.com**, passing `client_oid` as the exchange's idempotency hint.
6. **Poll for fill, then insert the transaction** with the full API response in `raw`. If a concurrent retry inserted first, the `UNIQUE(client_oid)` constraint raises — catch and move on.
7. **On success:** `update runs set status='succeeded', finished_at=now() where id=?`, then `insert` the next `runs` row with `status='pending'` and the next cadence slot — this is what the dashboard's "Next run" countdown reads.
8. **On failure:** `update runs set status='failed', error_message=?` and send a Telegram alert to the **private** channel (per [CLAUDE.md](CLAUDE.md)). Do not exit cleanly — silent failure is unacceptable.

## RLS invariants

- All four tables have `ROW LEVEL SECURITY` enabled.
- Anon role has `SELECT` policies only — no insert, update, or delete policies for `anon`.
- Service role bypasses RLS by design.

Do not add anon write policies, and do not disable RLS on any table, without explicit review. To verify the gate is live, switch the SQL Editor role to `anon` and run:

```sql
select * from public.transactions;
-- expected: succeeds (returns 0 rows pre-first-run)

insert into public.accounts (key, label, inception_date)
  values ('hacker', 'nope', '2026-01-01');
-- expected: ERROR — new row violates row-level security policy
```

Both outcomes — the read succeeding and the write failing — are required.

## Known limitations

- **`% return` under top-ups.** Today's calculation treats `starting_capital_usd` as the sum of all `capital_events` and compares against current portfolio value — a simple return that understates performance when a deposit lands mid-period. When top-ups become routine, switch to a time-weighted or money-weighted return; the schema already supports either.
- **Delisted assets.** [webapp/src/lib/prices.ts](webapp/src/lib/prices.ts) returns an empty series for any asset whose Crypto.com candlestick fetch fails, which means a delisted holding is currently valued at `$0` in the equity chart. Fix when a delisting actually bites by falling back to the last known price (e.g. cached at the last successful fetch, or stored alongside the transaction).

## Where prices come from

Supabase does **not** store prices. The dashboard fetches historical and live prices from Crypto.com's public candlestick endpoint via [webapp/src/lib/prices.ts](webapp/src/lib/prices.ts).

Reasons:
- Free-tier storage stays focused on the small, append-only trade and capital tables.
- Transparency: anyone can re-derive the chart from a public endpoint with no credentials.

If a feature needs persisted price history (e.g. detailed audit of execution slippage), introduce a new table — don't repurpose existing ones.

## Changing the schema

[schema.sql](schema.sql) is the single source of truth. Migrations are run by hand in the Supabase SQL Editor — paste the `CREATE TABLE` blocks (or a targeted `ALTER TABLE`) directly. Until this stops scaling (multiple environments, multiple contributors, frequent migrations), don't introduce a CLI-driven migration tool. When that day comes, move to `supabase/migrations/` + the Supabase CLI, with `schema.sql` as the starting baseline.

In the meantime: any schema change must update [schema.sql](schema.sql) and this document in the same commit so they don't drift.
