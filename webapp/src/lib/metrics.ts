import type { AccountKey, EquityPoint, ValuationSnapshot } from './types';

export function percentReturn(currentUSD: number, startingCapital: number): number {
  if (startingCapital === 0) return 0;
  return ((currentUSD - startingCapital) / startingCapital) * 100;
}

export function buildEquitySeriesFromSnapshots(
  snapshots: ValuationSnapshot[],
  starting: Record<AccountKey, number>
): EquityPoint[] {
  const byTime = new Map<string, ValuationSnapshot[]>();
  for (const s of snapshots) {
    const arr = byTime.get(s.snapshot_at);
    if (arr) arr.push(s);
    else byTime.set(s.snapshot_at, [s]);
  }
  const timestamps = Array.from(byTime.keys());

  let chamUSD = starting.chameleon;
  let ctrlUSD = starting.control;
  let chamBTC = 0;
  let ctrlBTC = 0;

  return timestamps.map((timestamp) => {
    for (const s of byTime.get(timestamp)!) {
      const usd = s.total_value_usd;
      const btc = s.btc_price_usd > 0 ? usd / s.btc_price_usd : 0;
      if (s.account === 'chameleon') {
        chamUSD = usd;
        chamBTC = btc;
      } else {
        ctrlUSD = usd;
        ctrlBTC = btc;
      }
    }
    return {
      timestamp,
      chameleon_usd: chamUSD,
      control_usd: ctrlUSD,
      chameleon_btc: chamBTC,
      control_btc: ctrlBTC,
      chameleon_pct: percentReturn(chamUSD, starting.chameleon),
      control_pct: percentReturn(ctrlUSD, starting.control)
    };
  });
}
