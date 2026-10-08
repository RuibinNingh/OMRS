/** 轻量操作的影响与逐题回执；正文和完整草稿在原位详情中核对。 */
import { html } from '../../core/html.js';
import { ref, confirmOf, toolPreview } from './tools-view.js';
import { isPending } from './review-model.js';

const labels = values => (values || []).length ? values.map(value => html`<span class="ast-op__tag">${value}</span>`) : html`<span class="ast-op__muted">无标记</span>`;
export function inlinePreview(item, step) {
  const p = item.preview || {}, r = item.result || {};
  if (item.tool === 'set_question_labels') {
    const rows = isPending(item) ? p.items || [] : r.details || [];
    return html`<div class="ast-op__rows" aria-label="逐题标记变更">${rows.map(row => html`<div class="ast-op__row"><div>${ref(row.uid || row.question_id)}</div>
      <div class="ast-op__labels"><span class="ast-op__muted">${isPending(item) ? '当前' : '修改前'}</span>${labels(row.before)}<span aria-hidden="true">→</span>${labels(row.after)}
      ${JSON.stringify(row.before) === JSON.stringify(row.after) ? html`<span class="ast-op__muted">无需变更</span>` : ''}</div></div>`)}
      ${(r.skipped || []).map(uid => html`<div class="ast-op__row">${ref(uid)}<span class="ast-op__muted">标记无需变更</span></div>`)}
      ${(r.failed || []).map(row => html`<div class="ast-op__row is-error">${typeof row === 'string' ? row : row.uid || row.question_id}：${row.error || row.msg || '未完成'}</div>`)}</div>`;
  }
  const args = item.payload?.arguments || item.payload?.args || item.payload || step?.args || {};
  if (isPending(item)) {
    if (item.tool === 'create_review_session') return html`<div class="ast-op__rows">${(p.items || []).map(row => html`<div class="ast-op__row">${ref(row.uid)}<span class="ast-op__muted">来源：${row.source === 'proficiency' ? '熟练度' : '到期推荐'}</span></div>`)}</div>`;
    return confirmOf({ ...step, name: item.tool, args, preview: p }).body;
  }
  if (!['applied', 'unchanged', 'partial'].includes(item.status) || !Object.keys(r).length) return '';
  return html`${toolPreview({ ...step, name: item.tool, args, result: r })}
    ${(r.failed || []).map(row => html`<p class="ast-note is-error">${typeof row === 'string' ? row : row.uid || row.question_id}：${row.error || row.msg || '未完成'}</p>`)}`;
}
