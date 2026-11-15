/** 问题工作台：宽列表、状态导航与批量操作。 */
import { html, raw } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { statuses } from '../../domain/problems.js';
import { detailView } from './view-detail.js';

export const disabled = value => raw(value ? 'disabled' : '');
export const statusBadge = p => html`<span class="prb-status" data-status="${p.status}"><span class="prb-dot"></span>${statuses[p.status]}</span>`;
const shortDate = t => new Date(t * 1000).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
const preview = text => (text || '').replace(/!\[[^\]]*\]\([^)]*\)/g, '[图片]').replace(/[#*`>\[\]]/g, '').replace(/\s+/g, ' ').trim();

function tabs(s) {
  return html`<nav class="prb-tabs" aria-label="按状态查看问题">
    ${[['', '全部问题'], ...Object.entries(statuses), ['trash', '回收站']].map(([key, label]) => html`
      <button class="prb-tab ${s.filter === key ? 'is-active' : ''}" data-prb="filter" data-value="${key}" aria-current="${s.filter === key ? 'true' : 'false'}" ${disabled(s.busy)}>
        ${key === 'trash' ? icon('trash') : ''}${label}<span>${s.counts[key || 'all'] ?? '—'}</span>
      </button>`)}</nav>`;
}
function selection(s) {
  const trash = s.filter === 'trash';
  return html`<div class="prb-bulk" data-key="selection">
    <strong>已选 ${s.chosen.size} 项</strong><button class="ui-btn ui-btn--ghost ui-btn--sm" data-prb="clearSelected" ${disabled(s.busy)}>取消选择</button>
    <div class="prb-bulk-actions">${trash ? html`<button class="ui-btn" data-prb="restore" ${disabled(s.busy)}>${icon('undo')}恢复问题</button>` : html`
      <select class="ui-select" aria-label="批量修改状态" data-prb-batch-status ${disabled(s.busy)}><option value="" selected>修改状态…</option>${Object.entries(statuses).map(([k, v]) => html`<option value="${k}">${v}</option>`)}</select>
      <button class="ui-btn ui-btn--danger" data-prb="trash" ${disabled(s.busy)}>${icon('trash')}删除</button>`}
    </div></div>`;
}
function rows(s) {
  return html`<div class="prb-table-head"><label class="prb-check"><input type="checkbox" data-prb-check-all aria-label="选择本页全部问题" ${raw(s.items.length && s.items.every(p => s.chosen.has(p.id)) ? 'checked' : '')} ${disabled(s.loading || s.busy || !s.items.length)}></label><span>问题 / 说明</span><span class="prb-col-status">状态</span><span class="prb-col-links">关联题目</span><span class="prb-col-date">最近更新</span><span></span></div>
    <div class="prb-items" aria-label="问题列表" aria-busy="${s.loading ? 'true' : 'false'}">${s.items.map(p => html`
      <div class="prb-row ${s.detail?.id === p.id ? 'is-selected' : ''} ${s.chosen.has(p.id) ? 'is-checked' : ''}" data-key="${p.id}">
        <label class="prb-check"><input type="checkbox" data-prb-check="${p.id}" aria-label="选择 ${p.title}" ${raw(s.chosen.has(p.id) ? 'checked' : '')} ${disabled(s.loading || s.busy)}></label>
        <button class="prb-row-open" data-prb="open" data-id="${p.id}" aria-expanded="${s.detail?.id === p.id ? 'true' : 'false'}" ${disabled(s.busy || s.loading)}>
          <span class="prb-row-title"><strong>${p.title}</strong><span class="prb-excerpt">${preview(p.description_md) || '尚未填写说明'}</span><small class="prb-row-meta">${p.question_count} 道关联题 · ${shortDate(p.updated_at)}</small></span>
          <span class="prb-col-status">${statusBadge(p)}</span><span class="prb-col-links">${icon('link')}${p.question_count} 道</span><time class="prb-col-date" datetime="${new Date(p.updated_at * 1000).toISOString()}">${shortDate(p.updated_at)}</time>${icon('chevron-right')}
        </button>
      </div>`)}</div>`;
}
function empty(s) {
  const filtered = s.query || s.filter;
  return html`<div class="prb-empty">${icon(s.filter === 'trash' ? 'trash' : filtered ? 'search' : 'inbox', { size: 'lg' })}
    <h2>${s.filter === 'trash' ? '回收站是空的' : filtered ? '没有找到匹配的问题' : '记下第一个想改善的问题'}</h2>
    <p>${s.filter === 'trash' ? '删除的问题会保留在这里，可以随时恢复。' : filtered ? '试试其他关键词，或放宽状态筛选。' : '从一个具体现象开始，补充应对办法，再验证是否改善。'}</p>
    <button class="ui-btn" data-prb="${filtered ? 'clear' : 'new'}">${filtered ? '查看全部问题' : '新建问题'}</button></div>`;
}
export function view(s) {
  return html`<div class="prb-page ${s.detail || s.opening ? 'has-detail' : ''}">
    <header class="prb-page-head"><div><h2>问题工作台</h2><p>集中浏览、整理和跟进每一个问题。</p></div><div class="prb-page-actions"><span class="prb-overview">${(s.counts.analyzing || 0) + (s.counts.working || 0) + (s.counts.verifying || 0)} 个进行中</span><button class="ui-btn ui-btn--primary ui-btn--lg" data-prb="new" ${disabled(s.busy)}>${icon('plus')}新建问题</button></div></header>
    ${tabs(s)}
    <div class="prb-workspace"><section class="prb-list" aria-label="浏览问题">
      <div class="prb-toolbar"><label class="prb-search">${icon('search')}<input class="ui-input" data-prb-field="query" value="${s.query}" placeholder="搜索标题或说明…" aria-label="搜索问题" ${disabled(s.busy)}><kbd>/</kbd></label>
        <select class="ui-select prb-sort" data-prb-field="sort" aria-label="问题排序" ${disabled(s.busy)}>${[['updated_desc', '最近更新'], ['updated_asc', '最早更新'], ['title', '标题排序'], ['questions_desc', '关联题目最多']].map(([k, v]) => html`<option value="${k}" ${raw(s.sort === k ? 'selected' : '')}>${v}</option>`)}</select>
        <button class="ui-btn ui-btn--ghost ui-btn--icon" data-prb="refresh" aria-label="刷新问题列表" ${disabled(s.loading || s.busy)}>${icon('refresh')}</button></div>
      ${s.chosen.size ? selection(s) : html`<div class="prb-list-caption" data-key="caption"><span>${s.filter === 'trash' ? '回收站' : statuses[s.filter] || '全部问题'}<strong>${s.total}</strong></span><span>${s.loading ? '正在读取…' : '勾选问题可批量管理'}</span></div>`}
      ${s.listError ? html`<div class="prb-error" role="alert">${icon('alert-circle')}<span>列表读取失败，保留上次结果：${s.listError}</span><button class="ui-btn ui-btn--sm" data-prb="refresh">重试</button></div>` : ''}
      <div class="prb-scroll">${s.items.length ? rows(s) : s.loading ? html`<div class="prb-empty" role="status">正在读取问题…</div>` : s.listError ? '' : empty(s)}</div>
      <footer class="prb-pagination"><label>每页<select class="ui-select" data-prb-field="limit" aria-label="每页问题数量" ${disabled(s.loading || s.busy)}>${[25, 50, 100].map(n => html`<option value="${n}" ${raw(s.limit === n ? 'selected' : '')}>${n}</option>`)}</select></label><span>${s.total ? s.offset + 1 : 0}–${Math.min(s.offset + s.items.length, s.total)} / ${s.total}</span><div><button class="ui-btn ui-btn--icon" data-prb="prev" aria-label="上一页" ${disabled(!s.offset || s.loading || s.busy)}>${icon('chevron-left')}</button><span>${Math.floor(s.offset / s.limit) + 1} / ${Math.max(1, Math.ceil(s.total / s.limit))}</span><button class="ui-btn ui-btn--icon" data-prb="next" aria-label="下一页" ${disabled(s.offset + s.limit >= s.total || s.loading || s.busy)}>${icon('chevron-right')}</button></div></footer>
    </section>
    ${s.detail || s.opening ? detailView(s) : ''}</div>
    <div class="prb-message ${s.error ? 'is-error' : ''}" role="status">${s.message}${s.detailError ? html`<span role="alert">读取详情失败：${s.detailError}</span>` : ''}</div>
  </div>`;
}
