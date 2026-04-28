# The Crypto Chameleon

A public-facing dashboard that transparently tracks two Crypto.com Exchange trading accounts: an algorithmic "chameleon" account that makes analysis-driven trading decisions, and a "control" account that performs simple DCA purchases. Runs on a configurable schedule (default weekly), writes each run's transactions to a shared database, and announces updates to a Telegram channel.

## Architecture

Three decoupled components:

- **Scheduled Python job (GCP free-tier `e2-micro` VM + cron)** — runs on a cron schedule on an always-on Compute Engine VM. On each run it:
  1. Performs trading analysis and executes a trade on the **chameleon** Crypto.com account.
  2. Executes a DCA purchase on the **control** Crypto.com account.
  3. Writes all resulting transactions to Supabase.
  4. Posts an announcement to the public Telegram channel linking to the dashboard.
- **SvelteKit dashboard (Vercel, free tier)** — public, read-only. Reads from Supabase and displays transactions for both accounts. Visitors can interact with visual filters (time ranges, account selector, cuts) but cannot mutate data. REFER TO `dashboard_plan.md`.
- **Supabase (free tier)** — shared persistence layer. Row Level Security configured so that the anon/public role has read-only access; writes go through a service role used only by the scheduled job. REFER to `database_instructions.md`

### Why a GCP VM + cron (and not GitHub Actions or Vercel cron)
The original plan was GitHub Actions: Python natively, generous free minutes, easy secrets, no need to manage a server. Vercel cron was rejected up front because the Hobby tier caps serverless execution time and adds Python cold-start friction.

The blocker that ruled both out: **Crypto.com Exchange requires IP whitelisting on trading API keys** — there is no opt-out for trade scope, only for withdrawals. GitHub-hosted runners egress from rotating Azure IP ranges (thousands of CIDRs, refreshed weekly), and Vercel/Lambda from rotating AWS ranges. Neither can provide a stable egress IP without a paid proxy or self-hosted runner.

GCP's Always Free tier includes one `e2-micro` Compute Engine VM (in `us-west1`, `us-central1`, or `us-east1`) with a reserved external IPv4 address that is free while attached to a running VM. That IP is what we whitelist at Crypto.com — single IP, both accounts. `cron` on the VM is the smallest possible scheduler: no hosted-runner daemon, no proxy plumbing, no YAML, just a crontab entry pointing at the Python script.

## Repository layout (intended)
- `cdc.py` — Crypto.com Exchange API wrapper (existing).
- `/scripts` or similar — Python entry points invoked by the scheduled job. Architecture (single script vs. many) is an open decision.
- `/webapp` — SvelteKit dashboard deployed to Vercel.
- VM-side scheduling (crontab, optional systemd unit) lives **on the VM**, not in this repo. The repo is `git pull`ed onto the VM; cron points at scripts inside it.

## Environments & secrets
- **No sandbox available.** Crypto.com restricted its UAT environment to institutional accounts, so all development runs against the live API. Read-only endpoints (`get_user_balance`, market data) are safe to call freely. For trading paths, use the smallest notional the instrument allows, or gate the actual `create_market_order` call behind a dry-run flag while iterating.
- Two sets of Crypto.com API credentials: one for the **chameleon** account, one for the **control** account. Both keys must whitelist the VM's reserved external IP. Disable withdraw permissions on both keys — the bot never withdraws.
- Secrets for the Python job live in a `.env` file on the VM (read by `python-dotenv`), never committed. Dashboard env vars live in Vercel.

## Guiding principles

### NotebookLM first coding for Crypto.com Exchange
Use the notebookLM skill to query https://notebooklm.google.com/notebook/01c07af5-acf8-4024-82ce-bd4a57eb1fd6 to ensure latest docs are being used.

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
