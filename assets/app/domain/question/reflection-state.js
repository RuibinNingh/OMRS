/** 按稳定题目身份保护草稿；保存失败和重新打开保持幂等编号。 */
import { requestId } from '../../core/request-id.js';
export class ReflectionDraft {
  constructor(questionId, storage = globalThis.sessionStorage) {
    this.key = `omrs-reflection-${questionId}`;
    this.storage = storage;
    this.value = { question_id: questionId, content_md: '', problem_ids: [], recurrence_of: '', occurred_at: '', editing_entry: null };
    this.id = '';
    try { const saved = JSON.parse(storage?.getItem(this.key) || 'null'); if (saved?.value?.question_id === questionId) { this.value = saved.value; this.id = saved.id || ''; } } catch { /* 草稿仅在当前窗口保留。 */ }
  }
  persist() { try { this.storage?.setItem(this.key, JSON.stringify({ value: this.value, id: this.id })); } catch { /* 内存草稿仍保留。 */ } }
  update(changes) { if (JSON.stringify(changes) !== JSON.stringify(Object.fromEntries(Object.keys(changes).map(k => [k, this.value[k]])))) this.id = ''; Object.assign(this.value, changes); this.persist(); }
  payload() { this.id ||= requestId(); this.persist(); return { ...this.value, request_id: this.id }; }
  dirty() { return !!this.value.content_md.trim(); }
  clear() { this.value = { ...this.value, content_md: '', problem_ids: [], recurrence_of: '', occurred_at: '', editing_entry: null }; this.id = ''; this.persist(); }
}
