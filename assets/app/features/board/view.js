/**
 * 展示板工作台：左栏板树、板头、确认条、常驻纸面、版式与纸面记录浮层；题目面板在 view-panel.js。
 * 纸面 #bd-stage 是唯一常驻的 skip 节点；它和父节点 .brd-desk 在纸面列里的位置固定，浮层宿主排在它后面。
 */
import { html, each, cls } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { kbd } from '../../ui/kbd.js';
import { labelChip } from '../../domain/labels/index.js';
import { ANSWER_OPTIONS, CUT_OPTIONS } from './state.js';
import { questionPanel, pressed, off } from './view-panel.js';

export function view(m) {
  return html`<div class="brd" data-key="brd"${m.listHidden ? html` data-list-hidden` : ''}>
    <nav class="brd-list" id="bd-list" aria-label="展示板列表" data-key="list"${m.boardsOpen ? html` data-open` : ''}>${listPane(m.tree)}</nav>
    <div class="brd-list-scrim" data-action="board.toggleBoards" data-key="scrim" aria-hidden="true"></div>
    <section class="brd-main" id="bd-content" aria-label="板内容" data-key="main">
      <header class="brd-bar" id="bd-statusbar" data-key="bar">${statusBar(m.status, m.renaming)}</header>
      <div class="brd-confirm" data-key="confirm"${!m.status.awaiting ? html` hidden` : ''}>${confirmBar(m.status)}</div>
      <div class="brd-work" data-key="work">
        <section class="brd-paper-col" aria-label="纸面预览" data-key="paper">
          <div class="brd-head" data-key="head">${stageHead({ ...m.stage, motionOpen: m.pop === 'motion' })}</div>
          <div class="brd-desk" data-key="desk"><div class="brd-stage" id="bd-stage" data-morph="skip" data-key="stage"></div></div>
          <div class="brd-pop-host" data-key="pop"${!m.pop ? html` hidden` : ''}>${popover(m.pop, m.inspector)}</div>
        </section>
        ${questionPanel(m)}
      </div>
    </section>
  </div>`;
}

const openList = html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-open-list" data-action="board.toggleBoards" aria-label="打开展示板列表" title="展示板列表">${icon('menu')}</button>`;

function statusBar(s, renaming) {
  if (s.empty) return html`<div class="brd-title-block"><div class="brd-title-line">${openList}<h2 class="brd-title">没有选中展示板</h2></div></div>`;
  return html`<div class="brd-title-block">
      <div class="brd-title-line">${openList}
      ${renaming ? html`<input class="ui-input brd-rename" data-board-rename value="${s.name}" maxlength="120" aria-label="展示板名称（Enter 保存，Esc 取消）">`
        : html`<h2 class="brd-title" data-board-rename-target title="双击重命名">${s.name}</h2>
          <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-rename-btn" data-action="board.rename" aria-label="重命名展示板" title="重命名">${icon('edit')}</button>`}
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.menu" data-arg="${s.id}" aria-label="展示板更多操作" title="更多" aria-haspopup="menu">${icon('more-h')}</button></div>
      <p class="brd-sub"><span>${icon('folder')}${s.folder}</span><span>${s.count} 题</span>
        <button type="button" class="${cls('brd-note-link', !s.note && 'is-empty')}" data-action="board.note" title="编辑备注">${s.note || '添加备注'}</button>
        <span class="${cls('brd-save-state', s.saving && 'is-busy')}">${icon(s.saving ? 'refresh' : 'check-circle')}${s.saving ? '正在保存…' : '已保存'}</span>
        ${s.locked ? html`<span class="brd-locked">${icon('lock')}版式已锁定</span>` : ''}</p>
    </div>
    <div class="brd-header-acts">
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.export" aria-label="下载 HTML" title="下载自包含 HTML">${icon('download')}</button>
      ${s.canNew ? html`<div class="brd-seg" role="group" aria-label="打印范围" data-board-modes>
        <button type="button" class="brd-seg__btn" data-board-mode="new" data-action="board.mode" data-arg="new" aria-pressed="${pressed(s.scope === 'new')}">只印新增</button>
        <button type="button" class="brd-seg__btn" data-board-mode="all" data-action="board.mode" data-arg="all" aria-pressed="${pressed(s.scope === 'all')}">全部重印</button></div>` : ''}
      <button type="button" class="ui-btn ui-btn--primary brd-primary" data-board-primary data-action="board.primary" title="打印预览（P）"${off(!s.printable)}>${icon('print')}${s.actionLabel}</button>
    </div>`;
}

function confirmBar(s) {
  if (!s.awaiting) return '';
  return html`<span class="brd-confirm__icon">${icon('print')}</span><div class="brd-confirm__text"><strong>打印好了吗？确认后才会记下纸面</strong>
    <span>确认后系统会记住每道题印在第几页，之后加题就能只补印新增。</span></div>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.cancelPrint">没打成</button>
    <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-action="board.markPrinted">已打印，记录纸面</button>`;
}

function listPane(t) {
  return html`<div class="brd-list__head"><h2 class="brd-list__title">展示板<span class="brd-count">${t.count}</span></h2>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.newFolder" aria-label="新建文件夹" title="新建文件夹">${icon('folder')}</button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.toggleBoards" aria-label="收起展示板列表" title="收起列表">${icon('chevron-left')}</button></div>
    <button type="button" class="ui-btn brd-new" data-action="board.create" title="新建展示板（N）">${icon('plus')}新建展示板${kbd('N')}</button>
    <label class="brd-search">${icon('search')}<input type="search" data-board-search data-input="board.search" value="${t.query || ''}" placeholder="查找展示板" aria-label="查找展示板"></label>
    <div class="brd-tree" data-board-tree data-key="tree">${t.empty ? html`<p class="brd-list__note">还没有展示板，点上方按钮新建。</p>`
      : t.groups.length ? each(t.groups, group => `g:${group.id}`, groupHtml) : html`<p class="brd-list__note">没有叫这个名字的板。</p>`}</div>`;
}
function groupHtml(g) {
  const drag = g.plain ? '' : html` draggable="true" data-board-folder-drag="${g.id}"`;
  return html`<div class="brd-group" data-key="g:${g.id}">
    <div class="${cls('brd-folder', g.folded && 'is-folded', g.plain && 'is-plain')}"${drag} data-board-folder-drop="${g.id}"${g.title ? html` title="${g.title}"` : ''}>
      ${g.plain ? html`<span aria-hidden="true"></span>` : html`<button type="button" class="brd-fold" data-action="board.fold" data-arg="${g.id}" aria-expanded="${pressed(!g.folded)}" aria-label="${g.folded ? '展开' : '折叠'}「${g.name}」">${icon('chevron-down')}</button>${icon('folder')}`}
      <span class="brd-folder__name">${g.name}</span><span class="brd-count">${g.count}</span>
      ${g.plain ? html`<span aria-hidden="true"></span>` : html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-menu-btn" data-action="board.folderMenu" data-arg="${g.id}" aria-label="文件夹「${g.name}」操作" aria-haspopup="menu">${icon('more-h')}</button>`}</div>
    ${g.folded ? '' : g.boards.length ? html`<div class="brd-folder__body">${each(g.boards, board => board.id, itemHtml)}</div>`
      : g.plain ? '' : html`<p class="brd-folder__empty" data-board-folder-drop="${g.id}">空文件夹，把板拖进来</p>`}</div>`;
}
function itemHtml(b) {
  return html`<div class="${cls('brd-item', b.on && 'is-current')}" data-key="${b.id}" draggable="true" data-board-drag="${b.id}" title="${b.title}${b.time ? ` · ${b.time} 更新` : ''}">
    <button type="button" class="brd-item__main" data-board-select="${b.id}" data-action="board.open" data-arg="${b.id}"${b.on ? html` aria-current="true"` : ''}>
      <strong class="brd-item__name">${b.name}</strong><span class="brd-item__meta">${b.bits.map(bit => html`<span${bit.tone ? html` data-tone="${bit.tone}"` : ''}>${bit.text}</span>`)}</span></button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-menu-btn" data-action="board.menu" data-arg="${b.id}" aria-label="展示板「${b.name}」操作" aria-haspopup="menu">${icon('more-h')}</button></div>`;
}

function stageHead(s) {
  if (s.empty) return '';
  const p = s.pager;
  return html`<button type="button" class="brd-paper-stat" data-action="board.paperPop" aria-haspopup="dialog" title="${s.paperPages ? '查看纸面记录' : '打印并记录纸面后，这里会显示纸上已有的题'}"${off(!s.paperPages)}>
      ${icon('file')}${s.paperPages ? `纸上 ${s.paperCount} 题 · ${s.paperPages} 页` : '还没打印过'}</button>
    ${s.newCount ? html`<button type="button" class="brd-chip" data-tone="new" data-action="board.page" data-arg="new" title="翻到第一道未印的题">${s.newCount} 题未印</button>` : ''}
    ${s.changedCount ? html`<button type="button" class="brd-chip" data-tone="changed" data-action="board.changed" data-arg="${s.changedUid}" title="打印后正文改过，纸上还是旧版">${s.changedCount} 题已改动</button>` : ''}
    ${p.error ? html`<span class="brd-preview-err" title="${p.error}">预览生成失败</span>` : ''}
    <span class="brd-grow"></span><div class="brd-pager" data-board-pager>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.page" data-arg="prev" aria-label="上一页" title="上一页（←）"${off(!p.multi)}>${icon('chevron-up')}</button>
      <label>第<input class="ui-input brd-jump__input" type="number" min="1" value="${p.page}" data-board-page-input data-input="board.jump" aria-label="页码">/ ${p.pages || '—'} 页</label>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.page" data-arg="next" aria-label="下一页" title="下一页（→）"${off(!p.multi)}>${icon('chevron-down')}</button></div>
    <span class="brd-tsep" aria-hidden="true"></span>
    <div class="brd-seg brd-zoom" role="group" aria-label="缩放"><button type="button" class="brd-seg__btn" data-action="board.zoom" data-arg="fit" aria-pressed="${pressed(p.zoom === 'fit')}">适应宽度</button><button type="button" class="brd-seg__btn" data-action="board.zoom" data-arg="1" aria-pressed="${pressed(p.zoom !== 'fit')}">100%</button></div>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm brd-motion-btn" data-action="board.motionPop" aria-haspopup="dialog" aria-expanded="${pressed(!!s.motionOpen)}" title="调整纸面切换动效">${icon('sparkle')}动效</button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.layoutPop" aria-haspopup="dialog">${icon('sliders')}版式</button>`;
}
function popover(kind, v) {
  if (!kind || v.empty) return '';
  const title = kind === 'layout' ? '版式' : kind === 'motion' ? '切换动效' : '纸面记录';
  return html`<div class="brd-pop-scrim" data-action="board.closePop"></div><section class="brd-pop" data-kind="${kind}" role="dialog" aria-label="${title}">
    <header><h3>${title}</h3><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.closePop" aria-label="关闭">${icon('x')}</button></header>
    <div class="brd-pop__body">${kind === 'layout' ? inspectorLayout(v.layout) : kind === 'motion' ? inspectorMotion(v.motion) : inspectorPaper(v.paper)}</div></section>`;
}
const segBtns = (field, options, current) => options.map(([value, label]) => html`<button type="button" class="brd-seg__btn" data-value="${value}" data-action="board.seg" data-arg="${field}" aria-pressed="${pressed(current === value)}">${label}</button>`);
const check = (field, on, label, disabled = false) => html`<label class="brd-check"><input type="checkbox" data-board-print="${field}" data-change="board.printSet" data-arg="${field}"${on ? html` checked` : ''}${off(disabled)}> ${label}</label>`;

function inspectorLayout(l) {
  return html`<div class="brd-field" data-key="ratio"><label class="brd-field__label" for="bd-ins-ratio">右侧留白 <b data-board-ratio-value>${l.ratio}%</b></label>
      <input class="brd-range" id="bd-ins-ratio" type="range" min="30" max="55" step="2" value="${l.ratio}" data-board-print="note_ratio" data-input="board.printLive" data-change="board.printSet" data-arg="note_ratio" title="右侧空白区占内容区宽度的比例">
      <p class="brd-hint" data-board-live="col-width">题栏约 ${l.colWidth}px，右边留给手写</p></div>
    <div class="brd-field" data-key="gaps"><label class="brd-field__label" for="bd-ins-gaps">题间留白 <b data-board-live="gap-lines">${l.gapText}</b></label>
      <input class="ui-input brd-num" id="bd-ins-gaps" type="number" min="0" max="24" inputmode="numeric" value="${l.gap}" data-board-print="gap_lines" data-input="board.printLive" data-change="board.printSet" data-arg="gap_lines" title="每题之后空几行；单题可在题目详情里单独设置"></div>
    <div class="brd-field" data-key="answers"><span class="brd-field__label" id="bd-ins-answers">答案</span>
      <div class="brd-seg brd-seg--fill" role="group" aria-labelledby="bd-ins-answers" data-board-seg="answers">${segBtns('answers', ANSWER_OPTIONS, l.answers)}</div></div>
    <div class="brd-field" data-key="heads"><span class="brd-field__label">题头显示</span>
      <div class="brd-checks">${check('show_labels', l.showLabels, '标记')}${check('show_meta', l.showMeta, '科目 · 难度')}</div></div>
    <div class="brd-field" data-key="cut"><span class="brd-field__label" id="bd-ins-cut">切割线<span class="brd-hint">每题留白末尾的裁切提示</span></span>
      <div class="brd-seg brd-seg--fill" role="group" aria-labelledby="bd-ins-cut" data-board-seg="cut_line">${segBtns('cut_line', CUT_OPTIONS, l.cut)}</div>
      <div class="brd-checks">${check('cut_label', l.cutLabel, '线右端标「第 N 题止」', l.cut === 'none')}</div></div>
    <div class="brd-lock" data-key="lock">${check('locked', l.locked, html`${icon('lock')}锁定版式`)}<p class="brd-hint">${l.lockHint}</p></div>`;
}

function inspectorPaper(p) {
  if (!p.has) {
    return html`<p class="brd-ins-empty" data-key="none">还没有纸面记录。打印后在确认条上点「已打印，记录纸面」，之后加题就只补印新增的部分。</p>
      <p class="brd-insnote" data-key="tip">打印时选 A4、缩放 100%，不要勾「适合页面」。</p>`;
  }
  return html`<dl class="brd-paper" data-key="paper">
      <div><dt>已印</dt><dd><b>${p.count}</b> 题 · <b>${p.pages}</b> 页${p.at ? ` · ${p.at}` : ''}</dd></div>
      <div><dt>续排位置</dt><dd>第 <b>${p.cursorPage}</b> 页${p.cursorY != null ? ` ${p.cursorY}px 处` : ''}</dd></div>
      ${p.changed ? html`<div><dt>已改动</dt><dd data-tone="danger">${p.changed} 题纸上还是旧版；要更新得「打印全部」换新纸。</dd></div>` : ''}
    </dl>
    <button class="ui-btn ui-btn--ghost ui-btn--sm" type="button" data-action="board.resetPrinted" data-key="reset">清空纸面记录</button>
    <p class="brd-insnote" data-key="tip">已打印位置固定，增删与排序不会改动旧占位；「仅新增」按纸面记录续排。锁定时确认真实版式变更会清空记录，需打印全部换新纸。打印时选 A4、缩放 100%。</p>`;
}

function inspectorMotion(m) {
  const current = m || { kind: 'fade', duration: 280 };
  const options = [['fade', '渐隐渐显'], ['slide', '左右滑页'], ['paper', '抽纸'], ['none', '关闭动效']];
  return html`<div class="brd-field" data-key="motion-kind"><span class="brd-field__label">翻页方式</span>
      <div class="brd-seg brd-seg--fill brd-motion__options" role="group" aria-label="翻页方式">${options.map(([value, label]) => html`<button type="button" class="brd-seg__btn" data-action="board.motionKind" data-arg="${value}" aria-pressed="${pressed(current.kind === value)}">${label}</button>`)}</div>
      <p class="brd-hint">板切换始终使用渐隐渐显。</p></div>
    <div class="brd-field" data-key="motion-duration"><label class="brd-field__label" for="bd-motion-duration">过渡时长 <b data-board-motion-duration>${current.duration}ms</b></label>
      <input class="brd-range" id="bd-motion-duration" type="range" min="100" max="800" step="50" value="${current.duration}" data-input="board.motionDuration" aria-label="过渡时长" aria-valuetext="${current.duration} 毫秒">
      <p class="brd-hint">只影响下一次切换，系统减少动效时会自动跳过位移动画。</p></div>`;
}

// ---------- 「按标记同步」对话框的正文（detail.js 的 syncLabel 用 ui/dialog 打开；单选按 id bd-sync-N 收值） ----------
export function syncBody(defs, current) {
  return html`<div class="brd-sync" role="radiogroup" aria-label="标记">${defs.map((label, index) => html`<label class="brd-sync__opt"><input type="radio" name="bd-sync" id="bd-sync-${index}" value="${label.name}"${(label.name === current || (!current && index === 0)) ? html` checked` : ''}>${labelChip(label.name, { lg: true })}<small>${Number(label.count) || 0} 题</small></label>`)}</div>`;
}
