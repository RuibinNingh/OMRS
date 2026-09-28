/**
 * 展示板工作台：板列表、板头、常驻纸面和题目面板。
 * 纸面 #bd-stage 是唯一常驻的 skip 节点；详情题面也使用固定挂载点。
 */
import { html, raw, each, cls } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { empty } from '../../ui/empty.js';
import { kbd } from '../../ui/kbd.js';
import { labelChip, labelChips, labelObject, ensureColor } from '../../domain/labels/index.js';
import { ANSWER_OPTIONS, CUT_OPTIONS } from './state.js';

const pressed = on => on ? 'true' : 'false';
const off = flag => flag ? html` disabled` : '';
const flags = values => values.map(f => html`<span class="brd-flag" data-tone="${f.tone}"${f.title ? html` title="${f.title}"` : ''}>${f.text}</span>`);
const labelDots = names => (names || []).map(name => {
  const color = ensureColor(labelObject(name).color);
  return html`<i class="brd-label-dot"${color ? html` data-lbl-c="${color}"` : ''} title="${name}" aria-label="${name}"></i>`;
});

export function view(m) {
  return html`<div class="brd" data-key="brd">
    <nav class="brd-list" id="bd-list" aria-label="展示板列表" data-key="list"${m.boardsOpen ? html` data-open` : ''}>${listPane(m.tree)}</nav>
    <section class="brd-main" id="bd-content" aria-label="板内容" data-key="main">
      <header class="brd-bar" id="bd-statusbar" data-key="bar">${statusBar(m.status, m.renaming)}</header>
      <div class="brd-confirm" data-key="confirm"${!m.status.awaiting ? html` hidden` : ''}>${confirmBar(m.status)}</div>
      <div class="brd-work" data-key="work">
        <section class="brd-paper-col" aria-label="纸面预览" data-key="paper">
          <div class="brd-head" data-key="head">${stageHead(m.stage)}</div>
          <div class="brd-desk" data-key="desk"><div class="brd-stage" id="bd-stage" data-morph="skip" data-key="stage"></div></div>
        </section>
        <section class="brd-questions" aria-label="题目" data-key="questions"${m.panel === 'detail' ? html` data-detail` : ''}>
          <div class="brd-question-list" data-key="list-layer"${m.panel === 'detail' ? html` inert` : ''}>
            ${contentHead(m.content, m.linked)}
            <div class="brd-body" id="bd-content-body" data-key="body">${contentBody(m.content)}</div>
            <div class="brd-list-foot" data-key="foot">点题目看详情；拖动 ⠿ 调顺序，或按 ${kbd('Ctrl', '↑↓')}</div>
          </div>
          <aside class="brd-ins" id="bd-inspector" aria-label="题目详情" data-key="detail-layer"${m.panel !== 'detail' ? html` inert` : ''}>${inspectorItem(m.inspector.item)}</aside>
        </section>
      </div>
      <div class="brd-pop-host" data-key="pop"${!m.pop ? html` hidden` : ''}>${popover(m.pop, m.inspector)}</div>
    </section>
  </div>`;
}

function statusBar(s, renaming) {
  if (s.empty) return html`<div class="brd-title-block"><button type="button" class="ui-btn ui-btn--ghost brd-open-list" data-action="board.toggleBoards" aria-label="打开展示板列表">${icon('menu')}</button><h2 class="brd-title">没有选中展示板</h2></div>`;
  return html`<div class="brd-title-block">
      <div class="brd-title-line"><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-open-list" data-action="board.toggleBoards" aria-label="打开展示板列表">${icon('menu')}</button>
      ${renaming ? html`<input class="ui-input brd-rename" data-board-rename value="${s.name}" maxlength="120" aria-label="展示板名称（Enter 保存，Esc 取消）">`
        : html`<h2 class="brd-title" data-board-rename-target title="点击重命名">${s.name}</h2>
          <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-rename-btn" data-action="board.rename" aria-label="重命名展示板">${icon('edit')}</button>`}
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.menu" data-arg="${s.id}" aria-label="展示板更多操作" aria-haspopup="menu">${icon('more-h')}</button></div>
      <p class="brd-sub"><span>${icon('folder')}${s.folder}</span><span>${s.count} 题</span>
        <button type="button" class="brd-note-link" data-action="board.note" title="编辑备注">${s.note || '添加备注'}</button>
        <span class="brd-save-state">${s.saving ? '正在保存…' : '已保存'}</span>${s.locked ? html`<span class="brd-locked">版式已锁定</span>` : ''}</p>
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
  return html`<div class="brd-list__head"><h2 class="brd-list__title">展示板 <span class="brd-count">${t.count}</span></h2>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.newFolder" aria-label="新建文件夹">${icon('folder')}</button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.toggleBoards" aria-label="收起展示板列表">${icon('menu')}</button></div>
    <button type="button" class="ui-btn brd-new" data-action="board.create" title="新建展示板（N）">${icon('plus')}新建展示板<span>${kbd('N')}</span></button>
    <label class="brd-search">${icon('search')}<input type="search" data-board-search data-input="board.search" value="${t.query || ''}" placeholder="查找展示板" aria-label="查找展示板"></label>
    <div class="brd-tree" data-board-tree data-key="tree">${t.empty ? html`<p class="brd-list__note">还没有展示板，点上方按钮新建。</p>` : each(t.groups, group => `g:${group.id}`, groupHtml)}</div>`;
}
function groupHtml(g) {
  return html`<div class="brd-group" data-key="g:${g.id}">
    <div class="${cls('brd-folder', g.folded && 'is-folded', g.plain && 'is-plain')}" ${g.plain ? '' : html`draggable="true" data-board-folder-drag="${g.id}"`} data-board-folder-drop="${g.id}">
      ${g.plain ? html`<span class="brd-folder__spacer"></span>` : html`<button type="button" class="brd-fold" data-action="board.fold" data-arg="${g.id}" aria-expanded="${pressed(!g.folded)}" aria-label="${g.folded ? '展开' : '折叠'}「${g.name}」">${icon('chevron-down')}</button>`}
      <span class="brd-folder__name">${g.name}</span><span class="brd-count">${g.count}</span>
      ${g.plain ? '' : html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-menu-btn" data-action="board.folderMenu" data-arg="${g.id}" aria-label="文件夹「${g.name}」操作" aria-haspopup="menu">${icon('more-h')}</button>`}</div>
    ${!g.folded ? html`<div class="brd-folder__body">${each(g.boards, board => board.id, itemHtml)}</div>` : ''}</div>`;
}
function itemHtml(b) {
  return html`<div class="${cls('brd-item', b.on && 'is-current')}" data-key="${b.id}" draggable="true" data-board-drag="${b.id}">
    <button type="button" class="brd-item__main" data-board-select="${b.id}" data-action="board.open" data-arg="${b.id}"${b.on ? html` aria-current="true"` : ''}>
      <strong class="brd-item__name">${b.name}</strong><span class="brd-item__meta">${b.bits.map((bit, i) => html`${i ? ' · ' : ''}<span${bit.tone ? html` data-tone="${bit.tone}"` : ''}>${bit.text}</span>`)}</span></button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-menu-btn" data-action="board.menu" data-arg="${b.id}" aria-label="展示板「${b.name}」操作" aria-haspopup="menu">${icon('more-h')}</button></div>`;
}

function stageHead(s) {
  if (s.empty) return '';
  const p = s.pager;
  return html`<button type="button" class="brd-paper-stat" data-action="board.paperPop" aria-haspopup="dialog"${off(!s.paperPages)}>
      ${icon('file')}${s.paperPages ? `纸上 ${s.paperCount} 题 · ${s.paperPages} 页` : '还没打印过'}</button>
    ${s.newCount ? html`<button type="button" class="brd-chip" data-tone="new" data-action="board.page" data-arg="new">${s.newCount} 题未印</button>` : ''}
    ${s.changedCount ? html`<button type="button" class="brd-chip" data-tone="changed" data-action="board.changed" data-arg="${s.changedUid}">${s.changedCount} 题已改动</button>` : ''}
    <span class="brd-grow"></span><div class="brd-pager" data-board-pager>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.page" data-arg="prev" aria-label="上一页"${off(!p.multi)}>${icon('chevron-up')}</button>
      <label>第 <input class="ui-input brd-jump__input" type="number" min="1" value="${p.page}" data-board-page-input data-input="board.jump" aria-label="页码"> / ${p.pages || '—'} 页</label>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.page" data-arg="next" aria-label="下一页"${off(!p.multi)}>${icon('chevron-down')}</button></div>
    <div class="brd-seg brd-zoom" role="group" aria-label="缩放"><button type="button" class="brd-seg__btn" data-action="board.zoom" data-arg="fit" aria-pressed="${pressed(p.zoom === 'fit')}">适应宽度</button><button type="button" class="brd-seg__btn" data-action="board.zoom" data-arg="1" aria-pressed="${pressed(p.zoom !== 'fit')}">100%</button></div>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.layoutPop" aria-haspopup="dialog">${icon('sliders')}版式</button>`;
}
function contentHead(c, linked) {
  return html`<div class="brd-question-head"><h2>题目</h2><span>${c.count || 0}${c.suspended ? ` / ${c.total}` : ''}</span><span class="brd-grow"></span>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.sortMenu" aria-label="排序" aria-haspopup="menu"${off(c.total < 2)}>${icon('sort')}</button>
    <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-action="board.add" title="添加题目（A）">${icon('plus')}添加题目</button></div>
    <div class="${cls('brd-syncbar', linked.pending && 'has-pending')}">
      <button type="button" class="brd-syncbar__label" data-action="board.linkLabel" aria-haspopup="menu">${linked.name ? labelChip(linked.name) : '关联标记'}${icon('chevron-down')}</button>
      <span>${linked.name ? linked.pending ? `有 ${linked.pending} 道新题没进板` : '已同步' : '选择标记后可一键同步新题'}</span>
      <button type="button" class="ui-btn ui-btn--sm" data-action="board.sync"${off(!linked.name || !linked.pending)}>同步</button></div>
    ${c.suspended ? html`<div class="brd-warn">${c.suspended} 道题已停用，打印时会跳过<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.clean" data-arg="suspended">移出</button></div>` : ''}
    ${c.missing ? html`<div class="brd-warn" data-tone="danger">${c.missing} 道题已缺失，打印时会跳过<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.clean" data-arg="missing">移出</button></div>` : ''}
    <div class="brd-cols" aria-hidden="true"><span>#</span><span>题目 · 顺序即纸面顺序</span><span>题后留白</span></div>`;
}
function contentBody(c) {
  if (c.empty || c.kind === 'none') return html`<p class="brd-placeholder">还没有题目。点「添加题目」从题库挑选。</p>`;
  return html`<div class="brd-rows" data-board-rows>${each(c.rows, row => row.uid, rowHtml)}</div>`;
}
function rowHtml(r) {
  return html`<div class="${cls('brd-row', r.missing && 'is-missing', r.suspended && 'is-suspended')}" data-key="${r.uid}" data-board-row="${r.uid}" data-board-index="${r.index}" draggable="true" tabindex="-1"${r.selected ? html` aria-current="true"` : ''}>
    <span class="brd-row__grip" aria-hidden="true" title="拖动调整顺序">⠿</span><span class="brd-row__no">${r.no}</span>
    <div class="brd-row__main"><div class="brd-row__head"><strong class="brd-row__uid">${r.name}</strong>${flags(r.flags)}</div>
      <div class="brd-row__meta"><span>${r.category || r.subject || '未分科'}</span>${r.difficulty ? html`<span>难度 ${r.difficulty}</span>` : ''}<span class="brd-labels" data-lbl-target="${r.uid}">${labelDots(r.labels)}</span></div></div>
    <div class="${cls('brd-row-gap', !r.gap.inherited && 'is-own')}" title="${r.gap.inherited ? '跟随默认留白' : '这道题单独设置的留白'}">
      <button type="button" data-action="board.gapStep" data-arg="${r.uid}:-1" aria-label="减少一行留白"${off(r.missing || r.suspended || r.gap.lines <= 0)}>−</button>
      <span data-board-gap-view="${r.uid}">${r.gap.lines}<small>行</small></span>
      <button type="button" data-action="board.gapStep" data-arg="${r.uid}:1" aria-label="增加一行留白"${off(r.missing || r.suspended || r.gap.lines >= 48)}>+</button></div>
  </div>`;
}
function inspectorItem(it) {
  if (!it) return html`<p class="brd-placeholder">点一道题查看详情。</p>`;
  return html`<div class="brd-detail-nav"><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.back">${icon('chevron-left')}全部题目</button>
      <span class="brd-grow"></span><span>${it.no} / ${it.total}</span>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.detailStep" data-arg="-1" aria-label="上一题"${off(it.index <= 0)}>${icon('chevron-up')}</button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.detailStep" data-arg="1" aria-label="下一题"${off(it.index >= it.total - 1)}>${icon('chevron-down')}</button></div>
    <div class="brd-detail-body"><span class="brd-detail-no">纸面第 ${it.no} 题</span><h3>${it.name} ${flags(it.flags)}</h3>
      <p class="brd-detail-meta">${it.meta} · 熟练度 ${it.mastery}%</p>
      <div class="brd-detail-labels" data-lbl-target="${it.uid}">${labelChips(it.labels, { add: true })}</div>
      <section class="brd-gap-card"><div class="brd-gap-card__head"><strong>题后留白</strong><span>约 ${it.gap.long}</span></div>
        <div class="brd-gap-card__step"><button type="button" data-action="board.gapStep" data-arg="${it.uid}:-1" aria-label="减少一行留白"${off(it.gap.lines <= 0 || it.missing)}>−</button>
          <output>${it.gap.lines} 行</output><button type="button" data-action="board.gapStep" data-arg="${it.uid}:1" aria-label="增加一行留白"${off(it.gap.lines >= 48 || it.missing)}>+</button></div>
        <div class="brd-gap-card__presets" role="group" aria-label="常用留白行数">${[0, 2, 4, 6, 8].map(n => html`<button type="button" data-action="board.gapPreset" data-arg="${it.uid}:${n}" aria-pressed="${pressed(it.gap.lines === n)}">${n}</button>`)}<span>行</span></div>
        ${it.own === '' ? html`<p>跟随板的默认留白 ${it.inherited} 行；改动后只影响这道题。</p>`
          : html`<p>单独设置 · <button type="button" class="brd-text-btn" data-action="board.inherit">改回默认 ${it.inherited} 行</button></p>`}
        ${it.note ? html`<p class="brd-gap-card__note">${it.note}</p>` : ''}</section>
      <section class="brd-question-preview"><h4>题面、答案与练习记录</h4><div data-morph="skip" data-key="qv:${it.uid}" data-qv-host data-uid="${it.uid}"></div></section>
    </div><div class="brd-detail-foot"><button type="button" class="ui-btn ui-btn--sm" data-action="board.openItem" data-arg="${it.uid}">打开题目</button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.remove" data-arg="${it.uid}">从板中移除</button></div>`;
}
function popover(kind, v) {
  if (!kind || v.empty) return '';
  return html`<div class="brd-pop-scrim" data-action="board.closePop"></div><section class="brd-pop" role="dialog" aria-label="${kind === 'layout' ? '版式' : '纸面记录'}">
    <header><h3>${kind === 'layout' ? '版式' : '纸面记录'}</h3><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.closePop" aria-label="关闭">${icon('x')}</button></header>
    <div class="brd-pop__body">${kind === 'layout' ? inspectorLayout(v.layout) : inspectorPaper(v.paper)}</div></section>`;
}
const segBtns = (field, options, current) => options.map(([value, label]) => html`<button type="button" class="brd-seg__btn" data-value="${value}" data-action="board.seg" data-arg="${field}" aria-pressed="${pressed(current === value)}">${label}</button>`);
const check = (field, on, label, disabled = false) => html`<label class="brd-check"><input type="checkbox" data-board-print="${field}" data-change="board.printSet" data-arg="${field}"${on ? html` checked` : ''}${off(disabled)}> ${label}</label>`;

function inspectorLayout(l) {
  return html`<div class="brd-field" data-key="ratio"><label class="brd-field__label" for="bd-ins-ratio">右侧留白 <b data-board-ratio-value>${l.ratio}%</b></label>
      <input class="brd-range" id="bd-ins-ratio" type="range" min="30" max="55" step="2" value="${l.ratio}" data-board-print="note_ratio" data-input="board.printLive" data-change="board.printSet" data-arg="note_ratio" title="右侧空白区占内容区宽度的比例">
      <p class="brd-hint" data-board-live="col-width">题栏约 ${l.colWidth}px，右边留给手写</p></div>
    <div class="brd-field" data-key="gaps"><label class="brd-field__label" for="bd-ins-gaps">题间留白 <b data-board-live="gap-lines">${l.gapText}</b></label>
      <input class="ui-input brd-num" id="bd-ins-gaps" type="number" min="0" max="24" inputmode="numeric" value="${l.gap}" data-board-print="gap_lines" data-input="board.printLive" data-change="board.printSet" data-arg="gap_lines" title="每题之后空几行；单题可在上面的「选中的题」里覆盖"></div>
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
    return html`<p class="brd-ins-empty" data-key="none">还没有纸面记录。打印之后点状态条上的「记录纸面」，之后加题就只补印新增的部分。</p>
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

// ---------- 「按标记同步」对话框的正文（detail.js 的 syncLabel 用 ui/dialog 打开；单选按 id bd-sync-N 收值） ----------
export function syncBody(defs, current) {
  return html`<div class="brd-sync" role="radiogroup" aria-label="标记">${defs.map((label, index) => html`<label class="brd-sync__opt"><input type="radio" name="bd-sync" id="bd-sync-${index}" value="${label.name}"${(label.name === current || (!current && index === 0)) ? html` checked` : ''}>${labelChip(label.name, { lg: true })}<small>${Number(label.count) || 0} 题</small></label>`)}</div>`;
}
