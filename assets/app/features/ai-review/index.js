/** 审核中心控制器：服务器拥有操作状态，本地表单独立保存并保护未提交修改。 */
import { morph } from '../../core/dom.js';
import { confirm, dialog } from '../../ui/dialog.js';
import { openMenu } from '../../ui/menu.js';
import { toast } from '../../ui/toast.js';
import { fetchReviewItems, fetchReviewDetail, updateReview, decideReview, openReview, currentReviewCounts, refreshReviewCounts } from '../../domain/ai-review.js';
import { reloadData } from '../../domain/data.js';
import { invalidateQuestions } from '../../domain/question/index.js';
import { refreshSessions } from '../../domain/sessions.js';
import { notifyHistoryChanged } from '../../domain/history.js';
import { selectedDraftId } from '../../domain/drafts.js';
import { boardDetailPort } from '../../domain/board/detail-port.js';
import { createDrafts } from './drafts.js';
import { draftActions } from './draft-actions.js';
import { editableValues, editedValue, changedPatch, changesOf, mergePage, isPending } from './state.js';
import { reviewView } from './view.js';
import { confirmDraftCleanup, requestDraftCleanup } from './maintenance.js';
import { reviewFilters, pendingDraftQueue } from './queue.js';

let controller = null;
export function createReviewController(root, ctx) {
  const query = new URLSearchParams(location.hash.split('?')[1] || '');
  const s = { view: 'pending', source: '', type: query.get('type') || '', status: '', range: '', items: [], loaded: false,
    listError: '', hasMore: false, nextOffset: 0, loadingMore: false, selectedId: null, item: null,
    detailLoading: false, detailError: '', counts: currentReviewCounts(), original: {}, edited: {},
    editing: false, dirty: false, busy: false, error: '', note: '', mobileDetail: false };
  let alive = true, listRequest = 0, detailRequest = 0, poll = null, draft = null;
  const paint = () => { if (alive) morph(root, reviewView(s)); };
  const syncTarget = () => ctx.router.replaceQuery?.(s.selectedId ? `${s.item?.kind === 'draft' ? 'draft' : 'operation'}=${encodeURIComponent(s.selectedId)}` : s.type === 'draft' ? 'type=draft' : '');
  function setItem(item) {
    s.item = item; s.original = editableValues(item); s.edited = structuredClone(s.original);
    s.dirty = false; s.error = ''; s.note = ''; s.detailError = ''; s.detailLoading = false; paint();
  }
  function stopDraft() { draft?.dispose(); draft = null; }
  function schedule() {
    if (poll) clearTimeout(poll);
    if (!alive || document.hidden) return;
    poll = setTimeout(async () => {
      if (!alive) return;
      await load();
      if (draft) { if (!draft.state.busy && !draft.state.job) await draft.reload({ changedIds: null }); }
      else if (s.item && !s.dirty && !s.busy) await readDetail(s.item.id, { refresh: true });
      schedule();
    }, 2500);
  }
  async function guard() {
    if (draft) return draft.guard();
    if (s.busy) return false;
    if (!s.dirty) return true;
    let action = 'discard';
    const out = await dialog({ title: '提案有未保存修改', hint: '选择如何处理当前修订。',
      okText: '放弃修改并离开', cancelText: '留在当前', danger: true,
      onOk: async () => action !== 'save' || await save(),
      onOpen(el) {
        el.querySelector('[data-dialog-ok]')?.addEventListener('click', event => { if (event.isTrusted) action = 'discard'; });
        const button = document.createElement('button'); button.type = 'button'; button.className = 'ui-btn ui-btn--primary'; button.textContent = '保存并离开';
        button.addEventListener('click', () => { action = 'save'; el.querySelector('[data-dialog-ok]')?.click(); });
        el.querySelector('.ui-dialog__foot')?.prepend(button);
      } });
    if (out.ok && action === 'discard') { s.edited = structuredClone(s.original); s.dirty = false; }
    return out.ok;
  }
  async function load(more = false) {
    if (more && (!s.hasMore || s.loadingMore)) return false;
    if (!more && s.loadingMore) return false;
    const mine = ++listRequest; s.loadingMore = more;
    const filters = reviewFilters(s);
    const target = more ? 30 : Math.max(30, s.items.length); let out, rows = [], offset = more ? s.nextOffset : 0;
    do {
      out = await fetchReviewItems({ ...filters, offset });
      if (!alive || mine !== listRequest) return false;
      if (!out.ok) break;
      rows = mergePage(rows, out.items || []); offset = out.next_offset || 0;
    } while (!more && out.has_more && rows.length < target && offset > 0);
    if (!alive || mine !== listRequest) return false;
    s.loaded = true; s.loadingMore = false;
    if (out.ok) { s.items = more ? mergePage(s.items, rows) : rows; s.hasMore = Boolean(out.has_more); s.nextOffset = out.next_offset || 0; s.listError = ''; }
    else s.listError = out.error;
    paint(); return out.ok;
  }
  async function readDetail(id, { refresh = false } = {}) {
    const mine = ++detailRequest;
    if (!refresh) { s.detailLoading = true; s.detailError = ''; paint(); }
    const out = await fetchReviewDetail(id);
    if (!alive || mine !== detailRequest || s.selectedId !== id || refresh && (s.dirty || s.busy)) return false;
    if (!out.ok) {
      s.detailLoading = false;
      if (s.item) s.error = `详情刷新失败：${out.error}；保留当前内容。`; else s.detailError = out.error;
      paint(); return false;
    }
    if (out.item?.kind === 'draft' && ['done', 'discarded'].includes(out.item.status)
      && (s.view !== 'records' || s.status !== out.item.status)) {
      s.view = 'records'; s.status = out.item.status; void load();
    }
    setItem(out.item);
    if (out.item?.kind === 'draft' && !draft) {
      draft = createDrafts(root, ctx, { embedded: true, isActive: () => alive,
        filterQueue: () => pendingDraftQueue(reviewFilters(s)),
        onPendingQueue() { if (s.view !== 'pending') { s.view = 'pending'; s.status = ''; void load(); } },
        onQueueError() { s.selectedId = null; s.item = { kind: 'draft', id: null }; syncTarget(); paint(); },
        onSelection(value) {
          if (!alive) return;
          if (!value) { s.selectedId = null; s.item = null; s.mobileDetail = false; stopDraft(); syncTarget(); paint(); return; }
          s.selectedId = value.id; s.item = { ...(s.items.find(row => row.id === value.id) || {}), id: value.id, kind: 'draft', draft: value, status: value.status }; syncTarget(); paint();
        } });
      await draft.enter(id);
    }
    return true;
  }
  async function select(id) {
    if (!id) return;
    if (id === s.selectedId) {
      s.mobileDetail = true; paint();
      if (matchMedia('(max-width: 760px)').matches) root.querySelector('.arv-mobile-back button')?.focus({ preventScroll: true });
      return;
    }
    if (!await guard()) return;
    stopDraft(); s.selectedId = id; s.item = null; s.editing = false; s.mobileDetail = true;
    await readDetail(id);
    syncTarget();
    if (matchMedia('(max-width: 760px)').matches) root.querySelector('.arv-mobile-back button')?.focus({ preventScroll: true });
  }
  async function maintenance(anchor) {
    if (draft) return draft.queueMenu(anchor);
    if (s.busy) return;
    const action = await openMenu(anchor, [{ value: 'reload', label: '刷新列表' }, { value: 'cleanup', label: '清理过期草稿' }], { label: '草稿队列操作' });
    if (!alive) return;
    if (action === 'reload') { await load(); return; }
    if (action !== 'cleanup' || !await confirmDraftCleanup()) return;
    s.busy = true; paint();
    try {
      const { result, summary } = await requestDraftCleanup();
      if (alive) toast(result.ok ? summary : `清理失败：${result.error?.message || result.data?.msg || '请求失败'}`, { kind: result.ok ? 'info' : 'error' });
    } finally { s.busy = false; paint(); }
  }
  async function filter(key, value) {
    if (s[key] === value || !await guard()) { paint(); return; }
    stopDraft(); detailRequest++; s[key] = value; s.selectedId = null; s.item = null;
    s.editing = false; s.mobileDetail = false; s.loaded = false; s.items = []; syncTarget(); paint();
    await load();
  }
  function field(key, value) {
    if (!isPending(s.item) || s.busy || !Object.hasOwn(s.original, key)) return;
    const kind = changesOf(s.item).find(row => row.field === key)?.kind;
    s.edited[key] = editedValue(s.original[key], value, kind);
    s.dirty = Object.keys(changedPatch(s.original, s.edited)).length > 0; s.error = ''; s.note = ''; paint();
  }
  async function save() {
    if (!s.item || s.busy || !isPending(s.item)) return false;
    if (!s.dirty) return true;
    s.busy = true; s.error = ''; paint();
    const id = s.item.id, out = await updateReview(id, s.item.revision, changedPatch(s.original, s.edited));
    if (!alive || s.selectedId !== id) return false;
    s.busy = false;
    if (out.ok) { setItem(out.item); s.note = '修订已保存，请核对新的影响预览。'; s.editing = false; void load(); }
    else s.error = `保存失败：${out.error}；本地修改已保留。`;
    paint(); return out.ok;
  }
  async function decide(decision) {
    if (!isPending(s.item) || s.busy) return;
    if (s.dirty) { s.error = '请先保存人工修订，再核对影响预览。'; paint(); return; }
    if (decision === 'reject' && !await confirm('拒绝这项写入提案？', { okText: '拒绝', danger: true })) return;
    s.busy = true; s.error = ''; paint(); const id = s.item.id;
    const out = await decideReview(id, s.item.revision, decision);
    if (!alive || s.selectedId !== id) return;
    s.busy = false;
    if (out.ok) {
      setItem(out.item); s.note = decision === 'approve' ? '决定已送达，执行结果以当前状态为准。' : '已拒绝。';
      await Promise.all([load(), refreshReviewCounts(), reloadData(), refreshSessions()]);
      invalidateQuestions(); notifyHistoryChanged('ai-review'); ctx.bus.emit('board:reload'); ctx.bus.emit('catalog:refresh');
    } else s.error = `未执行：${out.error}。请刷新详情后核对，原提案保留。`;
    paint();
  }
  function beforeUnload(event) { if (s.dirty || draft?.state.dirty) { event.preventDefault(); event.returnValue = ''; } }
  const stops = [ctx.router.setLeaveGuard(guard), ctx.bus.on('ai-review:counts', counts => { s.counts = counts; paint(); }),
    ctx.bus.on('ai-review:changed', async () => { await load(); if (draft) { if (!draft.state.busy && !draft.state.job) await draft.reload(); } else if (s.item && !s.dirty && !s.busy) await readDetail(s.item.id, { refresh: true }); }),
    ctx.bus.on('drafts:counts', counts => { if (draft) { draft.state.counts = counts; draft.paint(); } })];
  function focus() { if (!document.hidden) { void load(); schedule(); } else if (poll) clearTimeout(poll); }
  window.addEventListener('focus', focus); document.addEventListener('visibilitychange', focus); window.addEventListener('beforeunload', beforeUnload);
  paint();
  void load().then(() => { const id = query.get('draft') || query.get('operation'); if (id) void select(id); else if (s.type === 'draft' && s.items.length) void select(s.items.find(row => row.id === selectedDraftId())?.id || s.items[0].id); });
  schedule();
  return { state: s, openPage: route => ctx.router.go(route), editor: () => draft, guard, select, filter, field, save, decide, maintenance,
    refresh: async () => { await load(); await refreshReviewCounts(); if (draft) await draft.reload(); else if (s.selectedId && !s.dirty) await readDetail(s.selectedId, { refresh: true }); },
    retry: () => { if (!s.dirty) void readDetail(s.selectedId, { refresh: Boolean(s.item) }); }, more: () => load(true),
    back() { s.mobileDetail = false; paint(); root.querySelector(`.arv-row[data-arg="${CSS.escape(s.selectedId || '')}"]`)?.focus(); },
    edit() { s.editing = !s.editing; paint(); },
    dispose() { alive = false; listRequest++; detailRequest++; clearTimeout(poll); stopDraft(); stops.forEach(stop => stop());
      window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', focus); window.removeEventListener('beforeunload', beforeUnload); },
  };
}
export const page = {
  id: 'ai-review', title: '审核中心', workbench: true,
  mount(root, ctx) { controller = createReviewController(root, ctx); return () => { controller?.dispose(); controller = null; }; },
  actions: { ...draftActions(() => controller?.editor()),
    draftQueueMenu: ({ el }) => controller?.maintenance(el),
    refresh: () => controller?.refresh(), retry: () => controller?.retry(), open: ({ arg }) => controller?.select(arg),
    view: ({ arg }) => controller?.filter('view', arg), source: ({ value }) => controller?.filter('source', value),
    type: ({ value }) => controller?.filter('type', value), status: ({ value }) => controller?.filter('status', value), range: ({ value }) => controller?.filter('range', value),
    more: () => controller?.more(), back: () => controller?.back(), edit: () => controller?.edit(),
    editField: ({ arg, value }) => controller?.field(arg, value), save: () => controller?.save(),
    approve: () => controller?.decide('approve'), reject: () => controller?.decide('reject'),
    openDraft: ({ arg }) => openReview(arg, { kind: 'draft' }),
    openBoard: ({ arg }) => boardDetailPort.open(arg),
    openSession: () => controller?.openPage('schedule'),
    openPractice: ({ arg }) => controller?.openPage(`instant?practice=${encodeURIComponent(arg)}`),
  },
};
