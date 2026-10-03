/** 审核中心的跨页导航、当前状态与角标；业务决定以服务端回执为准。 */
import { get, post } from '../core/api.js';

const result = response => response.ok
  ? { ok: true, item: response.data?.item, operation: response.data?.item, ...response.data }
  : { ok: false, error: response.error?.message || '请求失败', status: response.status };
export const fetchReviewDetail = async id => result(await get(`/api/ai-review/detail?id=${encodeURIComponent(id)}`));
export const decideReview = async (id, revision, decision) => {
  const out = result(await post('/api/ai-review/decide', { id, expected_revision: revision, decision }));
  if (out.ok) publishReviewChange([id]);
  return out;
};
export const updateReview = async (id, revision, patch) => {
  const out = result(await post('/api/ai-review/update', { id, expected_revision: revision, patch }));
  if (out.ok) publishReviewChange([id]);
  return out;
};
export async function fetchReviewItems(filters = {}) {
  const query = new URLSearchParams(Object.entries({ limit: 30, ...filters }).filter(([, value]) => value !== '' && value != null));
  return result(await get(`/api/ai-review/items?${query}`));
}

export function createReviewNavigation({ bus, router, document: doc, window: win, request = get, timers = globalThis } = {}) {
  let snapshot = null, pending = null, queued = null, timer = null, alive = true;
  const stops = [];
  function paint() {
    const badge = doc?.getElementById('nav-review-count');
    if (!badge || !snapshot) return;
    badge.hidden = snapshot.pending === 0;
    badge.textContent = snapshot.pending > 99 ? '99+' : String(snapshot.pending);
    badge.setAttribute('aria-label', `${snapshot.pending} 项 AI 写操作待审核`);
  }
  async function read() {
    const out = await request('/api/ai-review/counts');
    if (!alive) return null;
    const counts = out.data?.counts;
    if (out.ok && Number.isSafeInteger(counts?.pending) && counts.pending >= 0) {
      snapshot = { ...counts }; paint(); bus?.emit('ai-review:counts', { ...snapshot });
    }
    return snapshot;
  }
  function refresh() {
    if (!alive) return Promise.resolve(snapshot);
    if (!pending) { pending = read().finally(() => { pending = null; }); return pending; }
    if (!queued) queued = pending.then(() => { queued = null; return refresh(); });
    return queued;
  }
  function schedule() {
    if (timer) timers.clearTimeout(timer);
    timer = null;
    if (!alive || doc?.hidden) return;
    timer = timers.setTimeout(async () => { timer = null; await refresh(); schedule(); }, 10000);
  }
  function focus() { if (!doc?.hidden) void refresh(); schedule(); }
  if (bus) {
    stops.push(bus.on('ai-review:changed', () => { void refresh(); }));
    stops.push(bus.on('drafts:changed', ids => { bus.emit('ai-review:changed', ids); }));
    stops.push(bus.on('page:change', () => { void refresh(); }));
  }
  win?.addEventListener('focus', focus); doc?.addEventListener('visibilitychange', focus);
  schedule();
  return {
    refresh, counts: () => snapshot && { ...snapshot },
    async open(id = '', { kind = 'operation' } = {}) {
      const query = new URLSearchParams();
      if (id) query.set(kind === 'draft' ? 'draft' : 'operation', id);
      else if (kind === 'draft') query.set('type', 'draft');
      await router?.go(`ai-review${query.size ? '?' + query : ''}`);
      return router?.current() === 'ai-review';
    },
    changed(ids = []) { bus?.emit('ai-review:changed', { ids }); },
    dispose() {
      alive = false; if (timer) timers.clearTimeout(timer); stops.forEach(stop => stop());
      win?.removeEventListener('focus', focus); doc?.removeEventListener('visibilitychange', focus);
    },
  };
}
let service = null;
export function connectReview(options) {
  service?.dispose(); service = createReviewNavigation(options); void service.refresh();
  return () => { service?.dispose(); service = null; };
}
export const openReview = (id, options) => service?.open(id, options) || Promise.resolve(false);
export const publishReviewChange = ids => service?.changed(ids);
export const refreshReviewCounts = () => service?.refresh();
export const currentReviewCounts = () => service?.counts();
