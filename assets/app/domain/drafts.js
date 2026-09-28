/** 草稿跨页导航与计数：先保存目标再切页，避免新页面尚未挂载时丢事件。 */
import { get } from '../core/api.js';

const SELECTED_KEY = 'omrs-selected-draft';

export function createDraftNavigation({ bus, router, document: doc, window: win, request = get } = {}) {
  let target = null;
  let selected = null;
  let snapshot = null;
  let running = null;
  let queued = null;
  let timer = null;
  let disposed = false;
  const activity = new Set();
  const stops = [];
  try { selected = win?.sessionStorage?.getItem(SELECTED_KEY) || null; } catch { /* 隐私模式仍支持内存选择。 */ }

  function select(id) {
    selected = typeof id === 'string' && id ? id : null;
    try {
      if (selected) win?.sessionStorage?.setItem(SELECTED_KEY, selected);
      else win?.sessionStorage?.removeItem(SELECTED_KEY);
    } catch { /* 不影响本次会话。 */ }
  }
  function paintCounts() {
    const el = doc?.getElementById('nav-draft-count');
    if (!el || !snapshot) return;
    const count = snapshot.cropping + snapshot.review;
    el.hidden = count === 0;
    el.textContent = count > 99 ? '99+' : String(count);
    el.setAttribute('aria-label', `${count} 份 AI 草稿待审核`);
  }
  async function fetchCounts() {
    const res = await request('/api/drafts/counts');
    if (disposed) return null;
    if (res.ok && res.data?.counts) {
      const counts = res.data.counts;
      const keys = ['cropping', 'review', 'done', 'discarded'];
      if (keys.every(key => Number.isSafeInteger(counts[key]) && counts[key] >= 0)) {
        snapshot = Object.fromEntries(keys.map(key => [key, counts[key]]));
        paintCounts();
        bus?.emit('drafts:counts', { ...snapshot });
      }
    }
    return snapshot;
  }
  function refresh() {
    if (disposed) return Promise.resolve(snapshot);
    if (!running) {
      running = fetchCounts().finally(() => { running = null; });
      return running;
    }
    if (!queued) queued = running.then(() => { queued = null; return refresh(); });
    return queued;
  }
  function schedule() {
    if (timer) clearTimeout(timer);
    timer = null;
    if (disposed || !activity.size || doc?.hidden) return;
    timer = setTimeout(async () => {
      timer = null;
      await refresh();
      schedule();
    }, 2000);
  }
  function onFocus() { if (!doc?.hidden) void refresh(); }
  function onVisibility() { onFocus(); schedule(); }
  if (bus) {
    stops.push(bus.on('drafts:changed', () => { void refresh(); }));
    stops.push(bus.on('page:change', onFocus));
  }
  win?.addEventListener('focus', onFocus);
  doc?.addEventListener('visibilitychange', onVisibility);

  return {
    select,
    selected: () => selected,
    consume() { const id = target; target = null; return id; },
    async open(id) {
      if (typeof id !== 'string' || !id) return false;
      target = id;
      select(id);
      if (router?.current() !== 'create') await router?.go('create');
      if (router?.current() !== 'create') { target = null; return false; }
      bus?.emit('drafts:open', { id });
      return true;
    },
    changed(ids = []) { bus?.emit('drafts:changed', { ids }); },
    refresh,
    counts: () => snapshot && { ...snapshot },
    activity(key, active) {
      if (activity.has(key) === Boolean(active)) return;
      if (active) activity.add(key); else activity.delete(key);
      schedule();
    },
    dispose() {
      disposed = true;
      if (timer) clearTimeout(timer);
      stops.forEach(stop => stop());
      win?.removeEventListener('focus', onFocus);
      doc?.removeEventListener('visibilitychange', onVisibility);
    },
  };
}

let service = null;
export function connectDrafts(options) {
  service?.dispose();
  service = createDraftNavigation(options);
  void service.refresh();
  return () => { service?.dispose(); service = null; };
}
export const consumeDraftTarget = () => service?.consume() || null;
export const selectedDraftId = () => service?.selected() || null;
export const selectDraftId = id => service?.select(id);
export const openDraft = id => service?.open(id);
export const publishDraftChange = ids => service?.changed(ids);
export const refreshDraftCounts = () => service?.refresh();
export const currentDraftCounts = () => service?.counts();
export const setDraftActivity = (key, active) => service?.activity(key, active);
