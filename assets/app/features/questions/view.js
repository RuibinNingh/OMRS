/**
 * 题库页外壳模板：工作栏（搜索 / 筛选 / 排序 / 视图 / 显示设置 / 重新扫描）、计数条快捷筛选、激活条件 chips、
 * 筛选抽屉、显示设置浮层、批量条。列表本体在 list.js。只产出 html``，由 index.js 用 morph 写入 #panel-questions。
 * 约定：会出现 / 消失的块都带 data-key；表单控件的选中态写进模板（checked / selected / aria-pressed），morph 据此同步。
 * 双滑块的填充条位置不写 style=（check_ui R6），由 index.js 在每次 morph 之后设 CSS 变量。
 */
import { html, each, cls } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { select } from '../../ui/select.js';
import { badge } from '../../ui/badge.js';
import { kbd } from '../../ui/kbd.js';
import { labelChip } from '../../domain/labels/index.js';
import {
  SORTS, DUE_OPTIONS, TAG_OPTIONS, SUSPENDED_OPTIONS, RANGES, OPTIONAL_COLUMNS, COLUMN_LABELS, visibleColumns,
} from './state.js';
import { tableView, galleryView } from './list.js';

const opts = pairs => pairs.map(([value, label]) => ({ value, label }));
const pressed = on => (on ? 'true' : 'false');
const facetOptions = (values, placeholder, value) => [{ value: '', label: placeholder }, ...values.map(v => ({ value: v, label: v }))]
  .concat(value && !values.includes(value) ? [{ value, label: value }] : []);

function toolbar(s, env) {
  const f = s.filters;
  const n = env.filterCount;
  return html`<div class="qlb-bar" data-key="bar">
  <label class="qlb-search">${icon('search')}<input class="qlb-search__input" type="search" id="qlb-search" value="${f.text}" placeholder="搜索 UID、分类、知识点、标记" data-input="questions.search" autocomplete="off" aria-label="搜索题目（按 / 聚焦）" aria-keyshortcuts="/"><span class="qlb-search__kbd">${kbd('/')}</span></label>
  <button type="button" class="${cls('ui-btn', 'qlb-filter-btn', s.drawer && 'is-on')}" data-action="questions.drawer" aria-expanded="${pressed(s.drawer)}" aria-controls="qlb-drawer" title="高级筛选（F）">${icon('filter')}<span>筛选</span>${n ? badge(n, { tone: 'accent', label: `${n} 个条件` }) : ''}</button>
  <span class="qlb-sort" data-change="questions.sort">${select({ id: 'qlb-sort', label: '排序', options: opts(SORTS), value: f.sort })}</span>
  <div class="qlb-seg" role="group" aria-label="视图（V 切换）">
    <button type="button" class="ui-btn qlb-seg__btn" data-action="questions.view" data-arg="table" aria-pressed="${pressed(env.prefs.view === 'table')}" title="表格（V 切换）">${icon('table')}<span>表格</span></button>
    <button type="button" class="ui-btn qlb-seg__btn" data-action="questions.view" data-arg="gallery" aria-pressed="${pressed(env.prefs.view === 'gallery')}" title="画廊（V 切换）">${icon('grid')}<span>画廊</span></button>
  </div>
  <div class="qlb-menu-wrap">
    <button type="button" class="${cls('ui-btn', s.menu && 'is-on')}" id="qlb-layout-btn" data-action="questions.menu" aria-expanded="${pressed(s.menu)}" aria-controls="qlb-layout" title="显示设置：列 / 列数 / 密度 / 视图预设">${icon('sliders')}<span>${env.prefs.view === 'gallery' ? '列数 / 密度' : '列 / 密度'}</span></button>
    ${s.menu ? layoutMenu(env) : ''}
  </div>
  <button type="button" class="ui-btn ui-btn--icon" data-action="app.scan" aria-label="重新扫描" data-tooltip="重新扫描：把在 Obsidian 里新增或改动的题目文件收进题库">${icon('refresh')}</button>
</div>`;
}

function counts(s, env) {
  const c = env.counts;
  const quick = (key, label, value, tone) => html`<button type="button" class="qlb-quick" data-action="questions.quick" data-arg="${key}" aria-pressed="${pressed(s.quick === key)}"${value && tone ? html` data-tone="${tone}"` : ''} title="点击筛选，再点取消">${label}<b>${value}</b></button>`;
  return html`<div class="qlb-counts" data-key="counts">
  ${quick('overdue', '逾期', c.overdue, 'danger')}${quick('attack', '待攻克', c.attack)}${quick('leech', '顽固题', c.leech, 'warning')}${quick('suspended', '停用', c.suspended)}
  <span class="qlb-total" role="status">共 <b>${c.total}</b> 题 · 显示 <b>${env.rows.length}</b>${env.sel.count ? html` · 已选 <b>${env.sel.count}</b>` : ''}</span>
</div>`;
}

function chips(env) {
  if (!env.active.length) return '';
  return html`<div class="qlb-chips" data-key="chips" role="list" aria-label="当前筛选条件">
  ${each(env.active, entry => `${entry.kind}:${entry.value || ''}`, entry => html`<button type="button" class="qlb-chip" role="listitem" data-key="${entry.kind}:${entry.value || ''}" data-action="questions.clear" data-arg="${entry.kind}|${entry.value || ''}" title="移除该条件">${entry.chip ? labelChip(entry.chip) : entry.label}${icon('x')}</button>`)}
  <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-key="clear-all" data-action="questions.clearAll">清空</button>
</div>`;
}

function segs(name, label, options, value) {
  return html`<div class="qlb-f"><span class="qlb-f__label" id="qlb-f-${name}-l">${label}</span>
  <div class="qlb-segs" role="group" aria-labelledby="qlb-f-${name}-l">${options.map(([v, text]) => html`<button type="button" class="qlb-segs__btn" data-action="questions.seg" data-arg="${name}|${v}" aria-pressed="${pressed(value === v)}">${text}</button>`)}</div>
</div>`;
}

function dual(kind, label, f, unit) {
  const r = RANGES[kind];
  const lo = f[r.lo], hi = f[r.hi];
  return html`<div class="qlb-f"><span class="qlb-f__label">${label}<b>${lo} – ${hi}${unit}</b></span>
  <div class="qlb-dual" data-dual="${kind}" data-lo="${(lo - r.min) / (r.max - r.min) * 100}" data-hi="${(hi - r.min) / (r.max - r.min) * 100}">
    <span class="qlb-dual__track"></span><span class="qlb-dual__fill"></span>
    <input type="range" min="${r.min}" max="${r.max}" step="${r.step}" value="${lo}" aria-label="${label}下限" aria-valuetext="${lo}${unit}" data-input="questions.range" data-change="questions.rangeCommit" data-arg="${kind}|lo">
    <input type="range" min="${r.min}" max="${r.max}" step="${r.step}" value="${hi}" aria-label="${label}上限" aria-valuetext="${hi}${unit}" data-input="questions.range" data-change="questions.rangeCommit" data-arg="${kind}|hi">
  </div>
  <div class="qlb-dual__ends"><span>${r.min}${unit}</span><span>${r.max}${unit}</span></div>
</div>`;
}

function drawer(s, env) {
  const f = s.filters;
  const live = env.liveFilters;
  const { subjects, categories, ktags } = env.facets;
  const labels = env.labels;
  return html`<aside class="qlb-drawer" id="qlb-drawer" data-key="drawer" aria-label="题库筛选">
  <header class="qlb-drawer__head"><h3 class="qlb-drawer__title">筛选</h3><span class="qlb-match" role="status">命中 <b>${env.liveCount}</b> 题</span>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="questions.drawer" data-arg="0" aria-label="关闭筛选">${icon('x')}</button></header>
  <div class="qlb-drawer__body">
  <div class="qlb-f"><span class="qlb-f__label">科目 / 分类</span>
    <div class="qlb-f__grid" data-change="questions.field">${select({ id: 'qlb-f-subject', label: '科目', options: facetOptions(subjects, '全部科目', f.subject), value: f.subject })}${select({ id: 'qlb-f-category', label: '分类', options: facetOptions(categories, '全部分类', f.category), value: f.category })}</div></div>
  <div class="qlb-f" data-change="questions.field"><span class="qlb-f__label">知识点</span>${select({ id: 'qlb-f-ktag', label: '知识点', options: facetOptions(ktags, '全部知识点', f.ktag), value: f.ktag })}</div>
  <div class="qlb-f"><span class="qlb-f__label" id="qlb-f-labels-l">标记<span class="qlb-hint">点亮即选</span><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="questions.manageLabels">管理…</button></span>
    ${labels.length ? html`<div class="qlb-lblf" role="group" aria-labelledby="qlb-f-labels-l">${each(labels, l => l.name, l => html`<button type="button" class="qlb-lblf__btn" data-key="${l.name}" data-action="questions.label" data-arg="${l.name}" aria-pressed="${pressed(f.labels.includes(l.name))}" title="${l.name}${l.count != null ? ` · ${l.count} 题` : ''}">${labelChip(l.name)}</button>`)}</div>
      ${f.labels.length > 1 ? html`<div class="qlb-segs" data-key="mode" role="group" aria-label="标记匹配方式">${[['any', '任一命中'], ['all', '全部命中']].map(([v, t]) => html`<button type="button" class="qlb-segs__btn" data-action="questions.seg" data-arg="labelMode|${v}" aria-pressed="${pressed(f.labelMode === v)}">${t}</button>`)}</div>` : ''}`
    : html`<p class="qlb-hint" data-key="nolabels">还没有标记 · 在题目上点「＋ 标记」即可创建</p>`}
  </div>
  ${dual('diff', '难度', live, '')}
  ${dual('mastery', '熟练度', live, '%')}
  ${segs('due', '到期', DUE_OPTIONS, f.due)}
  ${segs('tag', '状态', TAG_OPTIONS, f.tag)}
  ${segs('suspended', '题目', SUSPENDED_OPTIONS, f.suspended)}
  <div class="qlb-f"><span class="qlb-f__label">视图预设<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="questions.saveView">${icon('plus')}存为视图</button></span>
    ${env.views.length ? html`<div class="qlb-views">${each(env.views, name => name, name => html`<button type="button" class="qlb-views__btn" data-key="${name}" data-action="questions.applyView" data-arg="${name}" aria-pressed="${pressed(name === env.viewName)}">${name}</button>`)}</div>` : html`<p class="qlb-hint">还没有视图预设</p>`}
  </div>
  </div>
  <footer class="qlb-drawer__foot"><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="questions.clearAll">重置全部</button><button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-action="questions.drawer" data-arg="0">完成</button></footer>
</aside>`;
}

function layoutMenu(env) {
  const p = env.prefs;
  const gallery = p.view === 'gallery';
  const cols = visibleColumns(p.columns);
  const seg = (action, value, current, options) => html`<div class="qlb-segs qlb-segs--block" role="group">${options.map(([v, t, title]) => html`<button type="button" class="qlb-segs__btn" data-action="${action}" data-arg="${v}" aria-pressed="${pressed(String(current) === String(v))}"${title ? html` title="${title}"` : ''}>${t}</button>`)}</div>`;
  const check = (action, arg, on, label) => html`<label class="qlb-pop__check"><input type="checkbox" data-change="${action}" data-arg="${arg}"${on ? html` checked` : ''}><span>${label}</span></label>`;
  return html`<div class="qlb-pop" id="qlb-layout" role="dialog" aria-label="显示设置" data-key="pop">
  ${gallery ? html`<p class="qlb-pop__title">列数<span class="qlb-pop__kbd">${kbd('[')}${kbd(']')}</span></p>
    ${seg('questions.cols', 'cols', p.galleryCols, [['0', '自动', '按卡片最小宽度自动铺满'], ...['1', '2', '3', '4', '5', '6'].map(v => [v, v])])}
    ${check('questions.streak', '', p.streak, '战绩带（脚注显示最近 8 次对错与分数）')}
    ${check('questions.galleryDetail', '', p.galleryDetail, '显示元数据（科目 / 上次复习 / 知识点）')}`
    : html`<p class="qlb-pop__title">列设置</p><div class="qlb-pop__cols">${OPTIONAL_COLUMNS.map(key => check('questions.column', key, cols.has(key), COLUMN_LABELS[key]))}</div>`}
  <p class="qlb-pop__title">${gallery ? '卡片密度' : '行密度'}</p>
  ${seg('questions.density', 'density', p.density, [['comfortable', '舒适'], ['compact', '紧凑']])}
  <p class="qlb-pop__title">题面换行</p>
  ${seg('questions.mdMode', 'md', env.mdMode, [['full', '逐行', '保留普通文本的每一处换行，选项 / 小问各占一行'], ['lean', '简略', '按 Markdown 软换行合并单个换行，只在空行处分段']])}
  <div class="qlb-pop__actions">
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="questions.saveView">存为视图…</button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="questions.manageViews">管理视图…</button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="questions.resetLayout">恢复默认显示</button>
  </div>
</div>`;
}

function batchBar(env) {
  return html`<div class="qlb-batch" data-key="batch" role="toolbar" aria-label="批量操作">
  <strong class="qlb-batch__count">${icon('check')}已选 ${env.sel.count} 题</strong>
  <button type="button" class="ui-btn ui-btn--primary ui-btn--sm" data-action="questions.batchBoard" data-board-hint>加入展示板${kbd('B')}</button>
  <button type="button" class="ui-btn ui-btn--sm" data-action="questions.batchLabels">打标记${kbd('L')}</button>
  <button type="button" class="ui-btn ui-btn--sm" data-action="questions.batchSuspend">停用 / 恢复</button>
  <button type="button" class="ui-btn ui-btn--sm" data-action="questions.batchExport">导出 A4</button>
  <span class="qlb-batch__sep" aria-hidden="true"></span>
  <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="questions.clearSelection">清空${kbd('Esc')}</button>
</div>`;
}

export function view(s, env) {
  const list = env.prefs.view === 'gallery' ? galleryView(env.rows, env) : tableView(env.rows, env);
  return html`<div class="qlb" data-key="qlb">
  <section class="qlb-card" data-key="card" aria-label="题目库">
    ${toolbar(s, env)}
    ${counts(s, env)}
    ${chips(env)}
    <div class="qlb-body" data-key="body" data-drawer="${s.drawer ? '1' : '0'}">
      <div class="qlb-main" data-key="main-${env.prefs.view}">${list}</div>
      ${s.drawer ? drawer(s, env) : ''}
    </div>
  </section>
  ${env.sel.count ? batchBar(env) : ''}
</div>`;
}
