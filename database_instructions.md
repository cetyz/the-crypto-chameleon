# Database Instructions

How any code in this repo should interact with Supabase. Companion to [supabase_plan.md](supabase_plan.md) (the schema and migration steps) and [CLAUDE.md](CLAUDE.md) (the project's guiding principles).

If you're adding a new entry point — a new SvelteKit route, a new Python script, a one-off backfill — read this first.

## Clients & keys

| Caller | Key | Privileges | Where it lives |
|---|---|---|---|
| Webapp (browser + SSR) | `PUBLIC_SUPABASE_ANON_KEY` | RLS-restricted: `SELECT` only on all four tables | Vercel env vars + git-ignored `webapp/.env` |
| Python job (GitHub Actions) | `SUPABASE_SERVICE_ROLE_KEY` | Bypasses RLS — full read/write | GitHub Actions Secrets only |

The anon key is safe to ship to the browser because RLS guarantees read-only access. The service role key bypasses RLS and **must never** be committed, exposed to the browser, or set in Vercel.

## Tables

Authoritative schema is in [supabase_plan.md:28](supabase_plan.md#L28). Quick reference:

- **`accounts`** — two rows, keyed by `'chameleon' | 'control'`. Stores label and inception date. `starting_capital_usd` is **not** a column; derive it by summing `capital_events`.
- **`capital_events`** — deposits and withdrawals per account. Sum (`deposit` as +, `withdrawal` as −) gives net capital invested.
- **`runs`** — one row per scheduled job execution, plus one `pending` row for the next slot. `scheduled_for` is `UNIQUE` so retries upsert cleanly.
- **`transactions`** — one row per order. Two idempotency-critical fields:
  - `client_oid` — deterministic key set **before** the order is placed; `UNIQUE` constraint catches retry double-placement.
  - `cdc_order_id` — exchange ID returned **after** acceptance; nullable, also `UNIQUE`.
  - `raw` — full API response, kept for audit.

Prices are not stored. See **Where prices come from** below.

## Read patterns (webapp)

The dashboard's canonical queries are listed in [supabase_plan.md:157](supabase_plan.md#L157). When adding new reads:

- Import the singleton client: `import { supabase } from '$lib/supabase'` ([webapp/src/lib/supabase.ts](webapp/src/lib/supabase.ts)).
- Run reads in `+page.server.ts` (server-side load), not in components. Components stay dumb renderers.
- Read public env vars via `$env/static/public` (SvelteKit inlines them at build time).
- Map column names to component-facing types **at the query boundary** — e.g. `executed_at → timestamp` in [webapp/src/lib/data/index.ts](webapp/src/lib/data/index.ts) — so [webapp/src/lib/types.ts](webapp/src/lib/types.ts) and the components don't need to track schema renames.
- Pass SvelteKit's `event.fetch` down to anything that hits an external API (e.g. [webapp/src/lib/prices.ts](webapp/src/lib/prices.ts)) so SSR gets HTTP-level caching.

## Write patterns (Python job)

All writes go through `service_role`. The idempotency protocol is laid out in [supabase_plan.md:170](supabase_plan.md#L170); restated as rules:

1. **One `runs` row per `scheduled_for`.** Use `INSERT ... ON CONFLICT (scheduled_for) DO UPDATE SET status='running', started_at=now() RETURNING id`. A retry of the same scheduled slot updates the existing row, doesn't create a second.
2. **Deterministic `client_oid` per order.** Format: `{scheduled_for:%Y%m%d}-{account}-{purpose}` (or equivalent). Same inputs must produce the same key.
3. **Check before placing.** `SELECT 1 FROM transactions WHERE client_oid = ?` — if present, skip. Belt-and-braces alongside the `UNIQUE` constraint.
4. **Place the order on Crypto.com passing `client_oid` as the exchange's idempotency hint.**
5. **Insert the transaction with the full API response** in `raw`. If a concurrent retry beat us in, the `UNIQUE(client_oid)` constraint raises — catch and move on.
6. **On success:** `UPDATE runs SET status='succeeded', finished_at=now()` for the current run, then `INSERT` the next `pending` row at the next cadence slot.
7. **On failure:** `UPDATE runs SET status='failed', error_message=...` and send a Telegram alert to the **private** channel (per [CLAUDE.md](CLAUDE.md)). Do not exit cleanly.

## RLS invariants

- All four tables have `ROW LEVEL SECURITY` enabled.
- Anon role has `SELECT` policies only — no insert, update, or delete policies for `anon`.
- Service role bypasses RLS by design.

Do not add anon write policies, and do not disable RLS on any table, without explicit review. Verification snippet (run as `anon` in the SQL Editor) is in [supabase_plan.md:132](supabase_plan.md#L132): a `SELECT` succeeds, an `INSERT` fails with `new row violates row-level security policy`. Both outcomes are required to confirm the gate is live.

## Where prices come from

Supabase does **not** store prices. The dashboard fetches historical and live prices from Crypto.com's public candlestick endpoint via [webapp/src/lib/prices.ts](webapp/src/lib/prices.ts).

Reasons:
- Free-tier storage stays focused on the small, append-only trade and capital tables.
- Transparency: anyone can re-derive the chart from a public endpoint with no credentials.

If a feature needs persisted price history (e.g. detailed audit of execution slippage), introduce a new table — don't repurpose existing ones.

## Changing the schema

Schema migrations are run by hand in the Supabase SQL Editor following [supabase_plan.md](supabase_plan.md). Until that stops scaling (multiple environments, multiple contributors, frequent migrations), don't introduce a CLI-driven migration tool. When that day comes, move to `supabase/migrations/` + the Supabase CLI.

In the meantime: any schema change must update [supabase_plan.md](supabase_plan.md) and this document in the same commit so they don't drift.
