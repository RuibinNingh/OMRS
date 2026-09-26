/**
 * 仪表盘（P6 起的 features 页面；原 assets/dashboard.js + actions.js）。
 * - 契约：page = { id, title, mount(root, ctx) → unmount, actions }；动作命名空间 'dashboard'。
 * - 数据：统计快照读 store.data（domain/data.js 发布），Session 列表经 domain/sessions；两者变化（'data'、bus 的 'sessions'）都重绘。
 *   最近动态自己拉 /api/history（domain/history），每次数据刷新后重拉；Ledger 时区改了（bus 'ledger:tz'）只重新投影。
 * - 跳转：题库 → 切页后发 'questions:preset'；即时练习 → 'instant:load'；反馈录入 → 'feedback:session'；
 *   复习调度 → 'schedule:view'（打开「安排复习」）。页面之间不互相 import。
 */
import { morph } from '../../core/dom.js';
import { itemsOf, dueDays } from '../../domain/items.js';
import { listSessions } from '../../domain/sessions.js';
import { reloadData, lastError } from '../../domain/data.js';
import { fetchRecent, projectRecent } from '../../domain/history.js';
import { buildPlan } from './plan.js';
import * as S from './state.js';
import { view } from './view.js';

const s = S.state;
let ctl = null;

function createController(root, ctx) {
  let recentToken = 0;
  let slow = 0;
  let today = null;

  function env() {
    const data = ctx.store.get().data;
    const items = itemsOf(data);
    const now = new Date();
    const base = { items, data: data || {}, sessions: listSessions(), dueDays, today: now };
    s.plan = buildPlan(base);
    today = S.todaySummary(base);
    const err = lastError();
    return {
      ready: !!data, error: err && !items.length ? err.message : '', today, plan: s.plan, showAll: s.showAll,
      kpis: S.kpis(data), heat: S.heatmap(data?.recent_activity, now), weak: S.weakSubjects(items),
      recent: s.recent, recentRows: projectRecent(s.recent.commits, s.recent.retraction),
    };
  }

  const paint = () => morph(root, view(env()));

  async function loadRecent() {
    const token = ++recentToken;
    clearTimeout(slow);
    if (!s.recent.commits.length) {
      // 超过 300ms 还没回来才显示骨架（设计规范 §4.6）
      slow = setTimeout(() => { if (token === recentToken && ctl) { s.recent.phase = 'loading'; paint(); } }, 300);
    }
    const res = await fetchRecent();
    clearTimeout(slow);
    if (token !== recentToken) return;
    s.recent = res.ok
      ? { phase: 'ready', commits: res.commits, retraction: res.retraction, error: '' }
      : { ...s.recent, phase: 'error', error: res.error };
    if (ctl) paint();
  }

  function go(action) {
    if (!action) return;
    const { router, bus } = ctx;
    switch (action.go) {
      case 'questions': router.go('questions'); bus.emit('questions:preset', action.preset || {}); break;
      case 'instant': router.go('instant'); bus.emit('instant:load', action.preset || {}); break;
      case 'review': router.go('schedule'); bus.emit('schedule:view', 'arrange'); break;
      case 'feedback':
        router.go('feedback');
        if (action.session) bus.emit('feedback:session', action.session);
        break;
      case 'page': router.go(action.page); break;
      default: break;
    }
  }

  return {
    paint,
    loadRecent,
    run(arg) {
      const [row, order] = String(arg || '').split(':');
      const list = row === 'today' ? today?.actions : s.plan[Number(row)]?.actions;
      go(list?.[Number(order)]);
    },
    more() { s.showAll = !s.showAll; paint(); },
    weak(subject) { go({ go: 'questions', preset: { 'q-filter-subj': subject, 'q-sort': 'mastery-asc' } }); },
    page(id) { go({ go: 'page', page: id }); },
    async retry() { await reloadData(); },
    dispose() { clearTimeout(slow); recentToken += 1; },
  };
}

export const page = {
  id: 'dashboard',
  title: '仪表盘',
  mount(root, ctx) {
    ctl = createController(root, ctx);
    const offs = [
      ctx.store.subscribe(() => { ctl?.paint(); ctl?.loadRecent(); }, st => st.data),
      ctx.bus.on('sessions', () => ctl?.paint()),
      ctx.bus.on('ledger:tz', () => ctl?.paint()),
      ctx.bus.on('history:changed', () => ctl?.loadRecent()),
    ];
    ctl.paint();
    ctl.loadRecent();
    return () => { offs.forEach(off => off()); ctl?.dispose(); ctl = null; };
  },
  actions: {
    run: ({ arg }) => ctl?.run(arg),
    more: () => ctl?.more(),
    weak: ({ arg }) => ctl?.weak(arg),
    go: ({ arg }) => ctl?.page(arg),
    retry: () => ctl?.retry(),
    recentRetry: () => ctl?.loadRecent(),
  },
};
