<script lang="ts">
  let { lastUpdated }: { lastUpdated: string } = $props();
  const formatted = $derived(new Date(lastUpdated).toLocaleString());
</script>

<footer class="border-t border-slate-800 mt-12">
  <div class="mx-auto max-w-6xl px-4 py-6 text-xs text-slate-500 space-y-1">
    <p>Not financial advice. This dashboard tracks real trades for transparency and entertainment.</p>
    <p>Data source: Supabase (currently mocked). Last updated: {formatted}.</p>
  </div>
</footer>
