<script lang="ts">
  import type { Transaction } from '$lib/types';

  let {
    title,
    transactions,
    accent
  }: { title: string; transactions: Transaction[]; accent: string } = $props();

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

<div class="rounded-xl border border-slate-800 bg-slate-900/50 overflow-hidden">
  <div class="flex items-center justify-between px-4 py-3 border-b border-slate-800">
    <h3 class="text-sm font-semibold uppercase tracking-wider" style="color: {accent}">
      {title}
    </h3>
    <span class="text-xs text-slate-500">{transactions.length} trades</span>
  </div>
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead class="text-xs text-slate-500 bg-slate-950/50">
        <tr>
          <th class="text-left px-3 py-2 font-medium">Date</th>
          <th class="text-left px-3 py-2 font-medium">Side</th>
          <th class="text-left px-3 py-2 font-medium">Asset</th>
          <th class="text-right px-3 py-2 font-medium">Amount</th>
          <th class="text-right px-3 py-2 font-medium">Price</th>
          <th class="text-right px-3 py-2 font-medium">USD Value</th>
        </tr>
      </thead>
      <tbody>
        {#each shown as tx (tx.id)}
          <tr class="border-t border-slate-800/50">
            <td class="px-3 py-2 text-slate-300">{fmtDate(tx.timestamp)}</td>
            <td class="px-3 py-2 {tx.side === 'buy' ? 'text-emerald-400' : 'text-rose-400'}">
              {tx.side}
            </td>
            <td class="px-3 py-2 text-slate-200">{tx.asset}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-200">{tx.amount.toFixed(6)}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-400">{fmtUSD(tx.price_usd)}</td>
            <td class="px-3 py-2 text-right font-mono text-slate-200">{fmtUSD(tx.amount * tx.price_usd)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if visible < transactions.length}
    <div class="border-t border-slate-800 p-3 text-center">
      <button
        class="text-xs text-slate-400 hover:text-white"
        onclick={() => (visible += PAGE)}
      >
        Load more
      </button>
    </div>
  {/if}
</div>
