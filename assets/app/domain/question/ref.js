/** 稳定题目引用：在打开对话框或发起异步操作前冻结身份，UID 仅用于展示。 */
import { allItems } from '../items.js';

export const questionKey = item => item?.question_id || item?.uid || '';
export function questionItem(value, items = allItems()) {
  if (value && typeof value === 'object') {
    if (value.uid || !value.question_id) return value;
    return items.find(item => item.question_id === value.question_id) || value;
  }
  const key = String(value || '');
  return items.find(item => item.question_id === key) || items.find(item => item.uid === key) || null;
}
export function questionRef(value, items = allItems()) {
  const item = questionItem(value, items);
  if (!item?.question_id) throw new Error('题目身份不可确认，请刷新题库后重试');
  return Object.freeze({ question_id: item.question_id });
}
export function questionRefs(values, items = allItems()) {
  const seen = new Set();
  return (values || []).map(value => questionRef(value, items)).filter(ref => !seen.has(ref.question_id) && seen.add(ref.question_id));
}
