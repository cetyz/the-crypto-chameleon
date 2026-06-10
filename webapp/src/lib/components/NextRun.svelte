<script lang="ts">
  import { onDestroy } from 'svelte';

  let {
    scheduledAt,
    lastRun,
    lastUpdated
  }: { scheduledAt: string; lastRun: string; lastUpdated: string } = $props();

  let now = $state(Date.now());
  const target = $derived(new Date(scheduledAt).getTime());
  const interval = setInterval(() => (now = Date.now()), 1000);
  onDestroy(() => clearInterval(interval));

  const remaining = $derived(Math.max(0, target - now));
  const d = $derived(Math.floor(remaining / 86_400_000));
  const h = $derived(Math.floor((remaining % 86_400_000) / 3_600_000));
  const m = $derived(Math.floor((remaining % 3_600_000) / 60_000));
  const s = $derived(Math.floor((remaining % 60_000) / 1000));
  const fmt = (iso: string) => {
    if (!iso) return '—';
    const d = new Date(iso);
    const date = d.toLocaleDateString('en-CA');
    const time = d
      .toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
      .toLowerCase();
    return `${date} · ${time}`;
  };
  const lastRunStr = $derived(fmt(lastRun));
  const lastUpdatedStr = $derived(fmt(lastUpdated));
</script>

<section class="mx-auto max-w-5xl px-5 sm:px-8 border-t border-b hairline">
  <div class="flex flex-wrap items-baseline justify-between gap-2 py-4">
    <div class="flex items-baseline gap-3">
      <span class="label">Next run in</span>
      <span class="fig text-base">{d}d {h}h {m}m {s}s</span>
    </div>
    <div class="flex items-baseline gap-3">
      <span class="label">Last run</span>
      <span class="fig text-xs text-ink-faded">{lastRunStr}</span>
    </div>
    <div class="flex items-baseline gap-3">
      <span class="label">Last updated</span>
      <span class="fig text-xs text-ink-faded">{lastUpdatedStr}</span>
    </div>
  </div>
</section>
