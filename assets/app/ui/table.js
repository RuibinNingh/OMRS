/**
 * 表格：table({columns:[{key,label,num,render}], rows, rowKey, selected:[key], hover:key, empty, caption, stack})
 * 表头固定；行三态（悬停、选中、行内操作显示）；stack:true 时窄屏（≤760px）降级为卡片列表（D4），不横向截断。
 * render(row) 须返回 html`` 结果或纯文本。
 */
import { html, cls } from '../core/html.js';

export function table({ columns = [], rows = [], rowKey = 'id', selected = [], hover, empty = '', caption, stack = false } = {}) {
  const chosen = new Set(selected.map(String));
  const body = rows.length ? rows.map(row => {
    const key = String(row[rowKey]);
    return html`<tr data-key="${key}"${chosen.has(key) ? html` aria-selected="true"` : ''}${hover != null && String(hover) === key ? html` class="is-hover"` : ''}>${columns.map(col => html`<td data-label="${col.label}"${col.num ? html` class="is-num"` : ''}>${col.render ? col.render(row) : row[col.key]}</td>`)}</tr>`;
  }) : html`<tr class="ui-table__empty"><td colspan="${columns.length || 1}">${empty}</td></tr>`;
  return html`<div class="ui-table-wrap"><table class="${cls('ui-table', stack && 'ui-table--stack')}">${caption ? html`<caption>${caption}</caption>` : ''}<thead><tr>${columns.map(col => html`<th scope="col"${col.num ? html` class="is-num"` : ''}>${col.label}</th>`)}</tr></thead><tbody>${body}</tbody></table></div>`;
}
