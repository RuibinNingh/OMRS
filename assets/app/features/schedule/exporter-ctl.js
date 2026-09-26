/**
 * 复习调度 ·「全题库导出」与「已有计划」导出的控制器：筛选与已选、画廊题面懒加载、A4 单双栏确认、调 domain/exporting 下载。
 * 状态在 exporter.js 的模块单例里（离开页面再回来，筛选与已选都还在，与旧页一致）。
 */
import { confirm } from '../../ui/dialog.js';
import { itemsOf, facets, filterAll } from '../../domain/items.js';
import { listLabels } from '../../domain/labels/index.js';
import { qvRender, qvSetContext, viewQ, QV_CARD_OPTS } from '../../domain/question/index.js';
import { requestExport } from '../../domain/exporting.js';
import * as X from './exporter.js';

const x = X.exporter;
const askColumns = () => confirm('A4 用双栏排版？', { hint: '长公式、宽表格建议选「单栏」。', okText: '双栏', cancelText: '单栏' });

export function createExporter({ ctx, root, paint }) {
  const mounted = new WeakSet();
  let observer = null;

  function env() {
    const items = itemsOf(ctx.store.get().data);
    x.selection = X.pruneSelection(x.selection, items);
    const byUid = new Map(items.map(i => [i.uid, i]));
    const filtered = X.filterExport(items, x.filters, filterAll);
    qvSetContext('export', filtered.map(i => i.uid));
    qvSetContext('export-selection', x.selection);
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

  /** 真正的导出：A4 先问单 / 双栏（关掉对话框按单栏，与旧版一致）。返回 { ok, text }。 */
  async function run({ uids, sessionId, variant, answers, gap }) {
    const twoColumns = variant === 'a4' ? await askColumns() : true;
    const res = await requestExport(X.exportPayload({ uids, sessionId, variant, answers, gap, twoColumns }), X.exportFileName({ sessionId, variant }));
    return res.ok ? { ok: true, text: `已导出 ${res.name}` } : { ok: false, text: `导出失败：${res.error}` };
  }

  const set = fn => { fn(); paint(); };
  return {
    env, hydrate,
    async export() {
      if (x.busy) return;
      if (!x.selection.length) { set(() => { x.status = { ok: false, text: '请选择至少 1 道题' }; }); return; }
      set(() => { x.busy = true; x.status = null; });
      const result = await run({ uids: x.selection, variant: x.variant, answers: x.answers, gap: x.gap });
      set(() => { x.busy = false; x.status = result; });
    },
    /** 「已有计划」详情里的导出打印版 / 屏幕版：选项来自计划详情的打印选项。 */
    exportPlan: (sessionId, variant, { answers, gap }) => run({ sessionId, variant, answers, gap }),
    field: (key, value) => set(() => { x.filters = { ...x.filters, [key]: value ?? '' }; }),
    label: name => set(() => { const has = x.filters.labels.includes(name); x.filters = { ...x.filters, labels: has ? x.filters.labels.filter(v => v !== name) : [...x.filters.labels, name] }; }),
    view: v => set(() => { x.view = v === 'gallery' ? 'gallery' : 'flat'; }),
    variant: v => set(() => { x.variant = v === 'screen' ? 'screen' : 'a4'; x.status = null; }),
    answers: on => { x.answers = !!on; },
    gap: v => { x.gap = X.clampGap(v); },
    toggle: uid => set(() => { x.selection = X.toggleSelection(x.selection, uid); x.status = null; }),
    addFiltered: () => set(() => { x.selection = X.addFiltered(x.selection, env().filtered); x.status = null; }),
    removeFiltered: () => set(() => { x.selection = X.removeFiltered(x.selection, env().filtered); x.status = null; }),
    clear: () => set(() => { x.selection = []; x.status = null; }),
    preview: arg => { const [context, uid] = String(arg || '').split('|'); viewQ(uid, context); },
    dispose: () => observer?.disconnect(),
  };
}
