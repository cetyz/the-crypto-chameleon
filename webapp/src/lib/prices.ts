import type { PricePoint } from './types';
import type { PriceMap } from './metrics';

const ENDPOINT = 'https://api.crypto.com/exchange/v1/public/get-candlestick';

interface Candle {
  t: number;
  c: string;
}

interface CandlestickResponse {
  code: number;
  result?: {
    data?: Candle[];
  };
}

async function fetchOne(
  asset: string,
  count: number,
  fetch: typeof globalThis.fetch
): Promise<PricePoint[]> {
  const instrument = `${asset}_USD`;
  const url = `${ENDPOINT}?instrument_name=${instrument}&timeframe=1D&count=${count}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return [];
    const body = (await res.json()) as CandlestickResponse;
    if (body.code !== 0 || !body.result?.data) return [];
    return body.result.data
      .map((c) => ({ timestamp: new Date(c.t).toISOString(), usd: Number(c.c) }))
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  } catch {
    return [];
  }
}

export async function fetchPrices(
  assets: string[],
  sinceISO: string,
  fetch: typeof globalThis.fetch
): Promise<PriceMap> {
  const daysSince = Math.ceil(
    (Date.now() - new Date(sinceISO).getTime()) / (1000 * 60 * 60 * 24)
  );
  const count = Math.max(1, Math.min(1000, daysSince + 2));

  const targets = assets.filter((a) => a !== 'USD');
  const series = await Promise.all(targets.map((a) => fetchOne(a, count, fetch)));

  const map: PriceMap = {};
  targets.forEach((asset, i) => {
    map[asset] = series[i];
  });
  return map;
}
