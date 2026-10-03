/** 连续草稿审核使用公共待办身份，同时保留原生队列读取失败。 */
import { get } from '../../core/api.js';
import { fetchReviewItems } from '../../domain/ai-review.js';
import { sortDraftQueue } from './drafts-state.js';

export function reviewFilters(s) {
  const filters = { view: s.view, source: s.source, type: s.type, status: s.view === 'records' ? s.status : '' };
  if (s.range) { const start = new Date(); start.setHours(0, 0, 0, 0); start.setDate(start.getDate() - Number(s.range) + 1); filters.from = start.toISOString(); }
  return filters;
}
export async function pendingDraftQueue(filters, request = fetchReviewItems) {
  if (filters.type && filters.type !== 'draft') return { ok: true, items: [] };
  const items = []; let offset = 0, out;
  do {
    out = await request({ ...filters, view: 'pending', type: 'draft', status: '', limit: 100, offset });
    if (!out.ok) return out;
    items.push(...(out.items || []).filter(row => row.kind === 'draft')); offset = out.next_offset || 0;
  } while (out.has_more && offset > 0);
  return { ok: true, items };
}
export async function readDraftQueue(filter, filterQueue, request = get) {
  const result = await request(`/api/drafts/list?status=${filter}&limit=500`);
  if (!result.ok || !Array.isArray(result.data?.drafts)) return result;
  let rows = result.data.drafts.filter(row => filter === 'pending' ? ['cropping', 'review'].includes(row.status) : row.status === filter);
  if (filter === 'pending' && filterQueue) {
    const allowed = await filterQueue();
    if (!allowed.ok) return { ok: false, error: { message: allowed.error || '公共草稿队列读取失败' } };
    rows = allowed.items;
  }
  return { ...result, data: { ...result.data, drafts: sortDraftQueue(rows) } };
}
