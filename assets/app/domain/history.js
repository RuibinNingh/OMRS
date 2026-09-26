/**
 * 历史 Ledger（过渡期适配器）：仪表盘「最近动态」取数与投影。节点标题、撤销状态、修正类型的判定仍是旧 history.js 的函数，
 * 这里只转调；历史记录页迁到 features/history（P6 第 2 轮）时实现搬进来，仪表盘不动。
 */
import { get } from '../core/api.js';

const g = globalThis;
const fn = name => (typeof g[name] === 'function' ? g[name] : null);
const num = value => { const n = Number(value); return Number.isFinite(n) ? n : 0; };

/** 拉最近 limit 条提交（含服务端算好的撤销状态）。返回 { ok, commits, retraction, error }。 */
export async function fetchRecent(limit = 40) {
  const res = await get(`/api/history?limit=${limit}`);
  if (!res.ok) return { ok: false, commits: [], retraction: null, error: res.error?.message || '未知错误' };
  return { ok: true, commits: res.data?.commits || [], retraction: res.data?.retraction_state || null, error: '' };
}

/** 最近动态的行：去掉修正类节点与已撤销节点，按 seq 倒序取前 limit 条。时间按设置里的 Ledger 时区显示。 */
export function projectRecent(commits, retraction, limit = 4) {
  const list = Array.isArray(commits) ? commits : [];
  const rs = fn('normalizeHistoryRetractionState')?.(retraction)
    || fn('historyRetractionState')?.(list) || { retractedSessions: new Set(), retractedReviews: new Set() };
  const corrected = fn('isHistoryCorrection') || (() => false);
  const retracted = fn('isNodeRetracted') || (() => false);
  return [...list].sort((a, b) => num(b.seq) - num(a.seq))
    .filter(row => !corrected(row) && !retracted(row, rs)).slice(0, limit).map(row => {
      const stats = row.commit_type === 'review.batch_submit' ? fn('historyReviewBatchStats')?.(row, rs) : null;
      const time = (fn('formatLedgerTime')?.(row.created_at) || String(row.created_at || '')).slice(0, 16);
      return {
        id: String(row.commit_id || row.seq),
        family: fn('historyCommitFamily')?.(row.commit_type) || 'system',
        title: fn('historyNodeTitle')?.(row, rs) || row.summary || row.commit_type || '',
        meta: `${row.commit_id || ''} · seq ${row.seq ?? ''}`,
        chip: stats ? `${stats.correct} 对 · ${stats.wrong} 错` : '',
        time: time || 'GENESIS',
      };
    });
}
