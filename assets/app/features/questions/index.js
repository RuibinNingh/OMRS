/**
 * 题目库（features 页面，页面契约见 AI/frontend/architecture.md §3；页面说明见 AI/frontend/library.md）。
 * - 契约：page = { id, title, workbench, mount(root, ctx) → unmount, actions, keys }；动作命名空间与快捷键作用域都是 'questions'。
 * - 渲染：每次状态变化 paint() → morph(root, view(state, env))；之后 afterPaint() 补 DOM 属性（全选半选态、双滑块填充位置），
 *   画廊题面挂载点交给 domain 的 qvRender（与弹窗、反馈台同一套渲染与失效重绘），详情到齐后再重绘一次画上战绩带。
 * - 数据：题目列表、筛选语义、到期天数经 domain/items.js 读旧 core.js；写操作经 domain/question/ops.js；
 *   旧代码的 renderQ() / filterQ() 经过渡桥发 'questions:render'；仪表盘切页后发 'questions:preset' 套用预设，旧入口 questionsLoadPreset 同理。
 * - 快捷键走 core/keys.js；标记选择器（旧 labels.js 的浮层）打开时本页快捷键全部让位。
 */
import { morph } from '../../core/dom.js';
import { toast } from '../../ui/toast.js';
import { openMenu, closeMenu } from '../../ui/menu.js';
import { viewQ, qvSetContext, qvRender, qvRerenderAll, cachedDetail, mdLineBreakMode, setMdLineBreakMode } from '../../domain/question/index.js';
import { editQuestion, suspendQuestion, resumeQuestion, deleteQuestion, moveQuestion, batchSuspend, exportA4 } from '../../domain/question/ops.js';
import { allItems, filterAll, dueDays, facets, itemOf } from '../../domain/items.js';
import { listLabels, openLabelPicker, openLabelManager, pickerOpen } from '../../domain/labels/index.js';
import { boardQuickAdd, boardChooseAndAdd } from '../../domain/board/index.js';
import * as S from './state.js';
import { view } from './view.js';
import { openBatchLabels, askViewName, manageViews } from './dialogs.js';

const s = S.state;
let ctl = null;
const storage = () => { try { return globalThis.localStorage; } catch (error) { return null; } };
const split = arg => { const text = String(arg || ''); const i = text.indexOf('|'); return i < 0 ? [text, ''] : [text.slice(0, i), text.slice(i + 1)]; };
const FIELD = { 'qlb-f-subject': 'subject', 'qlb-f-category': 'category', 'qlb-f-ktag': 'ktag' };

/** 过渡桥用：仪表盘「在题库查看」等旧入口的预设（键为旧元素 id），套用前先清空所有条件，只保留视图与列设置。 */
export function loadPreset(preset) {
  s.filters = S.filtersFromFields(preset || {}, []);
  s.quick = '';
  s.live = null;
}

function createController(root, ctx) {
  let last = null;
  let frame = 0;

  function env() {
    const all = allItems();
    const itemFilters = S.toItemFilters(s.filters);
    const rows = S.postFilter(filterAll(all, itemFilters), s.quick);
    const uids = rows.map(item => item.uid);
    const liveFilters = S.withLive(s.filters, s.live);
    const liveCount = s.live ? S.postFilter(filterAll(all, S.toItemFilters(liveFilters)), s.quick).length : rows.length;
    const views = S.readViews(storage());
    const names = Object.keys(views);
    return {
      rows, uids, total: all.length, prefs: s.prefs, columns: S.columnList(s.prefs.columns), selected: s.selected, cursor: s.cursor,
      sel: S.selectionOf(s.selected, uids), counts: S.countsOf(all, dueDays), active: S.activeFilters(itemFilters),
      filterCount: S.filterCount(itemFilters), liveFilters, liveCount, facets: facets(all), labels: listLabels(),
      views: names, viewName: names.length ? S.currentViewName(views, s.filters) : '', mdMode: mdLineBreakMode(),
      dueDays, detailOf: cachedDetail,
    };
  }

  function paint() {
    if (frame) { cancelAnimationFrame(frame); frame = 0; }
    last = env();
    qvSetContext('q', last.uids);
    morph(root, view(s, last));
    afterPaint(last);
  }
  const schedule = () => { if (!frame) frame = requestAnimationFrame(() => { frame = 0; if (ctl) paint(); }); };

  function afterPaint(e) {
    const all = root.querySelector('#qlb-select-all');
    if (all) all.indeterminate = e.sel.some;
    root.querySelectorAll('.qlb-dual').forEach(el => {
      el.style.setProperty('--lo', `${el.dataset.lo}%`);
      el.style.setProperty('--hi', `${el.dataset.hi}%`);
    });
    if (e.prefs.view === 'gallery') hydrateGallery(e);
  }

  // 画廊题面：挂载点 key 变了才重新挂；首次拉到详情的卡，全部到齐后重绘一次，脚注换成战绩带
  function hydrateGallery(e) {
    const opts = S.galleryCardOpts(e.prefs);
    const jobs = [];
    root.querySelectorAll('[data-qv-host]').forEach(el => {
      if (el.dataset.qvFor === el.dataset.key) return;
      el.dataset.qvFor = el.dataset.key;
      const uid = el.dataset.uid;
      const had = !!cachedDetail(uid);
      jobs.push(qvRender(el, uid, opts).then(detail => {
        el.classList.toggle('is-clipped', el.scrollHeight - el.clientHeight > 4);
        return !had && !!detail;
      }));
    });
    if (jobs.length) Promise.all(jobs).then(fresh => { if (ctl && s.prefs.streak && fresh.some(Boolean)) schedule(); });
  }

  const savePrefs = () => S.writePrefs(storage(), s.prefs);
  const setPrefs = patch => { s.prefs = { ...s.prefs, ...patch }; savePrefs(); paint(); };
  const setFilters = (next, quick = '') => { s.filters = next; s.quick = quick; s.live = null; paint(); };
  const cursorUid = () => S.cursorOrFirst(last?.uids || [], s.cursor);

  const api = {
    paint,
    search: value => setFilters({ ...s.filters, text: String(value || '') }, S.quickAfterEdit(s.quick)),
    sort: value => setFilters({ ...s.filters, sort: value }, S.quickAfterEdit(s.quick)),
    field(id, value) { if (FIELD[id]) setFilters({ ...s.filters, [FIELD[id]]: value || '' }, S.quickAfterEdit(s.quick)); },
    seg(arg) { const [key, value] = split(arg); if (key in S.FILTER_DEFAULTS) setFilters({ ...s.filters, [key]: value }); },
    label: name => setFilters(S.toggleLabel(s.filters, name)),
    clear(arg) { const [kind, value] = split(arg); setFilters(S.clearFilter(s.filters, kind, value)); },
    clearAll: () => setFilters(S.resetFilters(s.filters)),
    quick(key) { const r = S.applyQuick(s.filters, s.quick, key); setFilters(r.filters, r.quick); },
    range(arg, value, commit) {
      const [kind, end] = split(arg);
      const r = S.RANGES[kind];
      if (!r) return;
      const cur = S.withLive(s.filters, s.live);
      const patch = S.rangeValues(kind, end === 'lo' ? value : cur[r.lo], end === 'hi' ? value : cur[r.hi], end);
      if (commit) { setFilters({ ...s.filters, ...patch }); return; }
      s.live = { ...(s.live || {}), ...patch };   // 拖动中只预览命中数与文案，松手（change）才重排列表
      paint();
    },
    view: v => { s.menu = false; setPrefs({ view: v === 'gallery' ? 'gallery' : 'table' }); },
    toggleView: () => api.view(s.prefs.view === 'table' ? 'gallery' : 'table'),
    drawer(arg) {
      s.drawer = arg === '0' ? false : arg === '1' ? true : !s.drawer;
      s.menu = false;
      paint();
      if (s.drawer) root.querySelector('#qlb-drawer select')?.focus({ preventScroll: true });
      else root.querySelector('.qlb-filter-btn')?.focus({ preventScroll: true });
    },
    menu() { s.menu = !s.menu; paint(); if (s.menu) root.querySelector('#qlb-layout button, #qlb-layout input')?.focus({ preventScroll: true }); },
    closeMenu(refocus) { if (!s.menu) return false; s.menu = false; paint(); if (refocus) root.querySelector('#qlb-layout-btn')?.focus(); return true; },
    outside(event) {
      if (!s.menu) return;
      const path = event.composedPath ? event.composedPath() : [];
      if (!path.some(node => node.classList?.contains('qlb-menu-wrap'))) api.closeMenu(false);
    },
    column: (key, on) => setPrefs({ columns: S.toggleColumn(s.prefs.columns, key, on) }),
    density: v => setPrefs({ density: v === 'compact' ? 'compact' : 'comfortable' }),
    cols: v => setPrefs({ galleryCols: S.clampCols(v) }),
    stepCols(step) { if (s.prefs.view !== 'gallery') return false; api.cols(S.stepCols(s.prefs.galleryCols, step)); return true; },
    streak: on => setPrefs({ streak: !!on }),
    galleryDetail: on => setPrefs({ galleryDetail: !!on }),
    mdMode(v) { setMdLineBreakMode(v); qvRerenderAll(); paint(); },
    resetLayout() {
      s.prefs = S.resetLayout(s.prefs);
      savePrefs();
      setMdLineBreakMode('full');
      qvRerenderAll();
      paint();
      toast('显示设置已恢复默认', { kind: 'ok' });
    },
    select(uid, on) {
      const next = new Set(s.selected);
      if (on) next.add(uid); else next.delete(uid);
      s.selected = next; s.cursor = uid;
      paint();
    },
    selectAll(on) { s.selected = S.toggleAll(s.selected, last?.uids || [], on); paint(); },
    clearSelection() { if (!s.selected.size) return false; s.selected = new Set(); paint(); return true; },
    open(uid) { if (!uid) return false; s.cursor = uid; paint(); viewQ(uid, 'q', { returnFocus: api.focusRow }); return true; },
    // 题目弹窗关闭后：游标移到最后看的那一题（翻过页就是翻到的那题），焦点交给它的行（页面已卸载则交回弹窗自己的默认）
    focusRow(uid) {
      if (ctl !== api || !uid) return null;
      if (s.cursor !== uid) { s.cursor = uid; paint(); }
      const row = root.querySelector(`[data-q-row="${CSS.escape(uid)}"]`);
      row?.scrollIntoView?.({ block: 'nearest' });
      return row;
    },
    rowClick(event) {
      const row = event.target.closest?.('[data-q-row]');
      if (!row || !root.contains(row)) return;
      if (event.target.closest('button, input, label, a, select, summary, [data-lbl-target], [data-qv-act]')) return;
      api.open(row.dataset.qRow);
    },
    async more(uid, anchor) {
      const value = await openMenu(anchor, S.rowMenuItems(itemOf(uid)), { label: `${uid} 的操作` });
      // 等这次点击冒泡完再执行：标记选择器（旧 labels.js）与选板浮层（domain/board/picker.js）在 document 上监听点击关闭，同一次点击里打开会被立刻关掉
      if (value) setTimeout(() => { if (ctl) api.rowAction(value, uid, anchor); }, 0);
    },
    rowAction(kind, uid, anchor) {
      const run = {
        view: () => api.open(uid),
        board: () => boardQuickAdd(uid, { anchor }),
        labels: () => openLabelPicker(uid, anchor),
        edit: () => editQuestion(uid),
        move: () => moveQuestion(uid),
        suspend: () => suspendQuestion(uid),
        resume: () => resumeQuestion(uid),
        delete: () => deleteQuestion(uid),
      }[kind];
      if (run) run();
    },
    batchBoard(anchor) { if (!s.selected.size) return false; boardChooseAndAdd([...s.selected], { anchor: anchor || root.querySelector('.qlb-batch') }); return true; },
    async batchLabels() { if (!s.selected.size) return false; if (await openBatchLabels([...s.selected])) paint(); return true; },
    async batchSuspend() { if (s.selected.size && await batchSuspend([...s.selected])) { s.selected = new Set(); paint(); } },
    batchExport() { if (s.selected.size) exportA4([...s.selected]); },
    async saveView() {
      s.menu = false; paint();
      const views = S.readViews(storage());
      const name = await askViewName(S.currentViewName(views, s.filters));
      if (!name) return;
      views[name] = S.snapshot(s.filters, s.prefs, mdLineBreakMode());
      S.writeViews(storage(), views);
      paint();
      toast(`已保存视图「${name}」`, { kind: 'ok' });
    },
    applyView(name) {
      const saved = S.readViews(storage())[name];
      if (!saved) return;
      const r = S.applySnapshot(saved, s.prefs);
      s.prefs = r.prefs; savePrefs();
      if (r.mdMode && r.mdMode !== mdLineBreakMode()) { setMdLineBreakMode(r.mdMode); qvRerenderAll(); }
      setFilters(r.filters);
      toast(`已切换到视图「${name}」`, { kind: 'ok' });
    },
    async manageViews() {
      s.menu = false; paint();
      const views = S.readViews(storage());
      if (!Object.keys(views).length) { toast('还没有保存的视图', { kind: 'warn' }); return; }
      const pick = await manageViews(views, { onDelete: name => { const cur = S.readViews(storage()); delete cur[name]; S.writeViews(storage(), cur); } });
      if (pick) api.applyView(pick); else if (ctl) paint();
    },
    // ── 键盘 ──
    cursorMove(delta) {
      if (!last?.uids.length) return false;
      s.cursor = S.moveCursor(last.uids, s.cursor, delta);
      paint();
      root.querySelector('[data-cursor="1"]')?.scrollIntoView?.({ block: 'nearest' });
      return true;
    },
    cursorToggle() { const uid = cursorUid(); if (!uid) return false; api.select(uid, !s.selected.has(uid)); return true; },
    cursorOpen: () => api.open(cursorUid()),
    focusSearch() { const el = root.querySelector('#qlb-search'); if (!el) return false; el.focus(); el.select(); return true; },
    escape(event) {
      if (event.target?.id === 'qlb-search') {
        if (!event.target.value) { event.target.blur(); return true; }
        event.target.value = '';
        api.search('');
        return true;
      }
      if (event.target?.closest?.('input, textarea, select')) return false;
      return api.closeMenu(true) || api.clearSelection() || (s.drawer ? (api.drawer('0'), true) : false);
    },
  };
  return api;
}

const onButton = event => !!event.target?.closest?.('button, a[href], [role="button"], [role="menuitem"], summary');
const ready = fn => (...args) => (ctl && !pickerOpen() ? fn(...args) : false);

export const page = {
  id: 'questions',
  title: '题目库',
  workbench: true,
  mount(root, ctx) {
    if (!s.loaded) { s.prefs = S.readPrefs(storage()); s.loaded = true; }
    ctl = createController(root, ctx);
    const onRootClick = event => ctl?.rowClick(event);
    const onDocClick = event => ctl?.outside(event);
    root.addEventListener('click', onRootClick);
    document.addEventListener('click', onDocClick);
    const offs = [
      ctx.bus.on('labels', () => ctl?.paint()),
      ctx.bus.on('questions:render', () => ctl?.paint()),
      ctx.bus.on('questions:preset', preset => { loadPreset(preset); ctl?.paint(); }),
      () => root.removeEventListener('click', onRootClick),
      () => document.removeEventListener('click', onDocClick),
    ];
    ctl.paint();
    return () => { offs.forEach(off => off()); closeMenu(); s.menu = false; ctl = null; };
  },
  actions: {
    search: ({ value }) => ctl?.search(value),
    sort: ({ event }) => ctl?.sort(event.target.value),
    field: ({ event }) => ctl?.field(event.target.id, event.target.value),
    seg: ({ arg }) => ctl?.seg(arg),
    label: ({ arg }) => ctl?.label(arg),
    clear: ({ arg }) => ctl?.clear(arg),
    clearAll: () => ctl?.clearAll(),
    quick: ({ arg }) => ctl?.quick(arg),
    range: ({ arg, value }) => ctl?.range(arg, value, false),
    rangeCommit: ({ arg, value }) => ctl?.range(arg, value, true),
    view: ({ arg }) => ctl?.view(arg),
    drawer: ({ arg }) => ctl?.drawer(arg),
    menu: () => ctl?.menu(),
    column: ({ el, arg }) => ctl?.column(arg, el.checked),
    density: ({ arg }) => ctl?.density(arg),
    cols: ({ arg }) => ctl?.cols(arg),
    streak: ({ el }) => ctl?.streak(el.checked),
    galleryDetail: ({ el }) => ctl?.galleryDetail(el.checked),
    mdMode: ({ arg }) => ctl?.mdMode(arg),
    resetLayout: () => ctl?.resetLayout(),
    select: ({ el, arg }) => ctl?.select(arg, el.checked),
    selectAll: ({ el }) => ctl?.selectAll(el.checked),
    clearSelection: () => ctl?.clearSelection(),
    more: ({ el, arg }) => ctl?.more(arg, el),
    batchBoard: ({ el }) => ctl?.batchBoard(el),
    batchLabels: () => ctl?.batchLabels(),
    batchSuspend: () => ctl?.batchSuspend(),
    batchExport: () => ctl?.batchExport(),
    saveView: () => ctl?.saveView(),
    applyView: ({ arg }) => ctl?.applyView(arg),
    manageViews: () => ctl?.manageViews(),
    manageLabels: () => openLabelManager(),
    goCreate: () => globalThis.__omrs?.router.go('create'),
  },
  keys: {
    '/': ready(() => ctl.focusSearch()),
    f: ready(() => { ctl.drawer(); return true; }),
    v: ready(() => { ctl.toggleView(); return true; }),
    '[': ready(() => ctl.stepCols(-1)),
    ']': ready(() => ctl.stepCols(1)),
    arrowdown: ready(() => ctl.cursorMove(1)),
    arrowup: ready(() => ctl.cursorMove(-1)),
    space: ready(event => (onButton(event) ? false : ctl.cursorToggle())),
    enter: ready(event => (onButton(event) ? false : ctl.cursorOpen())),
    b: ready(() => ctl.batchBoard()),
    l: ready(() => ctl.batchLabels()),
    escape: { inInput: true, handler: ready(event => ctl.escape(event)) },
  },
};
