/** 目录页：磁盘树读取、题目状态叠加与页面生命周期。 */
import { morph } from '../../core/dom.js';
import { get } from '../../core/api.js';
import { itemsOf, dueDays } from '../../domain/items.js';
import { viewQ } from '../../domain/question/index.js';
import { fallbackTree, folderStats, treePaths } from './state.js';
import { view } from './view.js';

let controller = null;
let savedTree = null;
let savedOpen = null;

function createController(root, ctx) {
  const host = root.querySelector('#cat-app') || root;
  const s = { tree: savedTree?.tree || null, summary: savedTree?.summary || null,
    source: savedTree?.source || '', open: new Set(savedOpen || []),
    stats: new Map(), query: '', showAll: false, loading: false, error: '', copyMessage: '' };
  let alive = true;
  let requestId = 0;
  let slow = 0;
  const items = () => itemsOf(ctx.store.get().data);
  const paint = () => {
    if (!alive) return;
    s.stats = folderStats(items(), dueDays);
    morph(host, view(s, items(), dueDays));
  };

  async function load(force = false) {
    if (s.tree && !force) { paint(); return { ok: true, cached: true }; }
    const mine = ++requestId;
    clearTimeout(slow);
    s.copyMessage = '';
    if (!s.tree) slow = setTimeout(() => { if (alive && mine === requestId) { s.loading = true; paint(); } }, 300);
    else { s.loading = true; paint(); }
    const result = await get('/api/tree');
    clearTimeout(slow);
    if (!alive || mine !== requestId) return result;
    s.loading = false;
    if (result.ok && result.data?.root) {
      s.tree = result.data.root;
      s.summary = result.data.summary || null;
      s.source = 'api';
      s.error = '';
    } else {
      s.error = result.error?.message || '服务没有返回目录树';
      if (!s.tree) {
        s.tree = fallbackTree(items());
        s.summary = null;
        s.source = 'fallback';
      }
    }
    savedTree = { tree: s.tree, summary: s.summary, source: s.source };
    if (!s.open.size && s.tree) {
      s.open.add(s.tree.path);
      (s.tree.children || []).forEach(child => s.open.add(child.path));
    }
    paint();
    return result;
  }

  async function copyPath(path) {
    let ok = false;
    try {
      if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(path); ok = true; }
      else {
        const probe = document.createElement('textarea');
        probe.className = 'catw-copy-probe';
        probe.value = path;
        document.body.append(probe);
        probe.select();
        try { ok = document.execCommand('copy'); } finally { probe.remove(); }
      }
    } catch { ok = false; }
    if (!alive) return;
    s.copyMessage = ok ? `已复制路径：${path}` : `复制失败，请手动复制路径：${path}`;
    paint();
  }

  return {
    load, paint,
    toggle(path) { s.open.has(path) ? s.open.delete(path) : s.open.add(path); paint(); },
    expand() { s.open = new Set(treePaths(s.tree)); paint(); },
    collapse() { s.open = new Set(s.tree ? [s.tree.path] : []); paint(); },
    search(value) { s.query = String(value || '').trim().toLocaleLowerCase(); s.copyMessage = ''; paint(); },
    showAll(checked) { s.showAll = !!checked; paint(); },
    copyPath,
    open(uid, el) { return viewQ(uid, null, { returnFocus: () => el?.isConnected ? el : host.querySelector(`[data-action="catalog.open"][data-arg="${CSS.escape(uid)}"]`) }); },
    refreshData() {
      if (s.source === 'fallback') {
        s.tree = fallbackTree(items());
        s.summary = null;
        savedTree = { tree: s.tree, summary: null, source: 'fallback' };
      }
      paint();
    },
    dispose() { savedOpen = new Set(s.open); alive = false; requestId += 1; clearTimeout(slow); },
  };
}

export const page = {
  id: 'catalog', title: '目录',
  mount(root, ctx) {
    controller = createController(root, ctx);
    const off = [ctx.store.subscribe(() => controller?.refreshData(), state => state.data),
      ctx.bus.on('catalog:refresh', () => controller?.load(true))];
    controller.paint();
    controller.load();
    return () => { off.forEach(stop => stop()); controller?.dispose(); controller = null; };
  },
  actions: {
    refresh: () => controller?.load(true),
    toggle: ({ arg }) => controller?.toggle(arg),
    expand: () => controller?.expand(),
    collapse: () => controller?.collapse(),
    search: ({ value }) => controller?.search(value),
    showAll: ({ el }) => controller?.showAll(el.checked),
    copy: ({ arg }) => controller?.copyPath(arg),
    open: ({ arg, el }) => controller?.open(arg, el),
  },
};
