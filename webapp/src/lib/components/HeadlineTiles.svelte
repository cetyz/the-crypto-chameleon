<script lang="ts">
  import type { AccountSummary } from '$lib/types';
  import Sparkline from './Sparkline.svelte';

  let { summaries }: { summaries: AccountSummary[] } = $props();

  function fmtUSD(n: number) {
    return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  }
  function fmtBTC(n: number) {
    return `${n.toFixed(4)} BTC`;
  }
  function fmtPct(n: number) {
    const sign = n >= 0 ? '+' : '';
    return `${sign}${n.toFixed(2)}%`;
  }
  function tileColor(key: string) {
    return key === 'chameleon' ? '#10b981' : '#6366f1';
  }
</script>

<section class="mx-auto max-w-6xl px-4 grid gap-4 md:grid-cols-2">
  {#each summaries as s (s.account.key)}
    <div class="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-400">
          {s.account.label}
        </h2>
        <span class="h-2 w-2 rounded-full" style="background-color: {tileColor(s.account.key)}"></span>
      </div>
      <div class="mt-2 text-4xl font-bold" style="color: {tileColor(s.account.key)}">
        {fmtPct(s.pct_return)}
      </div>
      <div class="mt-3 flex items-end justify-between gap-4">
        <div class="space-y-3">
          <div>
            <div class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Portfolio Value</div>
            <div class="text-sm mt-0.5">
              <span class="font-medium">{fmtUSD(s.portfolio_usd)}</span>
              <span class="text-slate-500"> | </span>
              <span>{fmtBTC(s.portfolio_btc)}</span>
            </div>
          </div>
          <div>
            <div class="text-xs font-semibold uppercase tracking-wider text-slate-400">Portfolio Breakdown</div>
            <div class="text-sm mt-0.5">
              <span class="font-medium">{fmtUSD(s.cash_usd)}</span>
              <span class="text-slate-500"> | </span>
              <span>{fmtBTC(s.btc_qty)}</span>
            </div>
          </div>
          <div class="text-sm text-slate-400">Capital invested: {fmtUSD(s.account.starting_capital_usd)}</div>
        </div>
        <Sparkline values={s.sparkline} color={tileColor(s.account.key)} />
      </div>
    </div>
  {/each}
</section>
