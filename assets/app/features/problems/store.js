/** 问题工作台状态：分页、请求代次、编辑草稿与幂等写入。 */
import { read, write, requestId } from '../../domain/problems.js';

export function createWorkspace(paint, api = { read, write }) {
  const s = {
    items: [], total: 0, counts: {}, offset: 0, limit: 25, query: '', filter: '', sort: 'updated_desc',
    chosen: new Map(), detail: null, draft: null, creating: false, editing: false, reason: '',
    loading: false, opening: false, busy: false, uploading: 0, listError: '', detailError: '', message: '', error: false,
    picker: false, questions: [], selected: new Set(), questionQuery: '',
  };
  let alive = true, listId = 0, detailId = 0, request = null;
  const emit = () => { if (alive) paint(s); };
  const dirty = () => s.creating || !!s.reason || ['title', 'description_md', 'status'].some(k => s.draft?.[k] !== s.detail?.[k]);
  const notice = (message, error = false) => { s.message = message; s.error = error; emit(); };
  const invalidateList = () => { listId++; s.loading = true; s.listError = ''; emit(); };
  async function load() {
    const mine = ++listId;
    s.loading = true; s.listError = ''; emit();
    const params = new URLSearchParams({ query: s.query, status: s.filter === 'trash' ? '' : s.filter,
      deleted: s.filter === 'trash' ? 'only' : '', sort: s.sort, limit: s.limit, cursor: s.offset });
    try {
      const data = await api.read(`/api/problems?${params}`);
      if (!alive || mine !== listId) return;
      if (s.offset && !data.items.length && data.total) {
        s.offset = Math.floor((data.total - 1) / s.limit) * s.limit;
        return load();
      }
      s.items = data.items; s.total = data.total; s.counts = data.counts || {};
      if (!s.total) s.offset = 0;
    } catch (e) {
      if (alive && mine === listId) s.listError = e.message;
    } finally {
      if (alive && mine === listId) { s.loading = false; emit(); }
    }
  }
  function close() {
    detailId++; s.detail = null; s.draft = null; s.creating = false; s.editing = false;
    s.reason = ''; s.picker = false; s.selected.clear(); s.opening = false; s.detailError = ''; emit();
  }
  async function open(id) {
    const mine = ++detailId;
    s.opening = true; s.detailError = ''; emit();
    try {
      const data = await api.read(`/api/problem?id=${encodeURIComponent(id)}`);
      if (!alive || mine !== detailId) return;
      s.detail = data.problem; s.draft = { ...data.problem }; s.creating = false;
      s.editing = false; s.reason = ''; s.picker = false; s.selected.clear();
    } catch (e) {
      if (alive && mine === detailId) s.detailError = e.message;
    } finally {
      if (alive && mine === detailId) { s.opening = false; emit(); }
    }
  }
  function create() {
    close();
    s.creating = true; s.editing = true;
    s.detail = { id: 'new', title: '', description_md: '## 具体表现\n\n## 应对办法\n\n## 怎样验证改善',
      status: 'analyzing', basis: 'user_confirmed', questions: [], entries: [], events: [] };
    s.draft = { ...s.detail }; emit();
  }
  function accept(problem) {
    // 写回执是保存事实，详情刷新失败也不能把已创建的问题当作新草稿。
    s.detail = { questions: s.detail?.questions || [], entries: [], events: [], ...problem };
    s.draft = { ...s.detail }; s.creating = false; s.editing = false; s.reason = ''; emit();
  }
  async function mutate(action, data) {
    if (s.busy || !alive) return null;
    const payload = JSON.stringify([action, data]);
    if (request?.payload !== payload) request = { payload, id: requestId() };
    s.busy = true; s.message = ''; emit();
    try {
      const result = await api.write(action, { ...data, request_id: request.id });
      request = null;
      return alive ? result : null;
    } finally { s.busy = false; emit(); }
  }
  return { s, emit, dirty, notice, invalidateList, load, open, close, create, accept, mutate,
    dispose() { alive = false; listId++; detailId++; },
  };
}
