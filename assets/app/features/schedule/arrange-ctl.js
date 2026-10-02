import { questionKey, questionRefs } from '../../domain/question/ref.js';
/**
 * 复习调度 ·「安排复习」的控制器：拉推荐（后发先至只认最新）、筛选与选择、生成计划、画廊题面懒加载。
 * 由 index.js 在页面挂载时创建；状态在 arrange.js 的模块单例里（离开页面再回来，筛选与选择都还在，与旧页一致）。
 */
import { get, post } from '../../core/api.js';
import { toast } from '../../ui/toast.js';
import { itemsOf, facets, filterAll, dueDays } from '../../domain/items.js';
import { listLabels } from '../../domain/labels/index.js';
import { openSessions } from '../../domain/sessions.js';
import { qvRender, qvSetContext, QV_CARD_OPTS } from '../../domain/question/index.js';
import * as A from './arrange.js';

const a = A.arrange;
const storage = () => { try { return globalThis.localStorage; } catch (error) { return null; } };

export function createArrange({ ctx, root, paint, openPlan }) {
  if (!a.viewLoaded) { a.view = A.readView(storage()); a.viewLoaded = true; }
  let observer = null;
  const mounted = new WeakSet();   // 已挂 qview 的画廊挂载点（不写属性：morph 会同步挂载点自身的属性）

  function env() {
    const all = (a.data || []).filter(Boolean);
    const filtered = A.filterCandidates(all, a.filters, filterAll);
    const problem = A.filterError(A.sharedFilters(a.filters));
    const shown = a.onlySelected ? filtered.filter(i => a.selected.has(questionKey(i))) : filtered;
    qvSetContext('schedule-pick', shown.map(i => i.uid));
    const items = itemsOf(ctx.store.get().data).filter(i => !i.suspended);
    return {
      facets: facets(items), labels: listLabels(), chips: A.chips(a.filters), dueDays, gallery: a.view === 'gallery',
      filtered, shown, problem, hidden: A.hiddenSelected(a.selected, filtered), minutes: A.estimateMinutes([...a.selected.values()]),
      empty: A.emptyState(a, problem, openSessions().length),
      suggestDisabled: a.loading || !!a.error || !!problem || !filtered.length,
      confirmDisabled: !a.selected.size || a.loading || !!a.error || a.submitting,
    };
  }

  /** 画廊题面：进入视口（提前 240px）才挂 qview；不支持观察器时全部挂上。已挂过的不重复挂。 */
  function hydrate() {
    observer?.disconnect();
    const hosts = [...root.querySelectorAll('[data-preview-uid]')].filter(el => !mounted.has(el));
    const mount = el => { if (!el.isConnected || mounted.has(el)) return; mounted.add(el); qvRender(el, el.dataset.previewUid, { ...QV_CARD_OPTS, clamp: 8 }); };
    if (typeof IntersectionObserver === 'undefined') { hosts.forEach(mount); return; }
    observer = new IntersectionObserver(entries => entries.forEach(e => { if (e.isIntersecting) { observer.unobserve(e.target); mount(e.target); } }), { rootMargin: '240px' });
    hosts.forEach(el => observer.observe(el));
  }

  async function load() {
    const mine = ++a.seq;
    a.loading = true;
    a.error = '';
    paint();
    const res = await get('/api/recommend?due_count=1000&prof_count=1000');
    if (mine !== a.seq) return;
    a.loading = false;
    if (res.ok) {
      const merged = A.mergeLoaded(res.data, a.selected);
      a.data = merged.data;
      a.selected = merged.selected;
      if (merged.removed) toast(`${merged.removed} 道已选题已不可安排，已移出选择。其余选择已保留。`, { kind: 'warn' });
    } else {
      a.error = res.error?.message || '未知错误';
    }
    paint();
  }

  async function confirm() {
    if (a.submitting || a.loading || a.error || !a.selected.size) return;
    a.submitting = true;
    a.notice = '';
    paint();
    const values = [...a.selected.values()];
    const subjects = new Set(values.map(i => i.subject));
    const res = await post('/api/confirm-schedule', { selected: values.map(i => ({ ...questionRefs([i])[0], source: i._source })), persist: true, subject: subjects.size === 1 ? [...subjects][0] : null });
    if (res.ok) {
      a.selected = new Map();
      a.onlySelected = false;
      a.submitting = false;
      await openPlan(res.data?.session_id);
      await load();
      toast(`已生成 ${res.data?.count ?? values.length} 题的复习计划`, { kind: 'ok' });
    } else {
      a.submitting = false;
      a.notice = `生成失败：${res.error?.message || '未知错误'}。选择已保留；若题目已被其他计划占用，请刷新推荐。`;
      paint();
    }
  }

  const set = (fn) => { fn(); paint(); };
  return {
    env, hydrate, load, confirm,
    field: (key, value) => set(() => { a.filters = { ...a.filters, [key]: value ?? '' }; a.notice = ''; }),
    label: name => set(() => { const has = a.filters.labels.includes(name); a.filters = { ...a.filters, labels: has ? a.filters.labels.filter(n => n !== name) : [...a.filters.labels, name] }; }),
    clearField: key => set(() => { a.filters = A.clearField(a.filters, key); }),
    resetFilters: () => set(() => { a.filters = A.resetFilters(a.filters); a.onlySelected = false; }),
    showHidden: () => set(() => { a.filters = A.resetFilters(a.filters); a.onlySelected = true; }),
    more: () => set(() => { a.more = !a.more; }),
    target: value => { a.target = String(value ?? ''); },
    smart: () => set(() => { const picked = A.smartPick(env().filtered, a.target); if (picked) { a.selected = picked; a.onlySelected = false; } }),
    toggle: uid => set(() => { if (a.selected.has(uid)) a.selected.delete(uid); else { const item = (a.data || []).find(i => questionKey(i) === uid); if (item) a.selected.set(uid, item); } }),
    selectAll: () => set(() => { if (a.loading || a.error) return; env().filtered.forEach(i => a.selected.set(questionKey(i), i)); }),
    clearSelection: () => set(() => { a.selected = new Map(); a.onlySelected = false; }),
    onlySelected: () => set(() => { a.onlySelected = !a.onlySelected; }),
    view: v => set(() => { a.view = v === 'gallery' ? 'gallery' : 'list'; A.writeView(storage(), a.view); }),
    dispose: () => { observer?.disconnect(); a.seq += 1; a.loading = false; },
  };
}
