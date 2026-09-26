/** Ledger 历史：共享投影、读取和修正请求。 */
import { get, post } from '../core/api.js';
import { historyRows, historyReviewBatchStats, historyCommitFamily,
  historyNodeTitle, formatLedgerTime } from './history-model.js';

export * from './history-model.js';

let publish = () => {};
export function connectHistory({ emit } = {}) {
  publish = typeof emit === 'function' ? emit : () => {};
}
export function notifyHistoryChanged(source = '') { publish('history:changed', { source }); }

export function ledgerTimeZone() {
  try { return localStorage.getItem('omrs-ledger-time-zone') || 'local'; }
  catch { return 'local'; }
}

/** 拉最近 limit 条提交（含服务端算好的撤销状态）。返回 { ok, commits, retraction, error }。 */
export async function fetchHistory(limit = 240) {
  const res = await get(`/api/history?limit=${limit}`);
  if (!res.ok) return { ok: false, commits: [], retraction: null, error: res.error?.message || '未知错误' };
  return { ok: true, commits: res.data?.commits || [], retraction: res.data?.retraction_state || null, error: '' };
}
export const fetchRecent = (limit = 40) => fetchHistory(limit);

export async function postHistoryCorrection(path, payload) {
  const res = await post(path, payload);
  return { ok: res.ok, data: res.data, error: res.ok ? '' : res.error?.message || '未知错误' };
}

/** 最近动态的行：去掉修正类节点与已撤销节点，按 seq 倒序取前 limit 条。时间按设置里的 Ledger 时区显示。 */
export function projectRecent(commits, retraction, limit = 4, zone = ledgerTimeZone()) {
  const list = Array.isArray(commits) ? commits : [];
  const { main, rs } = historyRows(list, retraction, 'desc');
  return main.slice(0, limit).map(row => {
      const stats = row.commit_type === 'review.batch_submit' ? historyReviewBatchStats(row, rs) : null;
      const time = formatLedgerTime(row.created_at, zone).slice(0, 16);
      return {
        id: String(row.commit_id || row.seq),
        family: historyCommitFamily(row.commit_type),
        title: historyNodeTitle(row, rs),
        meta: `${row.commit_id || ''} · seq ${row.seq ?? ''}`,
        chip: stats ? `${stats.correct} 对 · ${stats.wrong} 错` : '',
        time: time || 'GENESIS',
      };
  });
}
