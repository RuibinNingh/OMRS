/** Ledger 历史页：列表生命周期与修正操作。 */
import { morph } from '../../core/dom.js';
import { confirm, prompt } from '../../ui/dialog.js';
import { fetchHistory, postHistoryCorrection, notifyHistoryChanged, ledgerTimeZone } from '../../domain/history.js';
import { reloadData } from '../../domain/data.js';
import { refreshSessions } from '../../domain/sessions.js';
import { invalidateQuestions } from '../../domain/question/index.js';
import { state as s, readPreferences, reviewPayload } from './state.js';
import { view } from './view.js';

let ctl = null;

function createController(root, ctx) {
  const host = root.querySelector('#hist-app') || root;
  let alive = true;
  let loadSeq = 0;
  let slow = 0;
  const paint = () => { if (alive) morph(host, view(s, ledgerTimeZone())); };
  const rowOf = seq => s.commits.find(row => String(row.seq) === String(seq));

  function scrollToLatest() {
    const box = host.querySelector('#history-timeline');
    if (box) box.scrollTop = s.sort === 'desc' ? 0 : box.scrollHeight;
  }

  async function load({ scroll = false } = {}) {
    const mine = ++loadSeq;
    clearTimeout(slow);
    if (!s.commits.length) {
      slow = setTimeout(() => { if (alive && mine === loadSeq) { s.phase = 'loading'; paint(); } }, 300);
    }
    const result = await fetchHistory();
    clearTimeout(slow);
    if (!alive || mine !== loadSeq) return result;
    if (result.ok) {
      s.commits = result.commits;
      s.retraction = result.retraction;
      s.phase = 'ready';
      s.error = '';
    } else {
      s.phase = 'error';
      s.error = result.error;
    }
    paint();
    if (scroll && result.ok) scrollToLatest();
    return result;
  }

  function savePreference(key, value) {
    try { localStorage.setItem(key, value); } catch { /* 本地存储不可用时，本次页面状态仍有效。 */ }
  }

  async function perform(seq, prepare) {
    const key = String(seq);
    if (!s.edit || s.busy.has(key)) return;
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
    paint, load,
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
    dispose() { alive = false; loadSeq += 1; clearTimeout(slow); },
  };
}

export const page = {
  id: 'history', title: '历史记录',
  mount(root, ctx) {
    Object.assign(s, readPreferences(localStorage));
    ctl = createController(root, ctx);
    const off = [ctx.bus.on('history:changed', payload => {
      if (payload?.source !== 'history') ctl?.load();
    }), ctx.bus.on('ledger:tz', () => ctl?.paint())];
    ctl.paint();
    ctl.load({ scroll: true });
    return () => { off.forEach(stop => stop()); ctl?.dispose(); ctl = null; };
  },
  actions: {
    sort: ({ value }) => ctl?.sort(value),
    mode: () => ctl?.mode(),
    corrections: () => ctl?.corrections(),
    refresh: () => ctl?.load(),
    review: ({ arg }) => ctl?.review(arg),
    session: ({ arg }) => ctl?.session(arg),
    directRestore: ({ arg }) => ctl?.directRestore(arg),
    restoreState: ({ arg }) => ctl?.restoreState(arg),
  },
};
