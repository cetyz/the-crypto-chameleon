<script lang="ts">
  import type { AccountKey, EquityPoint, Transaction } from '$lib/types';
  import { LayerCake, Svg } from 'layercake';
  import { scaleTime } from 'd3-scale';

  let {
    points,
    chameleonTx = [],
    controlTx = []
  }: { points: EquityPoint[]; chameleonTx?: Transaction[]; controlTx?: Transaction[] } = $props();

  type EquityKey = 'chameleon_usd' | 'control_usd' | 'chameleon_btc' | 'control_btc';

  type Range = '1M' | '3M' | 'All';
  type Unit = 'USD' | 'BTC';
  let range = $state<Range>('All');
  let unit = $state<Unit>('USD');

  // Shared between LayerCake's coordinate space and the HTML tooltip overlay.
  const PAD = { top: 10, right: 4, bottom: 24, left: 72 };
  let hovered = $state<{ x: number; y: number; m: Marker } | null>(null);

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
    key: EquityKey
  ) {
    return data
      .map((d, i) => {
        const x = xScale(new Date(d.timestamp));
        const y = yScale(d[key]);
        return `${i === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(' ');
  }

  // Linearly interpolate an account's value series at an arbitrary trade time so the
  // marker sits on the line. Returns null when the trade is outside the visible x-range.
  function valueAt(series: EquityPoint[], t: number, key: EquityKey): number | null {
    if (series.length === 0) return null;
    const t0 = new Date(series[0].timestamp).getTime();
    const tN = new Date(series[series.length - 1].timestamp).getTime();
    if (t < t0 || t > tN) return null;
    for (let i = 0; i < series.length - 1; i++) {
      const a = new Date(series[i].timestamp).getTime();
      const b = new Date(series[i + 1].timestamp).getTime();
      if (t >= a && t <= b) {
        const f = b === a ? 0 : (t - a) / (b - a);
        return series[i][key] + f * (series[i + 1][key] - series[i][key]);
      }
    }
    return series[series.length - 1][key];
  }

  type Marker = {
    t: number;
    value: number;
    side: 'buy' | 'sell';
    account: AccountKey;
    label: string;
  };

  const markers = $derived.by(() => {
    const out: Marker[] = [];
    const add = (txs: Transaction[], account: AccountKey, key: EquityKey) => {
      for (const tx of txs) {
        const t = new Date(tx.timestamp).getTime();
        const value = valueAt(filtered, t, key);
        if (value == null) continue;
        const name = account === 'chameleon' ? 'Chameleon' : 'Control';
        const date = new Date(tx.timestamp).toLocaleDateString('en-US', {
          month: 'short',
          day: 'numeric',
          year: 'numeric'
        });
        out.push({
          t,
          value,
          side: tx.side,
          account,
          label: `${name} · ${tx.side.toUpperCase()} · ${tx.amount} ${tx.asset} · ${date}`
        });
      }
    };
    add(chameleonTx, 'chameleon', chamKey);
    add(controlTx, 'control', ctrlKey);
    return out;
  });

  // Up triangle = buy, down triangle = sell.
  function triPath(cx: number, cy: number, up: boolean, r = 5) {
    return up
      ? `M ${cx} ${cy - r} L ${cx + r} ${cy + r * 0.8} L ${cx - r} ${cy + r * 0.8} Z`
      : `M ${cx} ${cy + r} L ${cx + r} ${cy - r * 0.8} L ${cx - r} ${cy - r * 0.8} Z`;
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
        <span class="text-ink-rule">·</span>
        <span class="flex items-center gap-1.5">
          <svg width="9" height="9" viewBox="-5 -5 10 10" aria-hidden="true">
            <path d="M 0 -4 L 4 3 L -4 3 Z" fill="var(--ink-faded)" />
          </svg>
          Buy
        </span>
        <span class="flex items-center gap-1.5">
          <svg width="9" height="9" viewBox="-5 -5 10 10" aria-hidden="true">
            <path d="M 0 4 L 4 -3 L -4 -3 Z" fill="var(--ink-faded)" />
          </svg>
          Sell
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

  <div class="relative h-80">
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
        padding={PAD}
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
            {#each markers as m (m.account + m.t + m.side)}
              {@const cx = xScale(new Date(m.t))}
              {@const cy = yScale(m.value)}
              <path
                d={triPath(cx, cy, m.side === 'buy')}
                style:fill={m.account === 'chameleon' ? 'var(--chameleon)' : 'var(--ink-faded)'}
                stroke="var(--ink-deep)"
                stroke-width="1"
              />
              <circle
                {cx}
                {cy}
                r="10"
                fill="transparent"
                role="img"
                aria-label={m.label}
                onmouseenter={() => (hovered = { x: cx, y: cy, m })}
                onmouseleave={() => (hovered = null)}
              />
            {/each}
          </Svg>
        {/snippet}
      </LayerCake>
      {#if hovered}
        <div
          class="pointer-events-none absolute z-10 whitespace-nowrap border px-2 py-1 text-xs"
          style="
            left: {PAD.left + hovered.x}px;
            top: {PAD.top + hovered.y}px;
            transform: translate(-50%, calc(-100% - 8px));
            background: var(--ink-deep);
            border-color: var(--ink-rule);
            color: var(--ink-settled);
          "
        >
          {hovered.m.label}
        </div>
      {/if}
    {:else}
      <div class="flex h-full items-center justify-center text-sm text-ink-faded">
        Not enough data in this range yet.
      </div>
    {/if}
  </div>
</section>
