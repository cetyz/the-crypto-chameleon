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

<section class="mx-auto max-w-5xl px-5 sm:px-8 py-10">
  <div class="flex flex-wrap items-end justify-between gap-4 mb-6">
    <div>
      <h2 class="serif text-lg">Portfolio value over time</h2>
      <div class="mt-2 flex items-center gap-5 label">
        <span class="flex items-center gap-2">
          <span class="inline-block h-px w-5" style="background: var(--chameleon)"></span>
          Chameleon
        </span>
        <span class="flex items-center gap-2">
          <span class="inline-block h-px w-5 border-t border-dashed" style="border-color: var(--ink-faded)"></span>
          Control
        </span>
      </div>
    </div>
    <div class="flex items-center gap-5">
      <div class="flex items-center gap-3">
        {#each ['USD', 'BTC'] as u (u)}
          <button class="toggle" aria-pressed={unit === u} onclick={() => (unit = u as Unit)}>{u}</button>
        {/each}
      </div>
      <span class="text-ink-rule">·</span>
      <div class="flex items-center gap-3">
        {#each ['1M', '3M', 'All'] as r (r)}
          <button class="toggle" aria-pressed={range === r} onclick={() => (range = r as Range)}>{r}</button>
        {/each}
      </div>
    </div>
  </div>

  <div class="h-80">
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
        padding={{ top: 10, right: 4, bottom: 24, left: 72 }}
      >
        {#snippet children({ xScale, yScale }: { xScale: any; yScale: any })}
          <Svg>
            {@const ticks = yScale.ticks(5)}
            <g>
              {#each ticks as t (t)}
                <line x1="0" x2="100%" y1={yScale(t)} y2={yScale(t)} stroke="oklch(34% 0.012 60)" stroke-width="0.5" />
                <text
                  x="-10" y={yScale(t)} dy="0.32em"
                  text-anchor="end"
                  fill="oklch(68% 0.012 70)"
                  font-family="JetBrains Mono, ui-monospace, monospace"
                  font-size="10"
                  style="font-variant-numeric: tabular-nums"
                >{fmtTick(t)}</text>
              {/each}
            </g>
            <path
              d={linePath(filtered, xScale, yScale, ctrlKey)}
              fill="none"
              stroke="oklch(68% 0.012 70)"
              stroke-width="1.25"
              stroke-dasharray="3 3"
            />
            <path
              d={linePath(filtered, xScale, yScale, chamKey)}
              fill="none"
              stroke="oklch(74% 0.13 130)"
              stroke-width="1.75"
            />
          </Svg>
        {/snippet}
      </LayerCake>
    {:else}
      <div class="flex h-full items-center justify-center text-sm text-ink-faded">
        Not enough data in this range yet.
      </div>
    {/if}
  </div>
</section>
