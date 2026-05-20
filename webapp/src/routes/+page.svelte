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

<main>
  <HeadlineTiles summaries={data.summaries} />
  <EquityChart points={data.equity} />
  <NextRun scheduledAt={data.nextRun.scheduled_at} lastUpdated={data.nextRun.last_updated} />

  <section class="mx-auto max-w-5xl px-5 sm:px-8 py-10">
    <h2 class="serif text-2xl mb-8">Transaction log</h2>
    <div class="grid gap-12 md:grid-cols-2 md:gap-10">
      <TransactionTable title="Chameleon" transactions={data.chameleonTx} isChameleon />
      <TransactionTable title="Control" transactions={data.controlTx} />
    </div>
  </section>
</main>

<Footer lastUpdated={data.nextRun.last_updated} />
