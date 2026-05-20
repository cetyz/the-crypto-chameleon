<script lang="ts">
  let { lastUpdated }: { lastUpdated: string } = $props();
  const formatted = $derived(new Date(lastUpdated).toLocaleString());
</script>

<footer class="border-t hairline mt-16">
  <div class="mx-auto max-w-5xl px-5 sm:px-8 py-8 text-sm text-ink-faded space-y-2" style="max-width: 65ch;">
    <p>Not financial advice. Two real accounts, every trade on the table.</p>
    <p class="text-xs">Last updated <span class="fig">{formatted}</span>.</p>
  </div>
</footer>
