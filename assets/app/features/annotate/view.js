/** 框选标注页模板：顶栏（角色、进度、导出）、左栏（上传与图片队列）、画布区的外框与状态行、快捷键面板。 */
import { html, each, cls } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { filedrop } from '../../ui/filedrop.js';
import { kbd } from '../../ui/kbd.js';
import { select } from '../../ui/select.js';
import { FILTERS, ROLES, countRoles, filterImages, summary } from './state.js';

export const ACCEPT = 'image/png,image/jpeg,image/gif';
export const EXPORT_FORMATS = Object.freeze([
  { value: 'yolo', label: 'YOLO txt + JSONL' },
  { value: 'omrs_jsonl', label: 'OMRS JSONL' },
]);
export const exportHref = format => `/api/annotate/export?format=${encodeURIComponent(format)}`;

/** 快捷键表：每行 [按键组合列表, 说明]；一个组合是按键数组，多个组合之间显示「/」。 */
export const SHORTCUTS = Object.freeze([
  ['画框', [[[['拖动']], '画当前角色的框'], [[['Shift', '拖动']], '画另一种角色'], [[['F']], '整张图一个框']]],
  ['角色', [[[['Q']], '题目（选中框时改它的角色）'], [[['A']], '答案（同上）'], [[['Tab']], '选中下一个框']]],
  ['编辑', [[[['Delete']], '删除选中框'], [[['Ctrl', 'Z']], '撤销'], [[['Ctrl', 'Shift', 'Z'], ['Ctrl', 'Y']], '重做'], [[['C']], '沿用上一张的框'], [[['Esc']], '取消选中']]],
  ['翻页', [[[['Enter']], '完成，跳到下一张未完成'], [[['Shift', 'Enter']], '没有题目也标为完成'], [[['←'], ['→']], '上一张 / 下一张']]],
  ['其他', [[[['Ctrl', 'V']], '粘贴截图上传'], [[['+'], ['-'], ['0']], '放大 / 缩小 / 适应宽度'], [[['Shift', 'Delete']], '删除这张图'], [[['?']], '显示这张表']]],
]);

function roleSwitch(role) {
  return html`<div class="an-roles" role="group" aria-label="画框角色">
    ${Object.entries(ROLES).map(([key, label]) => html`<button type="button" class="${cls('an-role', `an-role--${key}`, role === key && 'is-on')}" data-action="role" data-arg="${key}" aria-pressed="${role === key ? 'true' : 'false'}">
      <span class="an-role__swatch" aria-hidden="true"></span>${label}${kbd(key === 'question' ? 'Q' : 'A')}</button>`)}
  </div>`;
}

export function headerView(state, format) {
  const s = summary(state.images);
  const pct = s.total ? Math.round(s.done / s.total * 100) : 0;
  return html`<div class="an-brand"><h1>框选标注</h1><span class="an-brand__sub">题目 / 答案训练数据</span></div>
    ${roleSwitch(state.role)}
    <div class="an-progress" title="已完成 ${s.done} 张，未完成 ${s.todo} 张">
      <span class="an-progress__num"><strong>${s.done}</strong> / ${s.total}</span>
      <progress class="an-progress__bar" max="100" value="${pct}" aria-label="完成 ${pct}%"></progress>
    </div>
    <div class="an-export">
      <span data-change="format">${select({ id: 'an-format', options: EXPORT_FORMATS, value: format, size: 'sm', label: '导出格式' })}</span>
      <a class="ui-btn ui-btn--sm" id="an-export" href="${exportHref(format)}" download title="只导出已完成的图片"><span class="ui-btn__label">导出已完成</span></a>
    </div>
    ${button({ label: '快捷键', icon: 'help-circle', size: 'sm', variant: 'ghost', action: 'help', title: '快捷键（?）' })}`;
}

/** 左栏上半：上传入口与筛选。 */
export function sideTopView(state) {
  const s = summary(state.images);
  const counts = { all: s.total, todo: s.todo, done: s.done };
  const up = state.uploading;
  return html`<div class="an-drop">${filedrop({ id: 'an-file', title: up ? `正在上传 ${up.done} / ${up.total}` : '拖入截图或文件夹', hint: up ? '可以边传边标，也可以继续拖入' : '也可以直接 Ctrl + V 粘贴', accept: ACCEPT, multiple: true })}
      ${up ? html`<progress class="an-drop__bar" max="${up.total}" value="${up.done}" aria-label="上传进度"></progress>` : ''}
      <label class="an-folder"><input type="file" id="an-folder" webkitdirectory multiple>选择整个文件夹</label>
    </div>
    <div class="an-filters" role="group" aria-label="筛选">
      ${FILTERS.map(f => html`<button type="button" class="${cls('an-filter', state.filter === f.value && 'is-on')}" data-action="filter" data-arg="${f.value}" aria-pressed="${state.filter === f.value ? 'true' : 'false'}">${f.label}<span class="an-filter__n">${counts[f.value]}</span></button>`)}
    </div>`;
}

/** 队列一行的签名：签名不变就不重画这一行（大批量时只改动过的行走 morph）。 */
export const rowSignature = (image, n, cur) => {
  const c = countRoles(image.boxes);
  return `${n}|${image.id === cur ? 1 : 0}|${image.status}|${c.question}|${c.answer}|${image.file}`;
};

/** 队列一行（<li> 的内容）；n 为在全部图片里的序号。 */
export function rowView(image, n, cur) {
  const c = countRoles(image.boxes);
  return html`<button type="button" class="${cls('an-item', image.id === cur && 'is-current', image.status === 'done' && 'is-done')}" data-action="open" data-arg="${image.id}"${image.id === cur ? html` aria-current="true"` : ''}>
    <span class="an-item__n">${n}</span>
    <span class="an-item__name">${image.file || image.id}</span>
    <span class="an-item__meta"><span class="an-count an-count--question" title="题目框">${c.question}</span><span class="an-count an-count--answer" title="答案框">${c.answer}</span></span>
  </button>`;
}

/** 序号表：id → 在全部图片里的位置（1 起），一次算好，避免每行 indexOf。 */
export const numbering = images => new Map(images.map((image, i) => [image.id, i + 1]));

export function listView(state, list = filterImages(state.images, state.filter), numbers = numbering(state.images)) {
  if (!list.length) return html`<li class="an-list__empty">${state.images.length ? '这个筛选下没有图片' : '还没有图片'}</li>`;
  return each(list, image => image.id, image => html`<li data-key="${image.id}">${rowView(image, numbers.get(image.id), state.cur)}</li>`);
}

const SAVE_TEXT = { idle: '已保存', pending: '待保存…', saving: '保存中…', error: '保存失败，稍后重试' };

export function footView(state, image, zoomPct) {
  if (!image) return html``;
  const c = countRoles(image.boxes);
  return html`<span class="an-foot__file" title="${image.file || ''}">${image.file || image.id}</span>
    <span class="an-foot__dim">${image.width}×${image.height} · ${zoomPct}%</span>
    <span class="an-foot__boxes">题目 ${c.question} · 答案 ${c.answer}</span>
    <span class="${cls('an-foot__status', image.status === 'done' && 'is-done')}">${image.status === 'done' ? '已完成' : '未完成'}</span>
    <span class="${cls('an-foot__save', `is-${state.saving}`)}" role="status">${SAVE_TEXT[state.saving] || ''}</span>
    <span class="an-foot__gap"></span>
    ${image.status === 'done' ? button({ label: '改回未完成', size: 'sm', variant: 'ghost', action: 'reopen' }) : ''}
    ${button({ label: '清空框', size: 'sm', variant: 'ghost', action: 'clear', disabled: !image.boxes.length })}
    ${button({ label: '删除这张', icon: 'trash', size: 'sm', variant: 'ghost', action: 'remove', title: 'Shift + Delete' })}
    ${button({ label: '完成，下一张', icon: 'check', size: 'sm', variant: 'primary', action: 'finish', title: 'Enter' })}`;
}

export function emptyView(state) {
  if (state.loading) return html`<p class="an-empty__text" role="status">正在读取…</p>`;
  if (state.error) return html`<div class="an-empty__box"><p class="an-empty__text" role="alert">${state.error}</p>${button({ label: '重试', size: 'sm', action: 'reload' })}</div>`;
  return html`<div class="an-empty__box">
    <p class="an-empty__title">把截图拖到左边，或直接按 ${kbd('Ctrl', 'V')} 粘贴</p>
    <p class="an-empty__text">每张图只标两样东西：题目在哪、答案在哪。拖动画框，按 ${kbd('Enter')} 完成并跳到下一张。</p>
  </div>`;
}

export function helpView() {
  return html`<div class="an-help__grid">${SHORTCUTS.map(([group, rows]) => html`<section class="an-help__group"><h3>${group}</h3><dl>
    ${rows.map(([combos, text]) => html`<div class="an-help__row"><dt>${combos.map((keys, i) => html`${i ? html`<span class="an-help__or">/</span>` : ''}${kbd(...keys)}`)}</dt><dd>${text}</dd></div>`)}
  </dl></section>`)}</div>`;
}
