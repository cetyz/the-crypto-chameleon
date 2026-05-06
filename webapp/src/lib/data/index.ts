import type {
  Account,
  AccountKey,
  AccountSummary,
  EquityPoint,
  NextRun,
  Transaction,
  ValuationSnapshot
} from '$lib/types';
import {
  buildEquitySeries,
  percentReturn,
  portfolioValueBTC,
  portfolioValueUSD
} from '$lib/metrics';
import { supabase } from '$lib/supabase';
import { fetchPrices } from '$lib/prices';

const SPARKLINE_POINTS = 12;

export async function getAccounts(): Promise<Account[]> {
  const [{ data: accRows, error: accErr }, { data: evtRows, error: evtErr }] = await Promise.all([
    supabase.from('accounts').select('key, label, inception_date'),
    supabase.from('capital_events').select('account, kind, amount_usd')
  ]);
  if (accErr) throw accErr;
  if (evtErr) throw evtErr;

  const netByAccount = new Map<string, number>();
  for (const e of evtRows ?? []) {
    const delta = e.kind === 'deposit' ? Number(e.amount_usd) : -Number(e.amount_usd);
    netByAccount.set(e.account, (netByAccount.get(e.account) ?? 0) + delta);
  }

  return (accRows ?? []).map((a) => ({
    key: a.key as AccountKey,
    label: a.label,
    inception_date: a.inception_date,
    starting_capital_usd: netByAccount.get(a.key) ?? 0
  }));
}

export async function getTransactions(account?: AccountKey): Promise<Transaction[]> {
  let query = supabase
    .from('transactions')
    .select('id, account, executed_at, side, asset, amount, price_usd')
    .order('executed_at', { ascending: false });
  if (account) query = query.eq('account', account);

  const { data, error } = await query;
  if (error) throw error;

  return (data ?? []).map((r) => ({
    id: r.id,
    account: r.account as AccountKey,
    timestamp: r.executed_at,
    side: r.side as 'buy' | 'sell',
    asset: r.asset,
    amount: Number(r.amount),
    price_usd: Number(r.price_usd)
  }));
}

export async function getNextRun(): Promise<NextRun> {
  const [pending, latest] = await Promise.all([
    supabase
      .from('runs')
      .select('scheduled_for')
      .eq('status', 'pending')
      .order('scheduled_for', { ascending: true })
      .limit(1)
      .maybeSingle(),
    supabase
      .from('runs')
      .select('finished_at')
      .eq('status', 'succeeded')
      .order('finished_at', { ascending: false })
      .limit(1)
      .maybeSingle()
  ]);
  if (pending.error) throw pending.error;
  if (latest.error) throw latest.error;

  return {
    scheduled_at: pending.data?.scheduled_for ?? '',
    last_updated: latest.data?.finished_at ?? ''
  };
}

function earliestInception(accounts: Account[]): string {
  if (accounts.length === 0) return new Date().toISOString();
  return accounts.map((a) => a.inception_date).sort()[0];
}

function startingMap(accounts: Account[]): Record<AccountKey, number> {
  return {
    chameleon: accounts.find((a) => a.key === 'chameleon')?.starting_capital_usd ?? 0,
    control: accounts.find((a) => a.key === 'control')?.starting_capital_usd ?? 0
  };
}

export async function getLatestSnapshots(): Promise<Record<AccountKey, ValuationSnapshot | null>> {
  const { data, error } = await supabase
    .from('valuation_snapshots')
    .select('account, snapshot_at, btc_qty, stable_usd, btc_price_usd, total_value_usd')
    .order('snapshot_at', { ascending: false });
  if (error) throw error;

  const result: Record<AccountKey, ValuationSnapshot | null> = {
    chameleon: null,
    control: null
  };
  for (const row of data ?? []) {
    const key = row.account as AccountKey;
    if (result[key] !== null) continue;
    result[key] = {
      account: key,
      snapshot_at: row.snapshot_at,
      btc_qty: Number(row.btc_qty),
      stable_usd: Number(row.stable_usd),
      btc_price_usd: Number(row.btc_price_usd),
      total_value_usd: Number(row.total_value_usd)
    };
  }
  return result;
}

export async function getEquityCurve(fetch: typeof globalThis.fetch): Promise<EquityPoint[]> {
  const [accounts, transactions] = await Promise.all([getAccounts(), getTransactions()]);
  const heldAssets = Array.from(new Set(transactions.map((t) => t.asset)));
  const prices = await fetchPrices(heldAssets, earliestInception(accounts), fetch);
  return buildEquitySeries(transactions, startingMap(accounts), prices);
}

export async function getAccountSummaries(
  fetch: typeof globalThis.fetch
): Promise<AccountSummary[]> {
  const [accounts, transactions, snapshots] = await Promise.all([
    getAccounts(),
    getTransactions(),
    getLatestSnapshots()
  ]);
  const heldAssets = Array.from(new Set(transactions.map((t) => t.asset)));
  const prices = await fetchPrices(heldAssets, earliestInception(accounts), fetch);
  const curve = buildEquitySeries(transactions, startingMap(accounts), prices);
  const tailStart = Math.max(0, curve.length - SPARKLINE_POINTS);

  return accounts.map((account) => {
    const snapshot = snapshots[account.key];
    const portfolio_usd =
      snapshot?.total_value_usd ??
      portfolioValueUSD(account.key, transactions, account.starting_capital_usd, prices);
    const portfolio_btc = portfolioValueBTC(portfolio_usd, prices);
    const pct_return = percentReturn(portfolio_usd, account.starting_capital_usd);
    const key = account.key === 'chameleon' ? 'chameleon_pct' : 'control_pct';
    const sparkline = curve.slice(tailStart).map((p) => p[key] as number);
    return { account, portfolio_usd, portfolio_btc, pct_return, sparkline };
  });
}
