/**
 * 选板浮层的模板：只产出 html``，由 picker.js 用 morph 写进浮层根节点。不碰 DOM、不读全局；单测见 tests/app/board-picker.test.mjs。
 * 行用 <button role="option">，键盘高亮只是 is-active 类 + 搜索框的 aria-activedescendant（焦点始终留在搜索框）。
 * 提示符列宽度恒定：↵ / ✓ / ↗ 出现时行内容不位移。
 */
import { html, each, cls } from '../../core/html.js';
import { icon } from '../../ui/icon.js';

/** 行元素的 id（aria-activedescendant 指向它）：浮层实例前缀 + 行 key。 */
export const boardPickerOptionId = (idBase, key) => `${idBase}-${key}`;

/** 行尾说明：题数、已印页数、缺失；部分已在板中时追加「已有 x/y」，全部在板中时只说这一句。 */
export function boardPickerMeta(board, state) {
  if (state.kind === 'full') return html`<span class="bpicker-state">已全部在板中</span>`;
  const paper = board.printed_summary || {};
  const bits = [html`<span>${board.count ?? 0} 题</span>`];
  if (paper.pages) bits.push(html`<span class="is-printed">已印 ${paper.pages} 页</span>`);
  if (board.missing) bits.push(html`<span class="is-missing">缺失 ${board.missing}</span>`);
  if (state.kind === 'partial') bits.push(html`<span class="bpicker-state">已有 ${state.have}/${state.total}</span>`);
  return bits.map((bit, i) => (i ? html` · ${bit}` : bit));
}

/** 提示符：本次已加 ✓；全部已在板中 ↗（点了打开该板）；键盘高亮 ↵。 */
export function boardPickerCue(row, active) {
  if (row.added) return '✓';
  if (row.state.kind === 'full') return '↗';
  return active ? '↵' : '';
}

function optionView(row, active, idBase) {
  const full = row.state.kind === 'full';
  return html`<button type="button" class="${cls('bpicker-opt', full && 'is-full', row.added && 'is-added', active && 'is-active')}" data-key="${row.key}" id="${boardPickerOptionId(idBase, row.key)}" data-bpk-board="${row.board.id}" role="option" aria-selected="${row.added ? 'true' : 'false'}" title="${row.board.note || row.board.name}"><span class="bpicker-cue" aria-hidden="true">${boardPickerCue(row, active)}</span><span class="bpicker-name">${row.board.name}${row.folderName ? html`<small>${row.folderName}</small>` : ''}</span><span class="bpicker-meta">${boardPickerMeta(row.board, row.state)}</span></button>`;
}

function groupView(group) {
  const count = group.count == null ? '' : html`<em>${group.count}</em>`;
  if (group.plain) return html`<div class="bpicker-group is-plain" data-key="${group.key}" role="presentation"><span class="bpicker-gname">${group.name}</span>${count}</div>`;
  return html`<button type="button" class="${cls('bpicker-group', group.folded && 'is-folded')}" data-key="${group.key}" data-bpk-fold="${group.id}" aria-expanded="${group.folded ? 'false' : 'true'}" tabindex="-1">${icon('chevron-down')}<span class="bpicker-gname">${group.name}</span>${count}</button>`;
}

/** 底栏提示：连加过就显示已加入几个板。 */
export function boardPickerHint(addedCount) {
  return addedCount ? html`已加入 <b>${addedCount}</b> 个板 · ⌘ 点击撤回` : 'Enter 加入 · Esc 关闭 · ⌘ 连加';
}

/** 「新建」按钮文案：搜索框有字时直接用它当板名。 */
export function boardPickerNewLabel(query) {
  const name = String(query || '').trim();
  return name ? `＋ 新建《${name}》并加入` : '＋ 新建板并加入…';
}

/**
 * 浮层内容。view: { title, count, query, items, rows, active, empty, addedCount, idBase }。
 * 搜索框的 value 写进模板；morph 不改聚焦中的输入框，所以打字时不会被回写。
 */
export function boardPickerView(view) {
  const activeRow = view.rows?.[view.active] || null;
  const activeKey = activeRow ? activeRow.key : '';
  const listId = `${view.idBase}-list`;
  const body = view.empty
    ? html`<div class="bpicker-empty" data-key="~empty">${view.empty}</div>`
    : each(view.items, item => item.key, item => (item.type === 'group' ? groupView(item) : optionView(item, item.key === activeKey, view.idBase)));
  return html`<div class="bpicker-head"><span class="bpicker-title">${view.title}</span><small class="bpicker-count">${view.count} 道题</small><button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm bpicker-x" data-bpk="close" aria-label="关闭">${icon('x')}</button></div>
<input class="ui-input ui-input--sm bpicker-search" data-bpk="search" value="${view.query}" placeholder="搜索板名或文件夹…" autocomplete="off" spellcheck="false" role="combobox" aria-label="搜索展示板" aria-expanded="true" aria-autocomplete="list" aria-controls="${listId}"${activeRow ? html` aria-activedescendant="${boardPickerOptionId(view.idBase, activeKey)}"` : ''}>
<div class="bpicker-list" id="${listId}" role="listbox" aria-label="展示板">${body}</div>
<div class="bpicker-foot"><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm bpicker-new" data-bpk="new">${boardPickerNewLabel(view.query)}</button><span class="bpicker-hint">${boardPickerHint(view.addedCount)}</span></div>`;
}

/** 「新建展示板」对话框的表单：板名（搜索框里的字作初值）+ 放进哪个文件夹（有文件夹时才有，默认上次用的板所在的文件夹）。 */
export function boardPickerNewBody({ seed = '', folders = [], current = '' } = {}) {
  const list = Array.isArray(folders) ? folders : [];
  const select = list.length
    ? html`<label class="bpicker-newfolder">放进<select class="ui-select bpicker-newfolder__select" id="bpk-new-folder">${list.map(folder => html`<option value="${folder.id}"${folder.id === current ? ' selected' : ''}>${folder.name}</option>`)}<option value=""${current ? '' : ' selected'}>未归档</option></select></label>`
    : '';
  return html`<input class="ui-input" id="bpk-new-name" value="${seed}" placeholder="如：考前速览·三角函数" maxlength="120" aria-label="板名">${select}`;
}
