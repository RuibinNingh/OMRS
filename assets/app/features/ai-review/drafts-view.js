/** AI 草稿工作区：列表、来源关联、字段与有序内容块。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { empty } from '../../ui/empty.js';
import { draftPendingCount, draftStatusLabel } from './drafts-state.js';

import { reviewWorkspace } from './drafts-review.js';
import { sourceWorkspace, canvasPanel, sourceView } from './drafts-sources.js';

const statuses = [
  ['pending', '待审核'], ['done', '已入库'], ['discarded', '已丢弃'],
];
const titleOf = draft => draft.blocks?.find(block => block.section === '题目' && block.kind === 'text')?.text?.slice(0, 72)
  || draft.blocks?.find(block => block.section === '题目' && block.kind === 'image')?.note || '图片草稿';

function listView({ list, listLoaded, listError, filter, selectedId, counts, busy, queueOpen }) {
  return html`<aside class="drf-list ${queueOpen ? 'is-open' : ''}" aria-label="AI 草稿列表">
    <div class="drf-list-head"><div><h2>AI 草稿</h2><p class="drf-count">${draftPendingCount(counts)} 份待审核</p></div>
      <div class="drf-list-actions">${button({ label: queueOpen ? '收起队列' : '查看队列', variant: 'ghost', size: 'sm', action: 'ai-review.draftToggleQueue' })}
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="ai-review.draftQueueMenu" aria-haspopup="menu" aria-label="草稿队列更多操作"${busy ? html` disabled` : ''}>更多</button></div></div>
    <div class="drf-filters"><select class="ui-select" data-change="ai-review.draftFilter" aria-label="筛选草稿"${busy ? html` disabled` : ''}>
      ${statuses.map(([value, label]) => html`<option value="${value}"${filter === value ? html` selected` : ''}>${label}</option>`)}
    </select></div>
    ${listError ? html`<div class="drf-error" role="alert">读取列表失败：${listError}${button({ label: '重试', size: 'sm', action: 'ai-review.draftReload' })}</div>`
    : !listLoaded ? html`<p role="status">正在读取草稿…</p>`
      : list.length ? html`<div class="drf-list-items">${each(list, draft => draft.id, draft => html`
      <button type="button" class="drf-item ${draft.id === selectedId ? 'on' : ''}" data-key="${draft.id}"
        data-action="ai-review.draftOpen" data-arg="${draft.id}" aria-current="${draft.id === selectedId ? 'true' : 'false'}">
        <span class="drf-item-top"><strong>${draft.subject || '未填科目'} · ${draft.category || '未填分类'}</strong>${draft.status === 'cropping' ? html`<small>待框选</small>` : ''}</span>
        <span class="drf-item-excerpt">${titleOf(draft)}</span>${draft.source_channel === 'mcp' ? html`<small>来源：MCP</small>` : ''}
      </button>`)}</div>` : empty({ icon: 'inbox', title: filter === 'pending' ? '没有待审核草稿' : '这里还没有草稿',
        hint: filter === 'pending' ? 'AI 助手创建的草稿会出现在这里。' : '切换筛选可查看其他状态。', bordered: true })}
  </aside>`;
}

function detailView(state) {
  const { draft, value, detailLoaded, detailError, dirty, busy, message, conflict } = state;
  const error = detailError ? html`<div class="drf-error" role="alert">读取草稿失败：${detailError}${draft && value ? '；当前内容保留。' : ''}${button({ label: '重试', action: 'ai-review.draftRetry' })}</div>` : '';
  if (detailError && (!draft || !value)) return html`<main class="drf-detail">${error}</main>`;
  if (!detailLoaded) return html`<main class="drf-detail"><p role="status">正在读取草稿…</p></main>`;
  if (!draft || !value) return html`<main class="drf-detail">${empty({ icon: 'inbox', title: '选择一份草稿', hint: '在左侧列表选择，核对后保存或通过。', bordered: true })}</main>`;
  const readonly = draft.status === 'done' || draft.status === 'discarded';
  const position = state.list.findIndex(row => row.id === draft.id);
  const total = state.list.length;
  const mode = state.workspaceMode || 'review';
  return html`<main class="drf-detail" data-workspace-mode="${mode}"><div class="drf-detail-head"><div class="drf-detail-title"><span class="drf-eyebrow">AI 草稿审核${draft.source_channel === 'mcp' ? ' · 来源：MCP' : ''}</span>
    ${draft.cause_verification === 'client_asserted' ? html`<p class="hint">错因由外部助手提供，待核对。${draft.cause_statement || ''}</p>` : ''}
      <p class="drf-id">${position >= 0 ? `第 ${position + 1}/${total} 题 · ` : ''}${draft.id}</p>
      <h2 title="草稿版本 ${draft.revision ?? '?'}">${draftStatusLabel(draft.status)} ${dirty ? '· 未保存' : ''}</h2>${error}</div>
      <div class="drf-detail-actions"><div class="drf-review-nav">${button({ label: '上一题', size: 'sm', action: 'ai-review.draftNavigate', arg: '-1', disabled: busy || position <= 0 })}
        ${button({ label: '下一题', size: 'sm', action: 'ai-review.draftNavigate', arg: '1', disabled: busy || position < 0 || position >= total - 1 })}</div>
        <button type="button" class="drf-source-trigger ui-btn ui-btn--sm" data-action="ai-review.draftToggleSource" aria-expanded="${mode === 'source' ? 'true' : 'false'}">${mode === 'source' ? '返回并排核对' : value.source_images.length ? '放大框选' : '来源与关联'}<span class="ui-btn__label"> · ${value.source_images.length} 张图</span></button></div></div>
    ${message ? html`<p class="drf-message" role="status">${message}
      ${conflict ? button({ label: '重新读取并放弃本地修改', size: 'sm', action: 'ai-review.draftReloadDetail' }) : ''}</p>` : ''}
    ${draft.status === 'done' ? html`<p class="drf-success">${draft.question_available === false ? '已入库，题目当前不可用' : `已入库：${draft.uid || draft.question_id || '题目'}`}
      ${draft.uid && draft.question_available !== false ? button({ label: '查看题目', size: 'sm', action: 'ai-review.draftQuestion' }) : ''}</p>` : ''}
    ${mode === 'source' ? sourceWorkspace(state, readonly) : reviewWorkspace(state, readonly,
      value.source_images.length ? html`<aside class="drf-entry-source" aria-label="原图与框选">${canvasPanel(state)}
        <details class="drf-source-maintenance" data-key="source-maintenance"><summary>来源图片与关联管理</summary>${sourceView(draft, value, readonly || busy)}</details></aside>` : '')}</main>`;
}

export function draftsView(state) {
  return state.embedded ? html`${state.listError ? html`<p class="drf-error" role="alert">读取草稿列表失败：${state.listError}${button({ label: '重试草稿列表', action: 'ai-review.draftReload' })}</p>` : ''}${detailView(state)}` : html`<div class="drf">${listView(state)}${detailView(state)}</div>`;
}
