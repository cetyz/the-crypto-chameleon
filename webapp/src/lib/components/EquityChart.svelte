<script lang="ts">
  import type { EquityPoint } from '$lib/types';
  import { LayerCake, Svg } from 'layercake';
  import { scaleTime } from 'd3-scale';

  let { points }: { points: EquityPoint[] } = $props();

  type Range = '1M' | '3M' | 'All';
  type Unit = 'USD' | 'BTC';
  let range = $state<Range>('All');
  let unit = $state<Unit>('USD');

  const filtered = $derived.by(() => {
    if (range === 'All') return points;
    const days = range === '1M' ? 30 : 90;
    const cutoff = Date.now() - days * 86_400_000;
    return points.filter((p) => new Date(p.timestamp).getTime() >= cutoff);
  });

  const chamKey = $derived(unit === 'USD' ? 'chameleon_usd' : 'chameleon_btc');
  const ctrlKey = $derived(unit === 'USD' ? 'control_usd' : 'control_btc');

  const xGet = (d: EquityPoint) => new Date(d.timestamp);
  const yGet = (d: EquityPoint) => Math.max(d[chamKey], d[ctrlKey]);
  const yGetMin = (d: EquityPoint) => Math.min(d[chamKey], d[ctrlKey]);

  function fmtUSD(n: number) {
    return n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  }
  function fmtTick(n: number) {
    return unit === 'USD' ? fmtUSD(n) : `${n.toFixed(4)} BTC`;
  }

  function linePath(
    data: EquityPoint[],
    xScale: (d: Date) => number,
    yScale: (n: number) => number,
    key: 'chameleon_usd' | 'control_usd' | 'chameleon_btc' | 'control_btc'
  ) {
    return data
      .map((d, i) => {
        const x = xScale(new Date(d.timestamp));
        const y = yScale(d[key]);
        return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(' ');
  }
</script>

<section class="mx-auto max-w-6xl px-4">
  <div class="rounded-xl border border-slate-800 bg-slate-900/50 p-5">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
      <div>
        <h2 class="text-sm font-semibold uppercase tracking-wider text-slate-400">
          Portfolio value
        </h2>
        <div class="mt-1 flex items-center gap-4 text-xs">
          <span class="flex items-center gap-1.5"><span class="inline-block h-2 w-2 rounded-full bg-chameleon"></span>Chameleon</span>
          <span class="flex items-center gap-1.5"><span class="inline-block h-2 w-2 rounded-full bg-control"></span>Control</span>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <div class="flex rounded-lg border border-slate-800 overflow-hidden text-xs">
          {#each ['USD', 'BTC'] as u (u)}
            <button
              class="px-3 py-1.5 transition {unit === u ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}"
              onclick={() => (unit = u as Unit)}
            >
              {u}
            </button>
          {/each}
        </div>
        <div class="flex rounded-lg border border-slate-800 overflow-hidden text-xs">
          {#each ['1M', '3M', 'All'] as r (r)}
            <button
              class="px-3 py-1.5 transition {range === r ? 'bg-slate-700 text-white' : 'text-slate-400 hover:text-white'}"
              onclick={() => (range = r as Range)}
            >
              {r}
            </button>
          {/each}
        </div>
      </div>
    </div>

    <div class="h-72">
      {#if filtered.length > 1}
        <LayerCake
          data={filtered}
          x={xGet}
          y={yGet}
          yDomain={[
            Math.min(...filtered.map(yGetMin)) * 0.98,
            Math.max(...filtered.map(yGet)) * 1.02
          ]}
          xScale={scaleTime()}
          padding={{ top: 10, right: 10, bottom: 24, left: 64 }}
        >
          {#snippet children({ xScale, yScale }: { xScale: any; yScale: any })}
            <Svg>
              {@const ticks = yScale.ticks(5)}
              <g class="ticks-y">
                {#each ticks as t (t)}
                  <line x1="0" x2="100%" y1={yScale(t)} y2={yScale(t)} stroke="#1e293b" />
                  <text x="-6" y={yScale(t)} dy="0.32em" text-anchor="end" fill="#64748b" font-size="10">{fmtTick(t)}</text>
                {/each}
              </g>
              <path d={linePath(filtered, xScale, yScale, ctrlKey)} fill="none" stroke="#6366f1" stroke-width="2" />
              <path d={linePath(filtered, xScale, yScale, chamKey)} fill="none" stroke="#10b981" stroke-width="2" />
            </Svg>
          {/snippet}
        </LayerCake>
      {:else}
        <div class="flex h-full items-center justify-center text-sm text-slate-500">
          Not enough data points in this range yet.
        </div>
      {/if}
    </div>
  </div>
</section>
