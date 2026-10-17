/** 日志筛选与选择视图；日期使用服务端提供的上海更新日期。 */
import { html, each } from '../../core/html.js';
import { formatBytes } from './storage-state.js';

export function filterLogs(files, { q = '', kind = '', since = '', until = '' } = {}) {
  const query = q.trim().toLocaleLowerCase();
  return files.filter(file => (!kind || file.kind === kind)
    && (!query || file.name.toLocaleLowerCase().includes(query))
    && (!since || file.modified_day >= since) && (!until || file.modified_day <= until));
}

export const logsView = () => html`<div class="st-log-fields">
  <label>文件名<input class="ui-input" id="st-log-query" type="search" placeholder="搜索日志文件名" autocomplete="off"></label>
  <label>日志类型<select class="ui-select" id="st-log-kind"><option value="">全部类型</option><option value="runtime">运行日志</option><option value="ai">AI 请求日志</option></select></label>
  <label class="st-log-date">更新开始日期<input class="ui-input" id="st-log-since" type="date"></label>
  <label class="st-log-date">更新结束日期<input class="ui-input" id="st-log-until" type="date"></label>
</div>
<p class="st-log-hint">按文件的更新日期筛选（北京时间），导出保留完整文件。AI 请求日志包含请求与响应原文。</p>
<div class="st-log-toolbar">
  <label class="st-log-check"><input id="st-log-all" type="checkbox" disabled>全选筛选结果</label>
  <button class="ui-btn ui-btn--sm" type="button" id="st-log-refresh">刷新列表</button>
  <button class="ui-btn ui-btn--ghost ui-btn--sm" type="button" id="st-log-reset">重置筛选</button>
</div>
<div id="st-log-list" class="st-log-list" aria-label="可导出的日志" aria-busy="true"><p class="st-log-empty">正在读取日志列表…</p></div>
<div class="st-log-summary"><span id="st-log-summary" role="status" aria-live="polite"></span><button class="ui-btn ui-btn--ghost ui-btn--sm" type="button" id="st-log-clear" disabled>清空选择</button></div>
<div id="st-log-status" class="st-status" role="status" aria-live="polite"></div>`;

export function logListView(files, selected, empty) {
  if (!files.length) return html`<p class="st-log-empty">${empty}</p>`;
  return html`${each(files, file => file.id, file => html`<label class="st-log-row" data-key="${file.id}">
    <input type="checkbox" data-log-id="${file.id}" aria-label="选择 ${file.name}" ${selected.has(file.id) ? 'checked' : ''}>
    <span class="st-log-file"><strong>${file.name}</strong><span>${file.kind === 'runtime' ? '运行日志' : 'AI 请求日志'} · ${formatBytes(file.size_bytes)}</span></span>
    <time datetime="${file.modified_at}">${new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(file.modified_at))}</time>
  </label>`)}`;
}
