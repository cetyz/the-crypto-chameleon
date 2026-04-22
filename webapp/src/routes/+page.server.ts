import {
  getAccountSummaries,
  getEquityCurve,
  getNextRun,
  getTransactions
} from '$lib/data';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
  const [summaries, equity, nextRun, chameleonTx, controlTx] = await Promise.all([
    getAccountSummaries(),
    getEquityCurve(),
    getNextRun(),
    getTransactions('chameleon'),
    getTransactions('control')
  ]);
  return { summaries, equity, nextRun, chameleonTx, controlTx };
};
