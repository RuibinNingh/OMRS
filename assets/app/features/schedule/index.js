/**
 * 复习调度页（P6 第 3 轮起的 features 页面；原 assets/schedule.js 的页面部分）。
 * - 契约：page = { id: 'schedule', title, mount(root, ctx) → unmount, actions, keys }；动作命名空间 'schedule'。
 *   挂载点是 #panel-schedule，本页 morph 其中的 #sch-app：标签栏与三个工作区（安排复习、已有计划、全题库导出）都是原生的。
 * - 数据：Session 列表归 domain/sessions（bus 'sessions' 重绘）；计划详情 /api/session 后发先至时只认最新一次。
 * - 页面事件：'schedule:view'（仪表盘「开始复习」打开安排复习）；'schedule:open-plan'（带 Session id：切过来后打开该计划）。
 */
import { morph } from '../../core/dom.js';
import { confirm } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { listSessions, sessionsState, refreshSessions, fetchSession, deleteSession, activeSessionId } from '../../domain/sessions.js';
import { reloadData } from '../../domain/data.js';
import { viewQ, qvSetContext, invalidateQuestions } from '../../domain/question/index.js';
import { exporter as exporterState } from './exporter.js';
import { createExporter } from './exporter-ctl.js';
import { arrange as arrangeState } from './arrange.js';
import { createArrange } from './arrange-ctl.js';
import * as S from './state.js';
import { view } from './view.js';

const s = S.state;
let ctl = null;

/** 过渡桥用：旧入口 confirmScheduleV2() / loadRecommendationsV2()（冒烟测试直接调用）。页面未挂载时不做事。 */
export const arrangeApi = { confirm: () => ctl?.arr.confirm(), load: () => ctl?.arr.load() };

function createController(root, ctx) {
  const host = root.querySelector('#sch-app') || root;
  let detailSeq = 0;
  let detailModel = null;
  let arr = null;
  let exp = null;

  function env() {
    const list = listSessions();
    const { loading, error } = sessionsState();
    return { s, view: s.view, active: S.activeCount(list), plans: S.filterPlans(list, s.filter, s.search).map(S.planCard),
      selected: s.selected, detail: detailModel, loading, error, a: arrangeState, arrange: s.view === 'arrange' ? arr.env() : null, x: exporterState, exporter: s.view === 'export' ? exp.env() : null };
  }
  const paint = () => { morph(host, view(env())); if (s.view === 'arrange') arr.hydrate(); if (s.view === 'export') exp.hydrate(); };
  arr = createArrange({ ctx, root: host, paint: () => paint(), openPlan: id => openFromArrange(id) });
  exp = createExporter({ ctx, root: host, paint: () => paint() });

  function show(target, { reload = true } = {}) {
    const prev = s.view;
    Object.assign(s, S.nextView(s, target));
    paint();
    if (s.view === 'arrange' && prev !== 'arrange' && reload) arr.load();
    if (prev !== s.view) root.scrollIntoView?.({ block: 'start' });
  }

  async function open(id, { focus = true } = {}) {
    if (!id) return;
    const mine = ++detailSeq;
    // 同一个计划重拉（Session 列表刷新后）时保留当前内容，不闪骨架；换计划才清空
    if (s.selected !== id || s.detailPhase === 'error') detailModel = null;
    s.deleted = false;
    s.selected = id;
    s.detailPhase = 'loading';
    s.detailError = '';
    if (focus) s.showDetail = true;
    paint();
    const res = await fetchSession(id);
    if (mine !== detailSeq) return;
    if (res.ok && res.data) {
      s.detail = res.data;
      s.detailPhase = 'ready';
      detailModel = S.detailModel(res.data);
      qvSetContext('schedule-plan', detailModel.previewable);
    } else {
      s.detailPhase = 'error';
      s.detailError = res.error || '未知错误';
    }
    if (ctl) paint();
  }

  async function remove() {
    const id = s.selected;
    if (!id || s.deleting.has(id)) return;
    s.deleting.add(id);
    paint();
    try {
      const ok = await confirm(`删除调度「${id}」？`, { hint: '删除后该计划将从已有计划中移除，题目可重新安排复习。若已录入反馈，这些反馈也会一并撤销，并重新计算熟练度和复习日期。题目正文保留，可在历史记录中恢复该 Session。', okText: '删除调度', danger: true });
      if (!ok) return;
      const res = await deleteSession(id);
      if (!res.ok) { toast(`删除失败：${res.error}`, { kind: 'error' }); return; }
      detailSeq += 1;
      if (s.selected === id) { s.selected = ''; s.detail = null; detailModel = null; s.showDetail = false; s.deleted = true; }
      paint();
      if (activeSessionId() === id) { ctx.bus.emit('feedback:reset'); ctx.bus.emit('feedback:clear-results'); }
      toast('调度已删除，可在历史记录中恢复。', { kind: 'ok' });
      const data = await reloadData();
      await invalidateQuestions();
      const again = await refreshSessions();
      await arr.load();
      if (!data.ok || !again.ok) toast(`调度已删除，但页面刷新失败，请刷新页面：${data.error?.message || again.error}`, { kind: 'error' });
    } finally {
      s.deleting.delete(id);
      if (ctl) paint();
    }
  }

  async function openFromArrange(id) {
    s.filter = 'active';
    s.search = '';
    show('plans', { reload: false });
    await refreshSessions();
    await open(id);
  }

  return {
    paint, show, open, remove, arr, exp,
    async exportPlan(variant) {
      const id = s.selected;
      if (!id || s.exporting) return;
      s.exporting = variant;
      s.exportStatus = null;
      paint();
      const result = await exp.exportPlan(id, variant, { answers: s.answers, gap: s.gap });
      s.exporting = '';
      if (s.selected === id) s.exportStatus = result;
      if (ctl) paint();
    },
    async enter() {
      paint();
      await Promise.all([refreshSessions(), arr.load()]);
    },
    onSessions() {
      // 选中的计划已不在列表里（被删除）：清掉选中，不再去拉它的详情
      if (s.selected && !listSessions().some(x => x.session_id === s.selected) && !sessionsState().loading) {
        detailSeq += 1; s.selected = ''; s.detail = null; detailModel = null; s.showDetail = false; s.deleted = true;
      }
      paint();
      const { loading, error } = sessionsState();
      if (!loading && !error && s.selected && s.view === 'plans' && s.detailPhase !== 'loading') open(s.selected, { focus: false });
    },
    async openPlan(id) {
      s.filter = 'active';
      s.search = '';
      show('plans', { reload: false });
      await open(id);
    },
    dispose() { detailSeq += 1; arr.dispose(); exp.dispose(); },
  };
}

export const page = {
  id: 'schedule',
  title: '复习调度',
  mount(root, ctx) {
    ctl = createController(root, ctx);
    const offs = [
      ctx.bus.on('sessions', () => ctl?.onSessions()),
      ctx.bus.on('schedule:view', v => ctl?.show(v)),
      ctx.bus.on('schedule:open-plan', id => ctl?.openPlan(id)),
      ctx.bus.on('labels', () => ctl?.paint()),
      ctx.bus.on('schedule:render', () => ctl?.paint()),
      ctx.store.subscribe(() => ctl?.paint(), st => st.data),
    ];
    ctl.enter();
    return () => { offs.forEach(off => off()); ctl?.dispose(); ctl = null; };
  },
  actions: {
    view: ({ arg }) => ctl?.show(arg),
    refresh: () => refreshSessions(),
    filter: ({ value }) => { s.filter = value; ctl?.paint(); },
    search: ({ value }) => { s.search = value; ctl?.paint(); },
    open: ({ arg }) => ctl?.open(arg),
    back: () => { s.showDetail = false; ctl?.paint(); },
    feedback: ({ el }) => { if (!s.selected) return; el?.blur?.(); globalThis.__omrs?.router.go('feedback'); globalThis.__omrs?.emit('feedback:session', s.selected); },
    export: ({ arg }) => ctl?.exportPlan(arg),
    remove: () => ctl?.remove(),
    preview: ({ arg }) => viewQ(arg, 'schedule-plan'),
    answers: ({ el }) => { s.answers = !!el.checked; },
    // <details> 的展开状态存进页面状态：重绘（morph 按模板同步属性）后不会自己收起
    options: ({ event }) => { event.preventDefault(); s.options = !s.options; ctl?.paint(); },
    gap: ({ value }) => { s.gap = S.clampGap(value); },
    // ── 安排复习 ──
    reload: () => ctl?.arr.load(),
    field: ({ arg, value, event }) => ctl?.arr.field(arg, value ?? event?.target?.value),
    label: ({ arg }) => ctl?.arr.label(arg),
    clearField: ({ arg }) => ctl?.arr.clearField(arg),
    resetFilters: () => ctl?.arr.resetFilters(),
    showHidden: () => ctl?.arr.showHidden(),
    more: ({ event }) => { event.preventDefault(); ctl?.arr.more(); },
    target: ({ value }) => ctl?.arr.target(value),
    smart: () => ctl?.arr.smart(),
    toggle: ({ arg }) => ctl?.arr.toggle(arg),
    selectAll: () => ctl?.arr.selectAll(),
    clearSelection: () => ctl?.arr.clearSelection(),
    onlySelected: () => ctl?.arr.onlySelected(),
    recView: ({ arg }) => ctl?.arr.view(arg),
    confirm: () => ctl?.arr.confirm(),
    // ── 全题库导出 ──
    xfield: ({ arg, value, event }) => ctl?.exp.field(arg, value ?? event?.target?.value),
    xlabel: ({ arg }) => ctl?.exp.label(arg),
    xview: ({ arg }) => ctl?.exp.view(arg),
    xvariant: ({ arg }) => ctl?.exp.variant(arg),
    xanswers: ({ el }) => ctl?.exp.answers(el.checked),
    xgap: ({ value }) => ctl?.exp.gap(value),
    xtoggle: ({ arg }) => ctl?.exp.toggle(arg),
    xaddFiltered: () => ctl?.exp.addFiltered(),
    xremoveFiltered: () => ctl?.exp.removeFiltered(),
    xclear: () => ctl?.exp.clear(),
    xpreview: ({ arg }) => ctl?.exp.preview(arg),
    xexport: () => ctl?.exp.export(),
  },
  keys: {
    arrowleft: tabNav, arrowright: tabNav, home: tabNav, end: tabNav,
  },
};

function tabNav(event) {
  if (!ctl || !event.target?.matches?.('.schd-tab')) return false;
  const next = S.tabKey(s.view, event.key.toLowerCase());
  if (!next) return false;
  ctl.show(next);
  globalThis.document.getElementById(`sch-tab-${next}`)?.focus();
  return true;
}
