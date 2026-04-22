import type {
  Account,
  AccountKey,
  AccountSummary,
  EquityPoint,
  NextRun,
  Transaction
} from '$lib/types';
import {
  buildEquitySeries,
  percentReturn,
  portfolioValueBTC,
  portfolioValueUSD,
  type PriceMap
} from '$lib/metrics';
import accountsFixture from './fixtures/accounts.json';
import transactionsFixture from './fixtures/transactions.json';
import pricesFixture from './fixtures/prices.json';
import nextRunFixture from './fixtures/next_run.json';

const accounts = accountsFixture as Account[];
const transactions = transactionsFixture as Transaction[];
const prices = pricesFixture as PriceMap;
const nextRun = nextRunFixture as NextRun;

const SPARKLINE_POINTS = 12;

async function delay<T>(value: T): Promise<T> {
  return value;
}

export async function getAccounts(): Promise<Account[]> {
  return delay(accounts);
}

export async function getTransactions(account?: AccountKey): Promise<Transaction[]> {
  const rows = account ? transactions.filter((t) => t.account === account) : transactions;
  return delay([...rows].sort((a, b) => b.timestamp.localeCompare(a.timestamp)));
}

export async function getEquityCurve(): Promise<EquityPoint[]> {
  const starting = {
    chameleon: accounts.find((a) => a.key === 'chameleon')!.starting_capital_usd,
    control: accounts.find((a) => a.key === 'control')!.starting_capital_usd
  };
  return delay(buildEquitySeries(transactions, starting, prices));
}

export async function getNextRun(): Promise<NextRun> {
  return delay(nextRun);
}

export async function getAccountSummaries(): Promise<AccountSummary[]> {
  const curve = await getEquityCurve();
  const tailStart = Math.max(0, curve.length - SPARKLINE_POINTS);
  return accounts.map((account) => {
    const portfolio_usd = portfolioValueUSD(
      account.key,
      transactions,
      account.starting_capital_usd,
      prices
    );
    const portfolio_btc = portfolioValueBTC(portfolio_usd, prices);
    const pct_return = percentReturn(portfolio_usd, account.starting_capital_usd);
    const key = account.key === 'chameleon' ? 'chameleon_pct' : 'control_pct';
    const sparkline = curve.slice(tailStart).map((p) => p[key] as number);
    return { account, portfolio_usd, portfolio_btc, pct_return, sparkline };
  });
}
