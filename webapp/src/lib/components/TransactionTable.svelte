<script lang="ts">
  import type { Transaction } from '$lib/types';

  let {
    title,
    transactions,
    isChameleon = false
  }: { title: string; transactions: Transaction[]; isChameleon?: boolean } = $props();

  const PAGE = 8;
  let visible = $state(PAGE);
  const shown = $derived(transactions.slice(0, visible));

  function fmtDate(iso: string) {
    return new Date(iso).toLocaleDateString(undefined, { year: '2-digit', month: 'short', day: 'numeric' });
  }
  function fmtUSD(n: number) {
    return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  }
</script>

<div>
  <div class="flex items-baseline justify-between pb-3">
    <h3
      class="serif text-lg inline-block pb-1 {isChameleon ? 'border-b border-chameleon' : ''}"
    >
      {title}
    </h3>
    <span class="label">{transactions.length} trades</span>
  </div>
  <table class="w-full text-sm border-t hairline">
    <thead>
      <tr class="border-b hairline">
        <th class="text-left py-3 pr-3 label font-medium">Date</th>
        <th class="text-left py-3 pr-3 label font-medium">Side</th>
        <th class="text-left py-3 pr-3 label font-medium">Asset</th>
        <th class="text-right py-3 pr-3 label font-medium">Amount</th>
        <th class="text-right py-3 pr-3 label font-medium">Price</th>
        <th class="text-right py-3 label font-medium">USD</th>
      </tr>
    </thead>
    <tbody>
      {#each shown as tx (tx.id)}
        <tr class="border-b hairline">
          <td class="py-3 pr-3 fig text-ink-faded">{fmtDate(tx.timestamp)}</td>
          <td class="py-3 pr-3 uppercase text-xs tracking-wider" style="letter-spacing: 0.06em;">
            {tx.side}
          </td>
          <td class="py-3 pr-3">{tx.asset}</td>
          <td class="py-3 pr-3 text-right fig">{tx.amount.toFixed(6)}</td>
          <td class="py-3 pr-3 text-right fig text-ink-faded">{fmtUSD(tx.price_usd)}</td>
          <td class="py-3 text-right fig">{fmtUSD(tx.amount * tx.price_usd)}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  {#if visible < transactions.length}
    <div class="pt-4">
      <button class="toggle" onclick={() => (visible += PAGE)}>Load more</button>
    </div>
  {/if}
</div>
