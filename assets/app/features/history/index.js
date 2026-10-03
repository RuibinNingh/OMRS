import { openReview } from '../../domain/ai-review.js';
/** Ledger 历史页：列表生命周期与修正操作。 */
import { morph } from '../../core/dom.js';
import { confirm, prompt } from '../../ui/dialog.js';
import { fetchHistoryPage, fetchHistoryDetail, postHistoryCorrection, notifyHistoryChanged, ledgerTimeZone } from '../../domain/history.js';
import { reloadData } from '../../domain/data.js';
import { refreshSessions } from '../../domain/sessions.js';
import { invalidateQuestions } from '../../domain/question/index.js';
import { openDraft } from '../../domain/drafts.js';
import { boardDetailPort } from '../../domain/board/detail-port.js';
import { state as s, readPreferences, reviewPayload, dateRange, timeline } from './state.js';
import { runtimeController } from './runtime-controller.js';
import { view } from './view.js';

let ctl = null;

function createController(root, ctx) {
  const host = root.querySelector('#hist-app') || root;
  let alive = true;
  let loadSeq = 0;
  let slow = 0;
  let searchTimer = 0;
  let linkedSeq = null;
  const pendingDetails = new Map();
  const paint = () => {
    if (!alive) return;
    const expanded = new Set([...host.querySelectorAll('details[open]')].map(detail => {
      const row = detail.closest('.hvw-node, .hvw-correction, .hvw-detail-panel');
      return row ? `${row.getAttribute('data-key')}:${detail.getAttribute('data-key') || detail.className}` : '';
    }));
    morph(host, view(s, ledgerTimeZone()));
    for (const tab of host.querySelectorAll('[role="tab"]')) {
      tab.setAttribute('data-action', 'history.tab'); tab.setAttribute('data-arg', tab.dataset.tab);
    }
    for (const detail of host.querySelectorAll('details')) {
      const row = detail.closest('.hvw-node, .hvw-correction, .hvw-detail-panel');
      if (!row) continue;
      if (expanded.has(`${row.getAttribute('data-key')}:${detail.getAttribute('data-key') || detail.className}`)) detail.open = true;
    }
  };
  const rowOf = seq => s.commits.find(row => String(row.seq) === String(seq)) || s.details.get(String(seq));
  const filters = () => ({ q: s.query, ...dateRange(s.range, ledgerTimeZone()) });
  const runtime = runtimeController(s.system, paint,
    () => ({ ...filters(), key_id: s.system.key, status: s.system.status }), () => s.tab === 'system');

  function scrollToLatest() {
    const box = host.querySelector('#history-timeline');
    if (box) box.scrollTop = s.sort === 'desc' ? 0 : box.scrollHeight;
  }

  async function load({ scroll = false, more = false } = {}) {
    if (more && (!s.hasMore || s.loadingMore)) return;
    const mine = ++loadSeq;
    const box = host.querySelector('#history-timeline');
    const anchor = box?.scrollTop || 0;
    const oldHeight = box?.scrollHeight || 0;
    const top = box?.getBoundingClientRect().top || 0;
    const visibleRow = [...(box?.querySelectorAll('.hvw-node') || [])]
      .find(row => row.getBoundingClientRect().bottom > top + 1);
    const visibleKey = visibleRow?.getAttribute('data-key');
    const visibleY = visibleRow?.getBoundingClientRect().top;
    s.loadingMore = more;
    clearTimeout(slow);
    if (!more && !s.commits.length) {
      slow = setTimeout(() => { if (alive && mine === loadSeq) { s.phase = 'loading'; paint(); } }, 300);
    }
    const result = await fetchHistoryPage(more ? s.nextBeforeSeq : null, 60, filters());
    if (!alive || mine !== loadSeq) return result;
    clearTimeout(slow);
    s.loadingMore = false;
    if (result.ok) {
      s.commits = more ? [...result.commits, ...s.commits] : result.commits;
      s.retraction = result.retraction;
      s.hasMore = result.hasMore;
      s.nextBeforeSeq = result.nextBeforeSeq;
      s.phase = 'ready';
      s.error = '';
      const main = timeline(s).main;
      if (s.selectedSeq !== linkedSeq && !main.some(row => row.seq === Number(s.selectedSeq))) s.selectedSeq = null;
      if (s.selectedSeq == null && main.length) s.selectedSeq = main[0].seq;
      if (s.selectedSeq != null) void detail(s.selectedSeq, !more);
    } else {
      s.phase = 'error';
      s.error = result.error;
    }
    paint();
    const nextBox = host.querySelector('#history-timeline');
    if (!scroll && nextBox && box) {
      nextBox.scrollTop = anchor + (more && s.sort === 'asc' ? nextBox.scrollHeight - oldHeight : 0);
      if (visibleKey) {
        const nextRow = [...nextBox.querySelectorAll('.hvw-node')]
          .find(row => row.getAttribute('data-key') === visibleKey);
        if (nextRow) nextBox.scrollTop += nextRow.getBoundingClientRect().top - visibleY;
      }
    }
    if (scroll && result.ok) scrollToLatest();
    return result;
  }

  async function detail(seq, force = false) {
    const key = String(seq);
    if (!force && (s.details.has(key) || pendingDetails.has(key))) return;
    const ticket = Symbol(); pendingDetails.set(key, ticket);
    s.detailErrors.delete(key);
    const result = await fetchHistoryDetail(seq);
    if (!alive || pendingDetails.get(key) !== ticket) return;
    pendingDetails.delete(key);
    if (result.ok) s.details.set(key, result.detail);
    else s.detailErrors.set(key, result.error);
    paint();
  }

  function savePreference(key, value) {
    try { localStorage.setItem(key, value); } catch { /* 本地存储不可用时，本次页面状态仍有效。 */ }
  }

  function tab(value) {
    s.tab = value === 'system' ? 'system' : 'learning'; s.mobileDetail = false;
    loadSeq++; clearTimeout(slow); s.loadingMore = false;
    clearTimeout(searchTimer); runtime.pause(); paint();
    if (s.tab === 'system') void runtime.load();
    else void load();
  }
  function select(seq, linked = false) {
    s.mobileDetail = true;
    if (s.tab === 'system') runtime.select(seq, linked);
    else { linkedSeq = linked ? Number(seq) : null; s.selectedSeq = Number(seq); paint(); void detail(seq); }
    if (matchMedia('(max-width: 760px)').matches) host.querySelector(`#history-${s.tab}-panel .is-back`)?.focus({ preventScroll: true });
  }
  function filter(key, value, debounce = false) {
    if (key === 'query') s.query = String(value || '').slice(0, 200);
    else if (key === 'range') s.range = ['today', '7d', '30d'].includes(value) ? value : 'all';
    else s.system[key] = String(value || '');
    loadSeq++; clearTimeout(slow); runtime.pause(); s.loadingMore = false; linkedSeq = null;
    s.mobileDetail = false;
    if (s.tab === 'system') s.system.selectedSeq = null;
    else s.selectedSeq = null;
    clearTimeout(searchTimer);
    const run = () => s.tab === 'system' ? runtime.load() : load();
    if (debounce) searchTimer = setTimeout(run, 250);
    else void run();
  }
  function related(seq, kind) {
    s.query = ''; s.range = 'all'; s.system.key = ''; s.system.status = '';
    tab(kind); select(seq, true);
  }
  function keyboard(event) {
    const item = event.target.closest('[role="tab"]');
    if (!item || !['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === 'Home' ? 'learning' : event.key === 'End' ? 'system' : item.dataset.tab === 'learning' ? 'system' : 'learning';
    tab(next); host.querySelector(`[data-tab="${next}"]`)?.focus();
  }
  host.addEventListener('keydown', keyboard);

  async function perform(seq, prepare) {
    const key = String(seq);
    if (!s.edit || s.busy.size) return;
    s.busy.add(key);
    s.writeError = '';
    s.note = '';
    paint();
    try {
      const instruction = await prepare();
      if (!instruction || !alive) return;
      const result = await postHistoryCorrection(instruction.path, instruction.payload);
      if (!alive) return;
      if (!result.ok) { s.writeError = `修正失败：${result.error}`; return; }
      await invalidateQuestions();
      const data = await reloadData();
      const sessions = await refreshSessions();
      notifyHistoryChanged('history');
      const history = await load({ scroll: true });
      if (!alive) return;
      const problems = [!data.ok && `统计刷新失败：${data.error?.message || '未知错误'}`,
        !sessions.ok && `Session 刷新失败：${sessions.error || '未知错误'}`,
        !history?.ok && `历史列表刷新失败：${history?.error || '未知错误'}`].filter(Boolean);
      if (problems.length) s.writeError = `修正已提交；${problems.join('；')}`;
      else s.note = '已追加历史节点';
    } catch (error) {
      if (alive) s.writeError = `修正失败：${error?.message || '未知错误'}`;
    } finally {
      s.busy.delete(key);
      paint();
    }
  }

  function review(arg) {
    const [seq, kind] = String(arg || '').split(':');
    if (!['replace', 'retract', 'restore'].includes(kind)) return;
    const row = rowOf(seq);
    if (!row || row.commit_type !== 'review.batch_submit') return;
    const values = {
      index: host.querySelector(`#hist-review-index-${seq}`)?.value,
      score: host.querySelector(`#hist-review-score-${seq}`)?.value,
      correct: host.querySelector(`#hist-review-correct-${seq}`)?.value,
      note: host.querySelector(`#hist-review-note-${seq}`)?.value,
      reason: host.querySelector(`#hist-review-reason-${seq}`)?.value,
    };
    const payload = reviewPayload(row, kind, values);
    perform(seq, async () => {
      if (kind === 'retract' && !await confirm('撤销这条反馈？', {
        hint: '会在 Ledger 追加撤销节点并重新计算题目状态。', okText: '撤销反馈', danger: true,
      })) return null;
      return { path: `/api/history/review/${kind}`, payload };
    });
  }

  function session(arg) {
    const [seq, kind] = String(arg || '').split(':');
    if (!['retract', 'restore'].includes(kind)) return;
    const row = rowOf(seq);
    const sid = row?.payload?.session_id || row?.payload?.session?.session_id;
    if (!sid) return;
    perform(seq, async () => {
      const reason = await prompt(kind === 'retract' ? '撤销原因' : '恢复原因');
      if (reason === null) return null;
      if (kind === 'retract' && !await confirm(`撤销整个 Session「${sid}」？`, {
        hint: '该 Session 下的反馈也会撤销，题目熟练度与复习日期会重新计算。', okText: '撤销 Session', danger: true,
      })) return null;
      return { path: `/api/history/session/${kind}`, payload: { session_id: sid, reason } };
    });
  }

  function directRestore(seq) {
    const row = rowOf(seq);
    const payload = row?.payload || {};
    if (!row) return;
    perform(seq, async () => {
      const reason = await prompt('恢复原因');
      if (reason === null) return null;
      if (row.commit_type === 'session.retract' && payload.session_id) {
        return { path: '/api/history/session/restore', payload: { session_id: payload.session_id, reason } };
      }
      if (row.commit_type === 'review.retract' && payload.target_commit_id != null) {
        return { path: '/api/history/review/restore', payload: {
          target_commit_id: payload.target_commit_id, target_review_index: Number(payload.target_review_index) || 0, reason,
        } };
      }
      return null;
    });
  }

  function restoreState(seq) {
    if (!rowOf(seq)) return;
    const reason = (host.querySelector(`#hist-restore-reason-${seq}`)?.value || '').trim();
    perform(seq, async () => {
      if (!await confirm(`还原结构化状态到 seq ${seq}？`, {
        hint: reason ? `原因：${reason}` : '未填写原因；本次操作仍会追加 Ledger 节点。',
        okText: '还原状态', danger: true,
      })) return null;
      return { path: '/api/history/state/restore', payload: { target_seq: Number(seq), reason } };
    });
  }

  return {
    paint, load, detail,
    tab, select, filter, related,
    operation(id) { s.query = ''; s.range = 'all'; s.system.key = ''; s.system.status = ''; s.system.operation = null;
      s.mobileDetail = true; tab('system'); s.mobileDetail = true; void runtime.openOperation(id); },
    operationConfirm: id => runtime.decide(id, 'confirm'),
    operationReject: id => runtime.decide(id, 'reject'),
    refresh() { return s.tab === 'system' ? runtime.refresh() : load(); },
    more() { return s.tab === 'system' ? runtime.load(true) : load({ more: true }); },
    close() {
      const seq = s.tab === 'system' ? s.system.selectedSeq : s.selectedSeq;
      s.mobileDetail = false; if (s.tab === 'system') { s.system.selectedSeq = null; s.system.operation = null; } else s.selectedSeq = null;
      paint(); host.querySelector(`#history-${s.tab}-panel .hvw-row[data-arg="${seq}"]`)?.focus({ preventScroll: true });
    },
    sort(value) {
      s.sort = value === 'desc' ? 'desc' : 'asc';
      savePreference('omrs-history-sort', s.sort);
      paint(); scrollToLatest();
    },
    mode() {
      s.edit = !s.edit;
      savePreference('omrs-history-edit-mode', s.edit ? '1' : '0');
      paint();
    },
    corrections() { s.correctionsOpen = !s.correctionsOpen; paint(); },
    review, session, directRestore, restoreState,
    dispose() { alive = false; loadSeq += 1; clearTimeout(slow); clearTimeout(searchTimer);
      pendingDetails.clear(); runtime.dispose(); host.removeEventListener('keydown', keyboard); },
  };
}

export const page = {
  id: 'history', title: '历史记录',
  mount(root, ctx) {
    const operation = new URLSearchParams(location.hash.split('?')[1] || '').get('operation');
    if (operation) { const timer = setTimeout(() => ctx.router.go(`ai-review?operation=${encodeURIComponent(operation)}`, { replace: true }), 0); return () => clearTimeout(timer); }
    Object.assign(s, readPreferences(localStorage));
    ctl = createController(root, ctx);
    const off = [ctx.bus.on('history:changed', payload => {
      if (payload?.source !== 'history') ctl?.refresh();
    }), ctx.bus.on('ledger:tz', () => ctl?.paint())];
    ctl.paint();
    ctl.refresh();
    return () => { off.forEach(stop => stop()); ctl?.dispose(); ctl = null; };
  },
  actions: {
    sort: ({ value }) => ctl?.sort(value),
    mode: () => ctl?.mode(),
    corrections: () => ctl?.corrections(),
    tab: ({ arg }) => ctl?.tab(arg),
    select: ({ arg }) => ctl?.select(arg),
    close: () => ctl?.close(),
    query: ({ value }) => ctl?.filter('query', value, true),
    range: ({ value }) => ctl?.filter('range', value),
    key: ({ value }) => ctl?.filter('key', value),
    status: ({ value }) => ctl?.filter('status', value),
    runtimeRelated: ({ arg }) => ctl?.related(arg, 'system'),
    learningRelated: ({ arg }) => ctl?.related(arg, 'learning'),
    openDraft: ({ arg }) => openDraft(arg),
    openBoard: ({ arg }) => boardDetailPort.open(arg),
    openReview: ({ arg }) => openReview(arg),
    operationConfirm: ({ arg }) => openReview(arg),
    operationReject: ({ arg }) => openReview(arg),
    refresh: () => ctl?.refresh(),
    more: () => ctl?.more(),
    detail: ({ arg }) => ctl?.detail(arg, true),
    review: ({ arg }) => ctl?.review(arg),
    session: ({ arg }) => ctl?.session(arg),
    directRestore: ({ arg }) => ctl?.directRestore(arg),
    restoreState: ({ arg }) => ctl?.restoreState(arg),
  },
};
