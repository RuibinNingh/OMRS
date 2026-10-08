/** 操作卡的当前状态与数量摘要：执行结果只取真实回执，不用批准或旧工具状态推断。 */
export const REVIEW_LABELS = { pending_confirmation: '待你确认', approved: '已确认，等待执行', applying: '执行中', running: '执行中',
  applied: '已完成', rejected: '已拒绝', expired: '已过期', conflict: '需要重新核对', failed: '失败', failure: '失败',
  cancelled: '已中止', invalidated: '已失效', interrupted: '已中断', partial: '部分完成', unchanged: '无实际变更' };
export const isPending = item => item?.status === 'pending_confirmation' && !item.history_readonly;
export const inlineTools = new Set(['set_question_labels', 'create_review_session', 'record_feedback', 'move_question',
  'suspend_question', 'resume_question', 'create_category', 'set_knowledge_points']);
export const attention = item => ['partial', 'conflict', 'failed', 'failure', 'interrupted', 'expired', 'invalidated'].includes(item?.status);
export const reviewTone = item => isPending(item) || item?.status === 'partial' ? 'warning'
  : ['applied', 'unchanged'].includes(item?.status) ? 'success' : attention(item) ? 'danger' : 'neutral';
const same = row => JSON.stringify(row.before) === JSON.stringify(row.after);
export function reviewSummary(item) {
  const p = item?.preview || {}, r = item?.result || {};
  if (item?.tool === 'propose_label_plan') {
    const counts = ['applied', 'unchanged'].includes(item.status) ? r.counts : p.counts;
    if (counts) return `${['applied', 'unchanged'].includes(item.status) ? '已整理' : '将整理'} ${counts.changed} 道题 · ${counts.definitions} 项定义操作 · ${counts.uncertain || 0} 题待判断`;
  }
  if (item?.tool === 'set_question_labels') {
    if (['applied', 'unchanged', 'partial'].includes(item.status) && Array.isArray(r.changed) && Array.isArray(r.skipped)) {
      return `已修改 ${r.changed.length} 道 · ${r.skipped.length} 道无需变更${r.failed?.length ? ` · ${r.failed.length} 道未完成` : ''}`;
    }
    if (isPending(item) && Array.isArray(p.items)) {
      const unchanged = p.items.filter(same).length;
      return `涉及 ${p.items.length} 道题 · ${p.items.length - unchanged} 道将变更 · ${unchanged} 道无需变更`;
    }
  }
  if (item?.status === 'rejected') return '本次操作已拒绝，未执行写入。';
  if (item?.status === 'approved') return '确认已送达，正在等待实际执行。';
  if (['applying', 'running'].includes(item?.status)) return '正在执行，请稍候。';
  return r.message || r.summary || (r.session_id ? `复习计划 ${r.session_id} · ${r.count ?? '—'} 道题` : '')
    || (r.recorded != null ? `已记录 ${r.recorded} 条反馈` : '') || p.summary || p.title || p.message || item?.summary || '';
}
export function confirmLabel(item) {
  if (item?.tool === 'set_question_labels') {
    const rows = item.preview?.items || [], count = rows.filter(row => !same(row)).length;
    return count ? `确认修改 ${count} 道题` : '确认核对标记';
  }
  return ({ create_review_session: '确认创建计划', record_feedback: '确认记录反馈', move_question: '确认移动',
    suspend_question: '确认停用', resume_question: '确认恢复', create_category: '确认创建分类', set_knowledge_points: '确认修改知识点' })[item?.tool] || '确认执行';
}
