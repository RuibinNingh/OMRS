/**
 * 展示板题目面板：列表层（关联标记、停用 / 缺失提醒、题目行与行内留白）和从右滑入的详情层。
 * 两层都是「固定头 + 内部滚动的身体 + 固定脚」。详情题面与练习记录各有一个 skip 挂载点，
 * 由 index.js 的 hydrate 按「题 + 是否显示答案」填充；「打开题目」经 detail.js 打开共享题目弹窗。
 */
import { html, each, cls } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { kbd } from '../../ui/kbd.js';
import { labelChip, labelChips, labelObject, ensureColor } from '../../domain/labels/index.js';

export const pressed = on => (on ? 'true' : 'false');
export const off = flag => (flag ? html` disabled` : '');
export const flags = values => values.map(f => html`<span class="brd-flag" data-tone="${f.tone}"${f.title ? html` title="${f.title}"` : ''}>${f.text}</span>`);
const labelDots = names => (names || []).map(name => {
  const color = ensureColor(labelObject(name).color);
  return html`<i class="brd-label-dot"${color ? html` data-lbl-c="${color}"` : ''} title="${name}" aria-label="${name}"></i>`;
});
const GAP_PRESETS = Object.freeze([0, 2, 4, 6, 8]);

/** m = index.js paint() 交给 view() 的整页模型；这里只读 content / linked / inspector / panel / reveal。 */
export function questionPanel(m) {
  const detail = m.panel === 'detail';
  return html`<section class="brd-questions" aria-label="题目" data-key="questions"${detail ? html` data-detail` : ''}>
    <div class="brd-question-list" data-key="list-layer"${detail ? html` inert` : ''}>
      ${contentHead(m.content, m.linked)}
      <div class="brd-body" id="bd-content-body" data-key="body">${contentBody(m.content)}</div>
      <div class="brd-list-foot" data-key="foot">${icon('info')}<span>点题看详情，双击打开；拖 ⠿ 或按 ${kbd('Alt', '↑↓')} 排序</span></div>
    </div>
    <aside class="brd-ins" id="bd-inspector" aria-label="题目详情" data-key="detail-layer"${!detail ? html` inert` : ''}>${inspectorItem(m.inspector.item, !!m.reveal)}</aside>
  </section>`;
}

function contentHead(c, linked) {
  const syncText = !linked.name ? '关联后可一键同步新题'
    : linked.pending ? html`有 <b>${linked.pending}</b> 道新题没进板` : '带这个标记的题都在板里了';
  return html`<header class="brd-question-head"><h2>题目</h2><span>${c.count || 0}${c.suspended || c.missing ? ` / ${c.total}` : ''}</span><span class="brd-grow"></span>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.sortMenu" aria-label="排序" title="排序" aria-haspopup="menu"${off(c.total < 2)}>${icon('sort')}</button>
    <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-action="board.add" title="添加题目（A）">${icon('plus')}添加题目</button></header>
    <div class="${cls('brd-syncbar', linked.pending && 'has-pending')}">
      <button type="button" class="brd-syncbar__label" data-action="board.linkLabel" aria-haspopup="menu" title="更换关联的标记">${linked.name ? labelChip(linked.name) : '关联标记'}${icon('chevron-down')}</button>
      <span>${syncText}</span>
      ${linked.name ? html`<button type="button" class="ui-btn ui-btn--sm" data-action="board.sync"${off(!linked.pending)}>${icon('refresh')}同步</button>` : ''}</div>
    ${c.suspended ? html`<div class="brd-warn">${icon('info')}<span>${c.suspended} 道题已停用，打印时会跳过</span><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.clean" data-arg="suspended">移出</button></div>` : ''}
    ${c.missing ? html`<div class="brd-warn" data-tone="danger">${icon('alert-triangle')}<span>${c.missing} 道题已缺失，打印时会跳过</span><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.clean" data-arg="missing">移出</button></div>` : ''}
    ${c.rows?.length ? html`<div class="brd-cols" aria-hidden="true"><span>#</span><span>题目 · 顺序即纸面顺序</span><span>题后留白</span></div>` : ''}`;
}

function contentBody(c) {
  if (c.empty || c.kind === 'none') return html`<p class="brd-placeholder"><b>板里还没有题</b>点「添加题目」从题库挑，或者关联一个标记后一键同步。</p>`;
  return html`<div class="brd-rows" data-board-rows>${each(c.rows, row => row.uid, rowHtml)}</div>`;
}

function rowHtml(r) {
  const locked = r.missing || r.suspended;
  return html`<div class="${cls('brd-row', r.missing && 'is-missing', r.suspended && 'is-suspended')}" data-key="${r.uid}" data-board-row="${r.uid}" data-board-index="${r.index}" draggable="true" tabindex="-1"${r.selected ? html` aria-current="true"` : ''}>
    <span class="brd-row__grip" aria-hidden="true" title="拖动调整顺序">⠿</span><span class="brd-row__no">${r.no}</span>
    <div class="brd-row__main"><div class="brd-row__head"><strong class="brd-row__uid">${r.name}</strong>${flags(r.flags)}</div>
      <div class="brd-row__meta"><span>${r.category || r.subject || '未分科'}</span>${r.difficulty ? html`<span>难度 ${r.difficulty}</span>` : ''}<span class="brd-labels" data-lbl-target="${r.uid}">${labelDots(r.labels)}</span></div></div>
    <div class="${cls('brd-row-gap', !r.gap.inherited && 'is-own')}" title="${r.gap.inherited ? '跟随板的默认留白' : '这道题单独设置的留白'}">
      <button type="button" data-action="board.gapStep" data-arg="${r.uid}:-1" aria-label="减少一行留白"${off(locked || r.gap.lines <= 0)}>−</button>
      <span data-board-gap-view="${r.uid}">${r.gap.lines}<small>行</small></span>
      <button type="button" data-action="board.gapStep" data-arg="${r.uid}:1" aria-label="增加一行留白"${off(locked || r.gap.lines >= 48)}>+</button></div>
  </div>`;
}

function inspectorItem(it, reveal) {
  if (!it) return html`<p class="brd-placeholder">点一道题查看详情。</p>`;
  return html`<div class="brd-detail-nav" data-key="nav">
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.back" title="返回题目列表（Esc）">${icon('chevron-left')}全部题目</button>
      <span class="brd-detail-pos">${it.no} / ${it.total}</span>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.detailStep" data-arg="-1" aria-label="上一题" title="上一题（↑）"${off(it.index <= 0)}>${icon('chevron-up')}</button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.detailStep" data-arg="1" aria-label="下一题" title="下一题（↓）"${off(it.index >= it.total - 1)}>${icon('chevron-down')}</button>
      <button type="button" class="ui-btn ui-btn--sm brd-open-q" data-action="board.openItem" data-arg="${it.uid}" title="在题目弹窗里打开（Enter）"${off(it.missing)}>${icon('external')}打开题目</button></div>
    <div class="brd-detail-body" data-key="body">
      <p class="brd-detail-no">纸面第 ${it.no} 题</p>
      <h3 class="brd-detail-title"><span>${it.name}</span>${flags(it.flags)}</h3>
      <p class="brd-detail-meta">${it.metaBits.map(bit => html`<span>${bit}</span>`)}</p>
      <div class="brd-detail-labels" data-lbl-target="${it.uid}">${labelChips(it.labels, { add: true })}</div>
      ${gapCard(it)}
      <section class="brd-detail-sec" data-key="qsec"><h4>${reveal ? '题面与答案' : '题面'}${reveal ? html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.reveal">${icon('eye-off')}收起答案</button>` : ''}</h4>
        <div class="brd-qv" data-morph="skip" data-key="qv:${it.uid}:${reveal ? 1 : 0}" data-qv-host data-uid="${it.uid}" data-reveal="${reveal ? '1' : '0'}"></div></section>
      <section class="brd-detail-sec" data-key="rsec"><h4>练习记录</h4>
        <div class="brd-rec" data-morph="skip" data-key="rec:${it.uid}" data-board-rec data-uid="${it.uid}"></div></section>
    </div>
    <div class="brd-detail-foot" data-key="foot"><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.locate" data-arg="${it.uid}" title="把纸面翻到这道题">${icon('file')}在纸上找到</button>
      <span class="brd-grow"></span>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm brd-danger-text" data-action="board.remove" data-arg="${it.uid}" title="从这块板移出（Delete）">${icon('trash')}移出</button></div>`;
}

function gapCard(it) {
  const g = it.gap;
  return html`<section class="brd-gap-card" aria-label="题后留白" data-key="gap">
    <header class="brd-gap-card__head"><strong>题后留白</strong><span>约 ${g.cm} cm 书写空间</span></header>
    <div class="brd-gap-card__row">
      <div class="brd-step" role="group" aria-label="题后留白行数">
        <button type="button" data-action="board.gapStep" data-arg="${it.uid}:-1" aria-label="减少一行留白"${off(g.lines <= 0 || it.missing)}>−</button>
        <output aria-live="polite"><b>${g.lines}</b>行</output>
        <button type="button" data-action="board.gapStep" data-arg="${it.uid}:1" aria-label="增加一行留白"${off(g.lines >= 48 || it.missing)}>+</button></div>
      <div class="brd-gap-card__presets" role="group" aria-label="常用留白行数">${GAP_PRESETS.map(n => html`<button type="button" data-action="board.gapPreset" data-arg="${it.uid}:${n}" aria-pressed="${pressed(g.lines === n)}"${off(it.missing)}>${n}</button>`)}</div></div>
    <p class="brd-gap-card__hint">${it.own === '' ? `跟随板的默认留白 ${it.inherited} 行；改了只影响这道题。`
      : html`这道题单独设置 · <button type="button" class="brd-text-btn" data-action="board.inherit">改回默认 ${it.inherited} 行</button>`}</p>
    ${it.note ? html`<p class="brd-gap-card__note">${icon('info')}<span>${it.note}</span></p>` : ''}</section>`;
}

/** 练习记录摘要（index.js 拿到题目详情后填进 [data-board-rec]）：战绩带 + 一句话。streak 是 qStreakHtml 的结果。 */
export function recordSummary(summary, streak) {
  if (!summary.count) return html`<p>${summary.text}</p>`;
  return html`<div class="brd-rec__line">${streak}<span><b>${summary.rate}%</b> 正确</span></div>
    <p>${summary.text}</p>${summary.alert ? html`<p data-tone="danger">${summary.alert}</p>` : ''}`;
}
