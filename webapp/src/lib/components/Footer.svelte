<script lang="ts">
  let { lastUpdated }: { lastUpdated: string } = $props();
  const formatted = $derived.by(() => {
    if (!lastUpdated) return '—';
    const d = new Date(lastUpdated);
    const date = d.toLocaleDateString('en-CA');
    const time = d
      .toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true })
      .toLowerCase();
    return `${date} · ${time}`;
  });
</script>

<footer class="border-t hairline mt-16">
  <div class="mx-auto max-w-5xl px-5 sm:px-8 py-8 text-sm text-ink-faded space-y-2" style="max-width: 65ch;">
    <p>Not financial advice. Two real accounts, every trade on the table.</p>
    <p class="text-xs">Last updated <span class="fig">{formatted}</span>.</p>
  </div>
</footer>
