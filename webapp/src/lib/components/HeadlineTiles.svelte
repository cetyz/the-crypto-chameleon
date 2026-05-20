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
</script>

<section class="mx-auto max-w-5xl px-5 sm:px-8 grid grid-cols-1 md:grid-cols-2 md:divide-x divide-y md:divide-y-0 divide-ink-rule">
  {#each summaries as s (s.account.key)}
    {@const isCham = s.account.key === 'chameleon'}
    <div class="py-8 md:py-10 {isCham ? 'md:pr-10' : 'md:pl-10'}">
      <h2
        class="serif text-lg inline-block pb-1 {isCham ? 'border-b border-chameleon' : ''}"
      >
        {s.account.label}
      </h2>
      <div
        class="serif mt-4"
        style="font-size: clamp(2.75rem, 7vw, 4.25rem); line-height: 1.02; color: {isCham ? 'var(--chameleon)' : 'var(--ink-settled)'};"
      >
        <span class="fig">{fmtPct(s.pct_return)}</span>
      </div>

      <div class="mt-6 grid grid-cols-2 gap-x-6 gap-y-4">
        <div>
          <div class="label">Portfolio</div>
          <div class="mt-1 text-sm">
            <span class="fig">{fmtUSD(s.portfolio_usd)}</span>
            <span class="text-ink-faded"> · </span>
            <span class="fig text-ink-faded">{fmtBTC(s.portfolio_btc)}</span>
          </div>
        </div>
        <div>
          <div class="label">Capital invested</div>
          <div class="mt-1 text-sm fig">{fmtUSD(s.account.starting_capital_usd)}</div>
        </div>
        <div>
          <div class="label">Cash</div>
          <div class="mt-1 text-sm fig">{fmtUSD(s.cash_usd)}</div>
        </div>
        <div>
          <div class="label">BTC held</div>
          <div class="mt-1 text-sm fig">{fmtBTC(s.btc_qty)}</div>
        </div>
      </div>

      <div class="mt-6">
        <Sparkline values={s.sparkline} color={isCham ? 'var(--chameleon)' : 'var(--ink-rule)'} />
      </div>
    </div>
  {/each}
</section>
