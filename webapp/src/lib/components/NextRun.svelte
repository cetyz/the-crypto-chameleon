<script lang="ts">
  import { onDestroy } from 'svelte';

  let { scheduledAt, lastUpdated }: { scheduledAt: string; lastUpdated: string } = $props();

  let now = $state(Date.now());
  const target = $derived(new Date(scheduledAt).getTime());
  const interval = setInterval(() => (now = Date.now()), 1000);
  onDestroy(() => clearInterval(interval));

  const remaining = $derived(Math.max(0, target - now));
  const d = $derived(Math.floor(remaining / 86_400_000));
  const h = $derived(Math.floor((remaining % 86_400_000) / 3_600_000));
  const m = $derived(Math.floor((remaining % 3_600_000) / 60_000));
  const s = $derived(Math.floor((remaining % 60_000) / 1000));
  const lastStr = $derived(new Date(lastUpdated).toLocaleString());
</script>

<section class="mx-auto max-w-6xl px-4">
  <div class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-800 bg-slate-900/50 px-4 py-3 text-sm">
    <div>
      <span class="text-slate-400">Next scheduled run in </span>
      <span class="font-mono text-white">{d}d {h}h {m}m {s}s</span>
    </div>
    <div class="text-slate-500 text-xs">Last updated {lastStr}</div>
  </div>
</section>
