import { questionKey, questionRefs } from '../../domain/question/ref.js';
/**
 * 复习调度两处导出的控制器：筛选与已选、画廊题面懒加载、参数面板、下载后记忆。
 * 状态在 exporter.js 的模块单例里（离开页面再回来，筛选与已选都还在，与旧页一致）。
 */
import { itemsOf, facets, filterAll } from '../../domain/items.js';
import { listLabels } from '../../domain/labels/index.js';
import { qvRender, qvSetContext, viewQ, QV_CARD_OPTS } from '../../domain/question/index.js';
import { requestExport } from '../../domain/exporting.js';
import * as X from './exporter.js';
import { openExportDialog } from './export-dialog.js';
import { saveExportOptions } from './export-options.js';

const x = X.exporter;

export function createExporter({ ctx, root, paint }) {
  const mounted = new WeakSet();
  let observer = null;

  function env() {
    const items = itemsOf(ctx.store.get().data);
    x.selection = X.pruneSelection(x.selection, items);
    const byUid = new Map(items.map(i => [questionKey(i), i]));
    const filtered = X.filterExport(items, x.filters, filterAll);
    qvSetContext('export', filtered.map(i => i.uid));
    qvSetContext('export-selection', x.selection.map(id => byUid.get(id)?.uid).filter(Boolean));
    return { facets: facets(items), labels: listLabels(), filtered, selected: x.selection.map(uid => byUid.get(uid)).filter(Boolean), summary: X.summary(filtered, x.selection) };
  }

  function hydrate() {
    observer?.disconnect();
    const hosts = [...root.querySelectorAll('[data-xpreview-uid]')].filter(el => !mounted.has(el));
    const mount = el => { if (!el.isConnected || mounted.has(el)) return; mounted.add(el); qvRender(el, el.dataset.xpreviewUid, { ...QV_CARD_OPTS }); };
    if (typeof IntersectionObserver === 'undefined') { hosts.forEach(mount); return; }
    observer = new IntersectionObserver(entries => entries.forEach(e => { if (e.isIntersecting) { observer.unobserve(e.target); mount(e.target); } }), { rootMargin: '240px' });
    hosts.forEach(el => observer.observe(el));
  }

  /** 打开面板前冻结题目引用；取消不发导出请求，失败留在面板内重试。 */
  async function run({ uids, sessionId, variant, count }) {
    const question_refs = sessionId ? undefined : questionRefs(uids);
    return openExportDialog({ variant, count: count ?? uids?.length, run: async options => {
      const res = await requestExport(X.exportPayload({ question_refs, sessionId, ...options }), X.exportFileName({ sessionId, variant: options.variant }));
      if (!res.ok) return { ok: false, text: `导出失败：${res.error}` };
      const saved = saveExportOptions(options);
      return { ok: true, text: `已导出 ${res.name}${saved ? '' : '（设置仅在本次打开期间保留）'}` };
    } });
  }

  const set = fn => { fn(); paint(); };
  return {
    env, hydrate,
    async export() {
      if (x.busy) return;
      if (!x.selection.length) { set(() => { x.status = { ok: false, text: '请选择至少 1 道题' }; }); return; }
      set(() => { x.busy = true; x.status = null; });
      const result = await run({ uids: x.selection });
      set(() => { x.busy = false; x.status = result; });
    },
    exportPlan: (sessionId, variant, count) => run({ sessionId, variant, count }),
    field: (key, value) => set(() => { x.filters = { ...x.filters, [key]: value ?? '' }; }),
    label: name => set(() => { const has = x.filters.labels.includes(name); x.filters = { ...x.filters, labels: has ? x.filters.labels.filter(v => v !== name) : [...x.filters.labels, name] }; }),
    view: v => set(() => { x.view = v === 'gallery' ? 'gallery' : 'flat'; }),
    toggle: uid => set(() => { x.selection = X.toggleSelection(x.selection, uid); x.status = null; }),
    addFiltered: () => set(() => { x.selection = X.addFiltered(x.selection, env().filtered); x.status = null; }),
    removeFiltered: () => set(() => { x.selection = X.removeFiltered(x.selection, env().filtered); x.status = null; }),
    clear: () => set(() => { x.selection = []; x.status = null; }),
    preview: arg => { const [context, uid] = String(arg || '').split('|'); viewQ(uid, context); },
    dispose: () => observer?.disconnect(),
  };
}
