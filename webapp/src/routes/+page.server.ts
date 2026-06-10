import {
  getAccountSummaries,
  getEquityCurve,
  getLatestSnapshotAt,
  getNextRun,
  getTransactions
} from '$lib/data';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
  const [summaries, equity, nextRun, lastSnapshotAt, chameleonTx, controlTx] = await Promise.all([
    getAccountSummaries(),
    getEquityCurve(),
    getNextRun(),
    getLatestSnapshotAt(),
    getTransactions('chameleon'),
    getTransactions('control')
  ]);
  return { summaries, equity, nextRun, lastSnapshotAt, chameleonTx, controlTx };
};
