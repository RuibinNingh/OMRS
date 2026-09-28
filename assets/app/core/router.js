/**
 * hash 路由：地址形如 #/questions。createRouter({ win, fallback, onEnter }) → { register, go, start, resolve, current, page, pages }。
 * - go(id)：同步切页（旧代码与冒烟测试都假定 switchTab 之后页面立刻可见），并用 pushState 写一条历史；
 *   replace:true 时改写当前历史。未登记的 id 落到 fallback。
 * - start()：监听前进 / 后退（popstate + hashchange），按当前地址进入页面；地址无效时改写成 fallback。
 * - 地址变成不是路由的 hash（如 href="#" 的链接）时不切页，并把地址改回当前页，刷新仍停在原页。
 * onEnter(page, prevId) 只在页面真正变化时调用。
 */
export function parseHash(hash) {
  const m = /^#\/([\w-]+)\/?(?:\?(.*))?$/.exec(hash || '');
  return m ? { id: m[1], query: m[2] || '' } : null;
}

export function createRouter({ win = globalThis.window, fallback = 'dashboard', onEnter } = {}) {
  const pages = new Map();
  let current = null;
  let started = false;
  let leaveGuard = null;
  let pending = null;
  let historyIndex = Number.isInteger(win.history.state?.omrsRouteIndex) ? win.history.state.omrsRouteIndex : 0;

  const target = id => (pages.has(id) ? id : fallback);
  const setHash = (id, replace) => {
    const hash = `#/${id}`;
    if (win.location.hash === hash) return;
    if (!replace) historyIndex += 1;
    win.history[replace ? 'replaceState' : 'pushState']({ ...win.history.state, omrsRouteIndex: historyIndex }, '', hash);
  };
  const activate = id => {
    if (id === current) return;
    const prev = current;
    current = id;
    onEnter?.(pages.get(id), prev);
  };
  // 无守卫时保持同步切页；有未保存内容时，确认完成前页面与地址保持在原处。
  const navigate = (to, { replace = false, external = false } = {}) => {
    if (pending) {
      if (external) setHash(current, true);
      return pending;
    }
    const externalState = win.history.state;
    const externalHash = win.location.hash;
    const externalIndex = externalState?.omrsRouteIndex;
    const enter = () => {
      if (external && Number.isInteger(externalIndex)) historyIndex = externalIndex;
      setHash(to, external || replace); activate(to); return to;
    };
    if (!current || current === to || !leaveGuard) return enter();
    const from = current;
    if (external) setHash(from, true);
    const cancel = () => {
      if (external) {
        // 先还原被临时替换的历史项，再返回原页面，避免取消后退丢失上一页。
        win.history.replaceState(externalState, '', externalHash);
        if (Number.isInteger(externalIndex) && externalIndex !== historyIndex && win.history.go) {
          win.history.go(historyIndex - externalIndex);
        } else {
          win.history.pushState({ ...externalState, omrsRouteIndex: ++historyIndex }, '', `#/${from}`);
        }
      }
      return current;
    };
    let decision;
    try { decision = leaveGuard({ from, to }); }
    catch (error) { console.error('[router] 离页检查失败', error); return cancel(); }
    if (decision && typeof decision.then === 'function') {
      pending = Promise.resolve(decision).then(allowed => allowed ? enter() : cancel(),
        error => { console.error('[router] 离页检查失败', error); return cancel(); })
        .finally(() => { pending = null; });
      return pending;
    }
    return decision ? enter() : cancel();
  };

  const api = {
    register(page) { pages.set(page.id, page); return api; },
    resolve(hash) { const r = parseHash(hash); return r && pages.has(r.id) ? r.id : fallback; },
    go(id, { replace = false } = {}) {
      const to = target(id);
      return navigate(to, { replace });
    },
    setLeaveGuard(fn) {
      leaveGuard = typeof fn === 'function' ? fn : null;
      return () => { if (leaveGuard === fn) leaveGuard = null; };
    },
    start() {
      if (!started) {
        started = true;
        win.history.replaceState({ ...win.history.state, omrsRouteIndex: historyIndex }, '', win.location.hash || `#/${fallback}`);
        const onNavigate = () => {
          const r = parseHash(win.location.hash);
          if (!r) { if (current) win.history.replaceState(null, '', `#/${current}`); return; }
          if (!pages.has(r.id)) { navigate(fallback, { external: true }); return; }
          navigate(r.id, { external: true });
        };
        win.addEventListener('popstate', onNavigate);
        win.addEventListener('hashchange', onNavigate);
      }
      return api.go(api.resolve(win.location.hash), { replace: true });
    },
    current: () => current,
    page: id => pages.get(id ?? current),
    pages: () => [...pages.values()],
  };
  return api;
}
