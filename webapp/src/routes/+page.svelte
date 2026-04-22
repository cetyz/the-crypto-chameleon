<script lang="ts">
  import Header from '$lib/components/Header.svelte';
  import HeadlineTiles from '$lib/components/HeadlineTiles.svelte';
  import EquityChart from '$lib/components/EquityChart.svelte';
  import NextRun from '$lib/components/NextRun.svelte';
  import TransactionTable from '$lib/components/TransactionTable.svelte';
  import Footer from '$lib/components/Footer.svelte';

  let { data } = $props();
</script>

<Header />

<main class="py-6 space-y-6">
  <HeadlineTiles summaries={data.summaries} />
  <EquityChart points={data.equity} />
  <NextRun scheduledAt={data.nextRun.scheduled_at} lastUpdated={data.nextRun.last_updated} />

  <section class="mx-auto max-w-6xl px-4 grid gap-4 md:grid-cols-2">
    <TransactionTable title="Chameleon" transactions={data.chameleonTx} accent="#10b981" />
    <TransactionTable title="Control" transactions={data.controlTx} accent="#6366f1" />
  </section>
</main>

<Footer lastUpdated={data.nextRun.last_updated} />
