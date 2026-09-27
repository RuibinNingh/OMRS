/**
 * 展示板页模板（P7 第 5 轮起，只产出 html``）：页面骨架、状态条、左栏树、舞台头（舞台栏 / 翻页 / 警告）；第 6 轮起
 * 列表 / 画廊（#bd-content-body）与检查器（#bd-inspector）也在这里。
 * 骨架里只有常驻预览 iframe 的舞台 #bd-stage 是 data-morph="skip"；画廊卡的题面挂载点也是 skip（key 编码 uid，qvRender 填）。
 * 每层的子节点个数与顺序固定（可有可无的块都包在 .brd-head 里），morph 永远不必挪动舞台——iframe 被 insertBefore
 * 移动一次就整份重载，近 1MB 的内联字体要重新解码。
 * 测试钩子沿用旧的 data-board-* 属性（主行动按钮、打印范围、视图、翻页条与页码框、板行、条目行、检查器字段与分段）；
 * 拖拽契约（features/board/drag.js）：data-board-drag、data-board-folder-drag、data-board-folder-drop、data-board-row / data-board-index。
 */
import { html, raw, each, cls } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { empty } from '../../ui/empty.js';
import { kbd } from '../../ui/kbd.js';
import { labelChip, labelChips } from '../../domain/labels/index.js';
import { qvGalleryIdHtml } from '../../domain/question/index.js';
import { VIEWS, ANSWER_OPTIONS, CUT_OPTIONS } from './state.js';

const pressed = on => (on ? 'true' : 'false');
const off = flag => (flag ? html` disabled` : '');

export function view(m) {
  return html`<div class="brd" data-key="brd">
  <section class="brd-bar" id="bd-statusbar" aria-label="打印状态" data-key="bar">${statusBar(m.status, m.renaming)}</section>
  <div class="brd-layout" data-key="layout">
    <nav class="ui-card brd-col brd-list" id="bd-list" aria-label="展示板列表" data-key="list">${listPane(m.tree)}</nav>
    <section class="ui-card brd-col brd-main" id="bd-content" aria-label="板内容" data-key="main">
      <div class="brd-head" data-key="head">${stageHead(m.stage)}</div>
      <div class="brd-stage" id="bd-stage" data-morph="skip" data-key="stage" hidden></div>
      <div class="brd-body" id="bd-content-body" data-key="body">${contentBody(m.content)}</div>
    </section>
    <aside class="ui-card brd-col brd-ins" id="bd-inspector" aria-label="检查器" data-key="ins"${m.inspector.empty ? html` hidden` : ''}>${inspector(m.inspector)}</aside>
  </div>
</div>`;
}

// ---------- 状态条 ----------
function statusBar(s, renaming) {
  if (s.empty) {
    return html`<p class="brd-intro" data-key="intro">左题右空的活页「错题集」：随时加题、重排、打印；打印过后只补印新增的题，接在原纸空白处。
      <span class="brd-keys">快捷键 ${kbd('N')} 新建 · ${kbd('A')} 添加 · ${kbd('P')} 打印预览 · ${kbd('↑↓')} 选行 · ${kbd('Ctrl', '↑↓')} 移动 · ${kbd('Delete')} 移除</span></p>`;
  }
  return html`<div class="brd-id" data-key="id">
      <div class="brd-id__line">${renaming
    ? html`<input class="ui-input brd-rename" data-board-rename value="${s.name}" maxlength="120" autocomplete="off" aria-label="展示板名称（Enter 保存，Esc 取消）">`
    : html`<h2 class="brd-title" data-board-rename-target title="双击重命名">${s.name}</h2><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-rename-btn" data-action="board.rename" aria-label="重命名展示板" title="重命名">${icon('edit')}</button>`}</div>
      <p class="brd-sub">${s.count} 题${s.subjects ? ` · ${s.subjects}` : ''}${s.note ? ` · ${s.note}` : ''}${s.locked ? html` · <span class="brd-locked">版式已锁定</span>` : ''}</p>
    </div>
    <div class="brd-chips" data-key="chips">${s.chips.map(chip => html`<span class="brd-chip" data-tone="${chip.kind}">${chip.text}</span>`)}</div>
    <p class="brd-why" data-key="why">${s.why}</p>
    <div class="brd-seg" role="group" aria-label="打印范围" data-board-modes data-key="modes">
      <button type="button" class="brd-seg__btn" data-board-mode="all" data-action="board.mode" data-arg="all" aria-pressed="${pressed(s.scope === 'all')}">打印全部</button>
      <button type="button" class="brd-seg__btn" data-board-mode="new" data-action="board.mode" data-arg="new" aria-pressed="${pressed(s.scope === 'new')}"${off(!s.canNew)}>仅新增${s.newCount ? `（${s.newCount}）` : ''}</button>
    </div>
    <button type="button" class="ui-btn ui-btn--primary brd-primary" data-board-primary data-action="board.primary" data-arg="${s.action.type}" title="打印预览（P）" data-key="primary">${s.action.label}</button>
    <div class="brd-more" data-key="more">
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.export" title="下载自包含 HTML，离线打印">${icon('download')}<span class="ui-btn__label">下载 HTML</span></button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.regen" aria-label="按最新正文重新生成纸面" title="题目正文在别处改过、纸面还是旧的时，强制重新生成">${icon('refresh')}</button>
    </div>`;
}

// ---------- 左栏：文件夹 → 板 两级树 ----------
function listPane(t) {
  if (t.empty) {
    return html`<div data-key="empty">${empty({
      icon: 'bookmark', title: '还没有展示板', compact: true,
      hint: '把考前必看的题集中到一个板里，随时加题、重排，打印成左题右空的活页纸；之后新增的题还能只补印一页。',
      action: { label: '新建第一个展示板', action: 'board.create', size: 'sm' },
    })}</div>`;
  }
  return html`<div class="brd-list__head" data-key="head">
      <h2 class="brd-list__title">展示板<span class="brd-count">${t.count}</span></h2>
      <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-action="board.newMenu" aria-haspopup="menu" title="新建（N）">${icon('plus')}<span class="ui-btn__label">新建</span>${icon('chevron-down')}</button>
    </div>
    <div class="brd-tree" data-board-tree data-key="tree">${each(t.groups, group => `g:${group.id}`, groupHtml)}</div>
    <p class="brd-list__note" data-key="note">板里存的是题目引用，题目改了重印即最新；纸面标题固定为「错题集」。</p>`;
}

function groupHtml(g) {
  const body = g.boards.length ? html`<div class="brd-folder__body">${each(g.boards, board => board.id, itemHtml)}</div>`
    : (g.plain || g.folded ? '' : html`<div class="brd-folder__body"><p class="brd-folder__empty">把板拖进来</p></div>`);
  if (g.plain) {
    return html`<div class="brd-group" data-key="g:">
      <div class="brd-folder is-plain" data-board-folder-drop=""><span class="brd-folder__name">未归档</span><span class="brd-count">${g.count}</span></div>${body}</div>`;
  }
  return html`<div class="brd-group" data-key="g:${g.id}">
    <div class="${cls('brd-folder', g.folded && 'is-folded')}" draggable="true" data-board-folder-drop="${g.id}" data-board-folder-drag="${g.id}" title="${g.title}">
      <button type="button" class="brd-fold" data-action="board.fold" data-arg="${g.id}" aria-expanded="${pressed(!g.folded)}" aria-label="${g.folded ? '展开' : '折叠'}「${g.name}」">${icon('chevron-down')}</button>
      <span class="brd-folder__name">${g.name}</span>
      ${g.newCount ? html`<span class="brd-plus" title="这组里有 ${g.newCount} 题还没印上纸">+${g.newCount}</span>` : ''}
      <span class="brd-count">${g.count}</span>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-menu-btn" data-action="board.folderMenu" data-arg="${g.id}" aria-haspopup="menu" aria-label="文件夹「${g.name}」操作">${icon('more-h')}</button>
    </div>${body}</div>`;
}

function itemHtml(b) {
  return html`<div class="${cls('brd-item', b.on && 'is-current')}" data-key="${b.id}" draggable="true" data-board-drag="${b.id}" title="${b.title}">
    <button type="button" class="brd-item__main" data-board-select="${b.id}" data-action="board.open" data-arg="${b.id}"${b.on ? html` aria-current="true"` : ''}>
      <span class="brd-item__name">${b.name}</span>
      <span class="brd-item__meta">${b.bits.map((bit, i) => html`${i ? ' · ' : ''}<span${bit.tone ? html` data-tone="${bit.tone}"` : ''}>${bit.text}</span>${bit.plus ? html` <span data-tone="new">${bit.plus}</span>` : ''}`)}</span>
    </button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-menu-btn" data-action="board.menu" data-arg="${b.id}" aria-haspopup="menu" aria-label="展示板「${b.name}」操作">${icon('more-h')}</button>
  </div>`;
}

// ---------- 舞台头：视图只决定「怎么看」，改版式或打印范围的控件不在这里 ----------
function stageHead(s) {
  if (s.empty) return html`<p class="brd-placeholder" data-key="none">请选择或新建一个展示板。</p>`;
  return html`<div class="brd-stagebar" data-key="stagebar">
      <div class="brd-seg" role="group" aria-label="视图">${VIEWS.map(([key, label]) => html`<button type="button" class="brd-seg__btn" data-board-view="${key}" data-action="board.view" data-arg="${key}" aria-pressed="${pressed(s.view === key)}">${label}</button>`)}</div>
      <span class="brd-note">${s.count} 题 · 顺序即纸面顺序</span>
      <span class="brd-grow"></span>
      <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-action="board.add" title="添加题目（A）">${icon('plus')}<span class="ui-btn__label">添加题目</span></button>
      <button type="button" class="ui-btn ui-btn--sm" data-action="board.sync">${icon('tag')}<span class="ui-btn__label">按标记同步</span></button>
      <button type="button" class="ui-btn ui-btn--sm" data-action="board.sortMenu" aria-haspopup="menu">${icon('sort')}<span class="ui-btn__label">排序</span></button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.clear"${off(!s.count)}>清空</button>
    </div>
    ${s.view === 'paper' ? pager(s.pager) : ''}
    ${s.missing ? html`<div class="brd-warn" data-tone="danger" data-key="warn-missing">${icon('alert-triangle')}<span>${s.missing} 道题已缺失（文件被删或无法解析），导出时会跳过。</span><button type="button" class="ui-btn ui-btn--sm" data-action="board.clean" data-arg="missing">清理缺失条目</button></div>` : ''}
    ${s.suspended ? html`<div class="brd-warn" data-key="warn-suspended">${icon('alert-triangle')}<span>${s.suspended} 道题已停用，导出时会跳过。</span><button type="button" class="ui-btn ui-btn--sm" data-action="board.clean" data-arg="suspended">移出停用题</button></div>` : ''}`;
}

function pager(p) {
  return html`<div class="brd-pager" data-board-pager data-key="pager">
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.page" data-arg="prev" aria-label="上一页" title="上一页（←）"${off(!p.multi)}>${icon('chevron-left')}</button>
    <label class="brd-jump">第 <input class="ui-input brd-jump__input" type="number" min="1" value="${p.page}" data-board-page-input data-input="board.jump" aria-label="页码"> / ${p.pages || '—'} 页</label>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.page" data-arg="next" aria-label="下一页" title="下一页（→）"${off(!p.multi)}>${icon('chevron-right')}</button>
    ${p.jumpNew ? html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="board.page" data-arg="new" title="跳到第一道还没印在纸上的题">⚑ 跳到新增</button>` : ''}
    <span class="brd-est">${estimate(p)}</span>
    <div class="brd-seg" role="group" aria-label="缩放">
      <button type="button" class="brd-seg__btn" data-action="board.zoom" data-arg="fit" aria-pressed="${pressed(p.zoom === 'fit')}">适应宽度</button>
      <button type="button" class="brd-seg__btn" data-action="board.zoom" data-arg="1" aria-pressed="${pressed(p.zoom !== 'fit')}">100%</button>
    </div>
  </div>`;
}

function estimate(p) {
  if (p.error) return html`<span data-tone="warn">无法生成预览：${p.error}</span>`;
  const e = p.estimate;
  if (!e) return html`<span class="brd-busy">正在排版…</span>`;
  const warn = e.warnings ? html` · <span data-tone="warn">⚠ ${e.warnings} 处切图告警</span>` : '';
  if (e.scope === 'new') {
    return html`本次补印 <b>${e.rendered}</b> 页（${e.range}）${e.partial ? `，第 ${e.partial} 页印在原纸上` : ''} · 打印后整板共 <b>${e.pages}</b> 页${warn}`;
  }
  return html`预计 <b>${e.pages}</b> 页 · A4 纵向 · 左右 10 / 上下 12mm${warn}`;
}

// ---------- 列表 / 画廊：顺序即纸面顺序；只读回显留白，改它在检查器 ----------
const flagList = flags => flags.map(f => html`<span class="brd-flag" data-tone="${f.tone}"${f.title ? html` title="${f.title}"` : ''}>${f.text}</span>`);

function contentBody(c) {
  if (c.kind === 'none') return '';
  if (c.empty) {
    return html`<div data-key="empty-${c.kind}">${empty({
      icon: 'plus', title: '板里还没有题目', compact: true,
      hint: '点「添加题目」筛选加入，或在题库勾选后批量加入；题目弹窗、反馈判错、录入题目后也有「加入展示板」。',
      action: { label: '添加题目', action: 'board.add', size: 'sm' },
    })}</div>`;
  }
  if (c.kind === 'gallery') return html`<div class="brd-gallery" data-key="gallery">${each(c.rows, row => row.uid, galleryCard)}</div>`;
  return html`<div class="brd-rows" data-board-rows data-key="rows">${each(c.rows, row => row.uid, rowHtml)}</div>`;
}

function rowMeta(r) {
  if (r.missing) return html`<span data-tone="danger">题目已删除或无法解析；导出时跳过</span>`;
  return html`<span>${r.subject}${r.category ? ` · ${r.category}` : ''}</span>${r.difficulty ? html`<span>难度 ${r.difficulty}</span>` : ''}<span>熟练 ${r.mastery}%</span>${r.due ? html`<span${r.due.tone ? html` data-tone="${r.due.tone}"` : ''}>${r.due.text}</span>` : ''}`;
}

function rowHtml(r) {
  return html`<div class="${cls('brd-row', r.missing && 'is-missing', r.suspended && 'is-suspended')}" data-key="${r.uid}" data-board-row="${r.uid}" data-board-index="${r.index}" draggable="true" tabindex="-1"${r.selected ? html` aria-current="true"` : ''} title="双击或 Enter 打开题目">
    <span class="brd-row__grip" aria-hidden="true" title="拖拽排序（Ctrl+↑/↓ 也可）">⠿</span><span class="brd-row__no">${r.no}</span>
    <div class="brd-row__main"><span class="brd-row__head"><strong class="brd-row__uid">${r.name}</strong>${flagList(r.flags)}<span class="q-label-cell brd-labels" data-lbl-target="${r.uid}">${labelChips(r.labels, { add: true })}</span></span>
      <span class="brd-row__meta">${rowMeta(r)}</span></div>
    <div class="brd-row__acts">
      <button type="button" class="${cls('brd-gapchip', !r.gap.inherited && 'is-own')}" data-action="board.focusGap" data-arg="${r.uid}" data-board-gap-view="${r.uid}" title="点一下到右栏改这道题的留白">${r.gap.text}</button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm brd-row__open" data-action="board.openItem" data-arg="${r.uid}"${off(r.missing)} title="打开题目详情">详情</button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon brd-row__x" data-action="board.remove" data-arg="${r.uid}" aria-label="从板中移除 ${r.name}" title="从板中移除（Delete）">${icon('x')}</button>
    </div>
  </div>`;
}

// 画廊卡：题面与题库画廊同一套 qview 渲染（挂载点 skip，key 只编码 uid：换题才换新挂载点）
function galleryCard(r) {
  return html`<article class="${cls('brd-gcard', r.missing && 'is-missing', r.suspended && 'is-suspended')}" data-key="${r.uid}" data-board-row="${r.uid}" data-board-index="${r.index}" tabindex="-1"${r.selected ? html` aria-current="true"` : ''} title="点击选中，双击打开题目">
  <header class="brd-gcard__head"><span class="brd-gcard__no">${r.no}</span><span class="brd-gcard__id">${raw(qvGalleryIdHtml(r.uid, r.category))}</span>
    <span class="brd-gcard__flags">${flagList(r.flags)}</span>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="board.locate" data-arg="${r.uid}" aria-label="回到纸面上 ${r.name}" title="回到纸面上这道题"${off(r.missing || r.suspended)}>${icon('target')}</button></header>
  ${r.missing
    ? html`<p class="brd-gcard__preview brd-gcard__gone" data-key="gone">题目已删除或无法解析，导出时会跳过</p>`
    : html`<div class="brd-gcard__preview" data-key="pv:${r.uid}" data-morph="skip" data-qv-host data-uid="${r.uid}"></div>`}
  <footer class="brd-gcard__foot"><span>${r.subject}${r.category ? ` · ${r.category}` : ''}</span>${r.difficulty ? html`<span>难度 ${r.difficulty}</span>` : ''}
    <span data-board-gap-view="${r.uid}" title="这道题之后留白 ${r.gap.lines} 行；改它在右栏检查器">${r.gap.text}</span>
    <span class="q-label-cell brd-labels" data-lbl-target="${r.uid}">${labelChips(r.labels, { add: true, max: 3 })}</span></footer>
</article>`;
}

// ---------- 检查器：选中的题 / 版式 / 纸面记录；「一个设置只有一个入口」 ----------
function inspector(v) {
  if (v.empty) return '';
  return html`<section class="brd-sec" data-sec="item" data-key="item" aria-labelledby="bd-ins-item-t">
    <header class="brd-sec__head"><h3 class="brd-sec__title" id="bd-ins-item-t">选中的题</h3>${v.selected ? '' : html`<span>未选中</span>`}</header>${inspectorItem(v.item)}</section>
  <section class="brd-sec" data-sec="layout" data-key="layout" aria-labelledby="bd-ins-layout-t">
    <header class="brd-sec__head"><h3 class="brd-sec__title" id="bd-ins-layout-t">版式</h3><span>改完纸面立刻重排</span></header>${inspectorLayout(v.layout)}</section>
  <section class="brd-sec" data-sec="paper" data-key="paper" aria-labelledby="bd-ins-paper-t">
    <header class="brd-sec__head"><h3 class="brd-sec__title" id="bd-ins-paper-t">纸面记录</h3></header>${inspectorPaper(v.paper)}</section>`;
}

function inspectorItem(it) {
  if (!it) return html`<p class="brd-ins-empty" data-key="none">在纸面、列表或画廊里点一道题，它的设置就出现在这里。三个视图点出来的是同一处。</p>`;
  return html`<div class="brd-insq" data-key="q:${it.uid}"><span class="brd-insq__no">第 ${it.no} 题</span><strong class="brd-insq__uid" title="${it.name}">${it.name}</strong>${flagList(it.flags)}</div>
    <p class="brd-insq__meta" data-key="meta">${it.meta}</p>
    <div class="brd-field" data-key="gap"><label class="brd-field__label" for="bd-ins-gap">题后留白 <b data-board-live="item-gap">${it.gap.long}</b></label>
      <div class="brd-gapline"><input class="ui-input brd-num" id="bd-ins-gap" type="number" min="0" max="48" inputmode="numeric" value="${it.own}" placeholder="${it.inherited}" data-board-inspect-gap="${it.uid}" data-input="board.gapLive" data-change="board.gapSet" title="留空 = 继承板设置的 ${it.inherited} 行">
        ${it.own === '' ? html`<span class="brd-hint">留空 = 继承板设置</span>` : html`<button class="ui-btn ui-btn--ghost ui-btn--sm" type="button" data-action="board.inherit" title="改回继承板的全局留白">改回继承</button>`}</div></div>
    <div class="brd-insacts" data-key="acts">
      <button class="ui-btn ui-btn--sm" type="button" data-action="board.inspectLocate" title="翻到这道题所在的页">${icon('target')}<span class="ui-btn__label">跳到这道题</span></button>
      <button class="ui-btn ui-btn--ghost ui-btn--sm" type="button" data-action="board.openItem" data-arg="${it.uid}"${off(it.missing)}>打开题目</button>
      <button class="ui-btn ui-btn--ghost ui-btn--sm" type="button" data-action="board.remove" data-arg="${it.uid}">从板中移除</button>
    </div>
    ${it.note ? html`<p class="brd-insnote" data-key="note">${it.note}</p>` : ''}`;
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
