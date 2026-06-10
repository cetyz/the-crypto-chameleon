import type {
  Account,
  AccountKey,
  AccountSummary,
  EquityPoint,
  NextRun,
  Transaction,
  ValuationSnapshot
} from '$lib/types';
import { buildEquitySeriesFromSnapshots, percentReturn } from '$lib/metrics';
import { supabase } from '$lib/supabase';

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

export async function getLatestSnapshotAt(): Promise<string> {
  const { data, error } = await supabase
    .from('valuation_snapshots')
    .select('snapshot_at')
    .order('snapshot_at', { ascending: false })
    .limit(1)
    .maybeSingle();
  if (error) throw error;
  return data?.snapshot_at ?? '';
}

export async function getNextRun(): Promise<NextRun> {
  const [pending, latest] = await Promise.all([
    supabase
      .from('runs')
      .select('scheduled_for')
      .eq('status', 'pending')
      .gte('scheduled_for', new Date().toISOString())
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

function startingMap(accounts: Account[]): Record<AccountKey, number> {
  return {
    chameleon: accounts.find((a) => a.key === 'chameleon')?.starting_capital_usd ?? 0,
    control: accounts.find((a) => a.key === 'control')?.starting_capital_usd ?? 0
  };
}

function mapSnapshotRow(row: {
  account: string;
  snapshot_at: string;
  btc_qty: number | string;
  stable_usd: number | string;
  btc_price_usd: number | string;
  total_value_usd: number | string;
}): ValuationSnapshot {
  return {
    account: row.account as AccountKey,
    snapshot_at: row.snapshot_at,
    btc_qty: Number(row.btc_qty),
    stable_usd: Number(row.stable_usd),
    btc_price_usd: Number(row.btc_price_usd),
    total_value_usd: Number(row.total_value_usd)
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
    result[key] = mapSnapshotRow(row);
  }
  return result;
}

export async function getSnapshotHistory(): Promise<ValuationSnapshot[]> {
  const { data, error } = await supabase
    .from('valuation_snapshots')
    .select('account, snapshot_at, btc_qty, stable_usd, btc_price_usd, total_value_usd')
    .order('snapshot_at', { ascending: true });
  if (error) throw error;
  return (data ?? []).map(mapSnapshotRow);
}

export async function getEquityCurve(): Promise<EquityPoint[]> {
  const [accounts, history] = await Promise.all([getAccounts(), getSnapshotHistory()]);
  return buildEquitySeriesFromSnapshots(history, startingMap(accounts));
}

export async function getAccountSummaries(): Promise<AccountSummary[]> {
  const [accounts, snapshots, history] = await Promise.all([
    getAccounts(),
    getLatestSnapshots(),
    getSnapshotHistory()
  ]);
  const curve = buildEquitySeriesFromSnapshots(history, startingMap(accounts));
  const tailStart = Math.max(0, curve.length - SPARKLINE_POINTS);

  return accounts.map((account) => {
    const snapshot = snapshots[account.key];
    const portfolio_usd = snapshot ? snapshot.total_value_usd : account.starting_capital_usd;
    const cash_usd = snapshot ? snapshot.stable_usd : account.starting_capital_usd;
    const btc_qty = snapshot ? snapshot.btc_qty : 0;
    const portfolio_btc =
      snapshot && snapshot.btc_price_usd > 0 ? portfolio_usd / snapshot.btc_price_usd : 0;
    const pct_return = percentReturn(portfolio_usd, account.starting_capital_usd);
    const key = account.key === 'chameleon' ? 'chameleon_pct' : 'control_pct';
    const sparkline = curve.slice(tailStart).map((p) => p[key] as number);
    return { account, portfolio_usd, portfolio_btc, cash_usd, btc_qty, pct_return, sparkline };
  });
}
