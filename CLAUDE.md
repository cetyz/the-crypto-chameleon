# The Crypto Chameleon

A public-facing dashboard that transparently tracks two Crypto.com Exchange trading accounts: an algorithmic "chameleon" account that makes analysis-driven trading decisions, and a "control" account that performs simple DCA purchases. Runs on a configurable schedule (default weekly), writes each run's transactions to a shared database, and announces updates to a Telegram channel.

## Architecture

Three decoupled components:

- **Scheduled Python job (GitHub Actions)** — runs on a cron schedule. On each run it:
  1. Performs trading analysis and executes a trade on the **chameleon** Crypto.com account.
  2. Executes a DCA purchase on the **control** Crypto.com account.
  3. Writes all resulting transactions to Supabase.
  4. Posts an announcement to the public Telegram channel linking to the dashboard.
- **SvelteKit dashboard (Vercel, free tier)** — public, read-only. Reads from Supabase and displays transactions for both accounts. Visitors can interact with visual filters (time ranges, account selector, cuts) but cannot mutate data. REFER TO `dashboard_plan.md`.
- **Supabase (free tier)** — shared persistence layer. Row Level Security configured so that the anon/public role has read-only access; writes go through a service role used only by the GitHub Actions job.

### Why GitHub Actions instead of Vercel cron
Vercel Hobby tier caps serverless execution time and has Python cold-start friction. GitHub Actions runs Python natively with generous free-tier minutes and easy secrets management — a better fit for a beginner and for weekly trading-logic runs.

## Repository layout (intended)
- `cdc.py` — Crypto.com Exchange API wrapper (existing).
- `/scripts` or similar — Python entry points invoked by the scheduled job. Architecture (single script vs. many) is an open decision.
- `/webapp` — SvelteKit dashboard deployed to Vercel.
- `.github/workflows/` — scheduled workflow(s).

## Environments & secrets
- **Crypto.com sandbox** is used for development (already supported in `cdc.py` via `use_sandbox=True`). Never develop or test against the production API with real funds.
- Two sets of Crypto.com API credentials: one for the **chameleon** account, one for the **control** account.
- Secrets live in GitHub Actions Secrets (for the Python job) and Vercel environment variables (for the dashboard). Never committed.

## Guiding principles

### Trade safety & idempotency
Real money is at stake. Each scheduled run must be safe to re-run: a crash, retry, or partially completed run must not cause duplicate trades. Favor explicit guards (e.g. checking for an existing transaction record before placing an order) over assumptions about execution order.

### Failure alerting
Silent failures are unacceptable — if a scheduled run fails, the user needs to know. Reuse the Telegram bot to send failure messages to a **private** channel/chat (distinct from the public announcement channel). The scheduled job should not exit cleanly on partial failure.

### Public read-only dashboard
The dashboard is a transparency tool. Anyone can view. No authentication needed to read. Interactions are client-side visual controls only — never writes, never privileged reads.

### Keep it barebones
The user is new to development and values simplicity. Prefer the fewest moving parts that work. Defer abstractions, frameworks-within-frameworks, and premature configuration surfaces until a concrete need appears.

## Deliberately deferred
These are acknowledged as open and will be decided as the project evolves:
- Specific trading analysis logic and decision rules for the chameleon account.
- DCA amount, asset, and frequency for the control account.
- Cadence specifics (default: weekly, but configurable).
- Supabase table schema.
- Telegram message content/format.
- Whether the Python side is one script or several orchestrated scripts.
