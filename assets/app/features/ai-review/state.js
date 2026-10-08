import { isLabelPlan, labelPlanValues } from './label-plan-state.js';
/** 审核列表与人工修订的纯投影；读取工具不由前端名称猜测。 */
export const STATUS_LABELS = Object.freeze({ pending_confirmation: '待审核', pending: '待审核',
  review: '待审核', cropping: '待框选', applying: '执行中', running: '执行中',
  applied: '已执行', success: '已执行', done: '已入库', rejected: '已拒绝', discarded: '已丢弃',
  expired: '已过期', conflict: '有冲突', failure: '失败', failed: '失败', interrupted: '已中断',
  invalidated: '已失效', approved: '已批准，等待执行', cancelled: '已中止', partial: '部分成功', recorded: '已记录', unchanged: '无实际变更' });
export const reviewStatus = item => STATUS_LABELS[item?.status] || item?.status || '未知状态';
export const sourceLabel = item => ({ mcp: 'MCP', agent: 'AI 助手', legacy: '旧草稿' })[item?.source || item?.source_channel] || '来源未确认';
export const isPending = item => item?.kind === 'operation' && !item.history_readonly && ['pending_confirmation', 'pending'].includes(item.status);
export const itemLabel = item => item?.label || (item?.kind === 'draft' ? '新题草稿' : item?.tool) || 'AI 写操作';
export const itemSummary = item => item?.summary || item?.preview?.summary || '';
export const changesOf = item => Array.isArray(item?.preview?.changes) ? item.preview.changes
  : item?.preview && Object.hasOwn(item.preview, 'before') && Object.hasOwn(item.preview, 'after')
    ? [{ field: item.tool === 'set_knowledge_points' ? 'points' : 'content', label: item.preview.section || '知识点',
      before: item.preview.before, after: item.preview.after, kind: Array.isArray(item.preview.after) ? 'list' : 'text' }] : [];
export const FIELD_LABELS = Object.freeze({ question: '题目', answer: '答案解析', cause: '错因', note: '补充备注',
  question_text: '题目', answer_text: '答案解析', content: '修改内容', knowledge_points: '知识点', points: '知识点',
  labels: '人工标记', subject: '科目', category: '分类', difficulty: '难度', title: '标题', reason: '原因' });
export function editableValues(item) {
  if (isLabelPlan(item)) return labelPlanValues(item);
  const fields = Array.isArray(item?.editable_fields) ? item.editable_fields : [];
  const payload = item?.payload?.patch || item?.payload?.arguments || item?.payload?.args || item?.payload || {};
  return Object.fromEntries(fields.map(field => [field, payload[field] ?? changesOf(item).find(row => row.field === field)?.after ?? ''])
    .filter(([, value]) => value == null || typeof value !== 'object' || Array.isArray(value) && value.every(v => typeof v !== 'object')));
}
export function editInput(value) { return Array.isArray(value) ? value.join('，') : String(value ?? ''); }
export function editedValue(original, input, kind) {
  if (Array.isArray(original) || kind === 'list') return String(input).split(/[,，\n]/).map(text => text.trim()).filter(Boolean);
  if (typeof original === 'number' || kind === 'number') return input === '' ? '' : Number(input);
  return String(input);
}
export function changedPatch(original, edited) {
  return Object.fromEntries(Object.entries(edited).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(original[key])));
}
export function mergePage(existing, incoming) {
  return [...new Map([...existing, ...incoming].map(item => [`${item.kind}:${item.id}`, item])).values()];
}
