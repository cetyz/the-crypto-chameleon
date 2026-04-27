import {
  getAccountSummaries,
  getEquityCurve,
  getNextRun,
  getTransactions
} from '$lib/data';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ fetch }) => {
  const [summaries, equity, nextRun, chameleonTx, controlTx] = await Promise.all([
    getAccountSummaries(fetch),
    getEquityCurve(fetch),
    getNextRun(),
    getTransactions('chameleon'),
    getTransactions('control')
  ]);
  return { summaries, equity, nextRun, chameleonTx, controlTx };
};
