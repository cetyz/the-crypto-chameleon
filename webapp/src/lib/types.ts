export type AccountKey = 'chameleon' | 'control';

export interface Account {
  key: AccountKey;
  label: string;
  inception_date: string;
  starting_capital_usd: number;
}

export interface Transaction {
  id: string;
  account: AccountKey;
  timestamp: string;
  side: 'buy' | 'sell';
  asset: string;
  amount: number;
  price_usd: number;
}

export interface PricePoint {
  timestamp: string;
  usd: number;
}

export interface EquityPoint {
  timestamp: string;
  chameleon_pct: number;
  control_pct: number;
  chameleon_usd: number;
  control_usd: number;
  chameleon_btc: number;
  control_btc: number;
}

export interface NextRun {
  scheduled_at: string;
  last_updated: string;
}

export interface ValuationSnapshot {
  account: AccountKey;
  snapshot_at: string;
  btc_qty: number;
  stable_usd: number;
  btc_price_usd: number;
  total_value_usd: number;
}

export interface AccountSummary {
  account: Account;
  portfolio_usd: number;
  portfolio_btc: number;
  pct_return: number;
  sparkline: number[];
}
