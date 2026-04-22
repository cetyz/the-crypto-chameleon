import type { AccountKey, EquityPoint, PricePoint, Transaction } from './types';

export type PriceMap = Record<string, PricePoint[]>;

function priceAt(series: PricePoint[], tISO: string): number {
  const t = new Date(tISO).getTime();
  let last = series[0]?.usd ?? 0;
  for (const p of series) {
    if (new Date(p.timestamp).getTime() <= t) last = p.usd;
    else break;
  }
  return last;
}

export function currentPrice(prices: PriceMap, asset: string): number {
  const series = prices[asset];
  if (!series || series.length === 0) return asset === 'USD' ? 1 : 0;
  return series[series.length - 1].usd;
}

interface HoldingsState {
  cash_usd: number;
  assets: Record<string, number>;
}

function walk(
  txns: Transaction[],
  startingCapital: number,
  upToISO?: string
): HoldingsState {
  const state: HoldingsState = { cash_usd: startingCapital, assets: {} };
  const cutoff = upToISO ? new Date(upToISO).getTime() : Infinity;
  for (const tx of txns) {
    if (new Date(tx.timestamp).getTime() > cutoff) continue;
    const notional = tx.amount * tx.price_usd;
    const held = state.assets[tx.asset] ?? 0;
    if (tx.side === 'buy') {
      state.cash_usd -= notional;
      state.assets[tx.asset] = held + tx.amount;
    } else {
      state.cash_usd += notional;
      state.assets[tx.asset] = held - tx.amount;
    }
  }
  return state;
}

function valueUSD(state: HoldingsState, prices: PriceMap, atISO?: string): number {
  let total = state.cash_usd;
  for (const [asset, amount] of Object.entries(state.assets)) {
    if (amount === 0) continue;
    const series = prices[asset];
    const px = series ? (atISO ? priceAt(series, atISO) : series[series.length - 1].usd) : 0;
    total += amount * px;
  }
  return total;
}

export function portfolioValueUSD(
  account: AccountKey,
  transactions: Transaction[],
  startingCapital: number,
  prices: PriceMap
): number {
  const txns = transactions.filter((t) => t.account === account);
  return valueUSD(walk(txns, startingCapital), prices);
}

export function portfolioValueBTC(portfolioUSD: number, prices: PriceMap): number {
  const btc = currentPrice(prices, 'BTC');
  return btc === 0 ? 0 : portfolioUSD / btc;
}

export function percentReturn(currentUSD: number, startingCapital: number): number {
  if (startingCapital === 0) return 0;
  return ((currentUSD - startingCapital) / startingCapital) * 100;
}

export function buildEquitySeries(
  transactions: Transaction[],
  startingCapital: Record<AccountKey, number>,
  prices: PriceMap
): EquityPoint[] {
  const btcSeries = prices.BTC ?? [];
  return btcSeries.map((p) => {
    const chamState = walk(
      transactions.filter((t) => t.account === 'chameleon'),
      startingCapital.chameleon,
      p.timestamp
    );
    const ctrlState = walk(
      transactions.filter((t) => t.account === 'control'),
      startingCapital.control,
      p.timestamp
    );
    const chamUSD = valueUSD(chamState, prices, p.timestamp);
    const ctrlUSD = valueUSD(ctrlState, prices, p.timestamp);
    return {
      timestamp: p.timestamp,
      chameleon_usd: chamUSD,
      control_usd: ctrlUSD,
      chameleon_pct: percentReturn(chamUSD, startingCapital.chameleon),
      control_pct: percentReturn(ctrlUSD, startingCapital.control)
    };
  });
}
