/**
 * 外壳：连接路由与页面。页面登记表（各页 features/<页>/index.js 导出的页面契约）决定
 * 顶栏标题、文档标题、侧栏高亮（aria-current）、面板显隐与工作台布局（.content.is-workbench）。
 * 进入页面调 mount(root, ctx)，离开时执行它返回的卸载函数。
 * 新页面契约里的 actions / keys 在登记时一次性注册：动作命名空间与快捷键作用域都是页面 id（切页时外壳切作用域）。
 * 在 window.__omrs 暴露 { bus, store, router, emit }，供 domain 层跳页与测试脚本使用（页面里用 mount 收到的 ctx）；统计快照由 domain/data.js 经 bus 发 'data'，这里同步进 store.data。
 * 全局动作 app.*：跨页共用的按钮（仪表盘 / 题库 / 目录的「重新扫描」）走 data-action="app.scan"。
 */
import { createRouter } from './core/router.js';
import { createBus } from './core/bus.js';
import { createStore } from './core/store.js';
import { bindEvents, defineActions } from './core/events.js';
import { bindKeys, registerKeys, setScope } from './core/keys.js';
import { scanVault } from './domain/scan.js';
import { get } from './core/api.js';

export function applyChrome(page, doc = document) {
  const title = doc.getElementById('topbar-title');
  if (title) title.textContent = page.title;
  doc.title = `${page.title} · OMRS`;
  doc.querySelectorAll('.sidebar-nav .tab[data-tab]').forEach(tab => {
    const on = tab.dataset.tab === page.id;
    tab.classList.toggle('active', on);
    if (on) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  });
  doc.querySelectorAll('.content > .panel').forEach(panel => panel.classList.toggle('active', panel.id === `panel-${page.id}`));
  doc.querySelector('.content')?.classList.toggle('is-workbench', !!page.workbench);
}

/** 侧栏折叠成纯图标时，给导航项挂 data-tooltip（悬停或键盘聚焦显示页面名）；展开时撤掉。 */
function syncCollapsedTooltips(doc) {
  const collapsed = doc.documentElement.getAttribute('data-sidebar') === 'collapsed';
  doc.querySelectorAll('.sidebar-nav .tab[data-tab]').forEach(tab => {
    if (collapsed) tab.setAttribute('data-tooltip', tab.textContent.trim());
    else tab.removeAttribute('data-tooltip');
  });
}

/** 跨页共用的动作。scan：调 scanVault()，期间按钮置忙防重复点；在目录页时顺带重读目录树，「未进题库」提示随之更新。 */
function defineAppActions(win, router, bus) {
  let scanning = false;
  defineActions('app', {
    create: () => router.go('create'),
    collapse: () => {
      const collapsed = win.localStorage.getItem('omrs-sidebar-collapsed') === '1';
      win.localStorage.setItem('omrs-sidebar-collapsed', collapsed ? '0' : '1');
      win.document.documentElement.setAttribute('data-sidebar', collapsed ? '' : 'collapsed');
    },
    drawer: () => win.document.body.classList.toggle('drawer-open'),
    closeDrawer: () => win.document.body.classList.remove('drawer-open'),
    async scan({ el }) {
      if (scanning) return;
      scanning = true;
      const buttons = [...win.document.querySelectorAll('[data-action="app.scan"]')];
      buttons.forEach(b => { b.disabled = true; b.setAttribute('aria-busy', 'true'); });
      try {
        const scanned = await scanVault();
        if (scanned && router.current() === 'catalog') bus.emit('catalog:refresh');
      } finally {
        buttons.forEach(b => { b.disabled = false; b.removeAttribute('aria-busy'); });
        scanning = false;
        el?.isConnected && el.focus?.({ preventScroll: true });
      }
    },
  });
}

export function startShell(win, pages) {
  const doc = win.document;
  const bus = createBus();
  const store = createStore({ data: null });
  let unmount = null;
  const router = createRouter({
    win,
    fallback: 'dashboard',
    onEnter(page, prev) {
      if (typeof unmount === 'function') {
        try { unmount(); } catch (error) { console.error('[shell] 卸载页面出错', error); }
      }
      unmount = null;
      applyChrome(page, doc);
      setScope(page.id);
      doc.body.classList.remove('drawer-open');
      try {
        unmount = page.mount(doc.getElementById(`panel-${page.id}`), { bus, store, router });
      } catch (error) {
        console.error(`[shell] 进入「${page.title}」出错`, error);
      }
      bus.emit('page:change', { id: page.id, prev });
    },
  });
  pages.forEach(page => {
    router.register(page);
    if (page.actions) defineActions(page.id, page.actions);
    if (page.keys) registerKeys(page.id, page.keys);
  });
  bus.on('data', data => store.set({ data }));
  bindEvents(doc);
  bindKeys(doc);
  defineAppActions(win, router, bus);
  doc.addEventListener('keydown', event => { if (event.key === 'Escape') doc.body.classList.remove('drawer-open'); });
  doc.addEventListener('click', event => { if (event.target.closest('.sidebar-nav .tab') && win.matchMedia('(max-width:860px)').matches) doc.body.classList.remove('drawer-open'); });
  get('/api/status').then(res => { const foot = doc.getElementById('sidebar-foot'); if (foot && res.ok && res.data?.version) foot.textContent = `${res.data.version} · 本地服务`; });
  // 侧栏导航是 <a href="#/页面">：普通点击同步切页（旧代码与冒烟测试都假定点击后立即切换）；带修饰键时交给浏览器
  doc.addEventListener('click', event => {
    const link = event.target.closest?.('a.tab[data-tab]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    router.go(link.dataset.tab);
  });
  syncCollapsedTooltips(doc);
  new win.MutationObserver(() => syncCollapsedTooltips(doc))
    .observe(doc.documentElement, { attributes: true, attributeFilter: ['data-sidebar'] });
  win.__omrs = Object.freeze({ bus, store, router, emit: (type, payload) => bus.emit(type, payload) });
  return { bus, store, router };
}
