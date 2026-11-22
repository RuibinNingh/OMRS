import { questionItem } from '../../domain/question/ref.js';
import { morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { toast } from '../../ui/toast.js';
import { confirm, dialog } from '../../ui/dialog.js';
import { editQuestion, invalidateQuestions, mountQuestionStage, mountReflections } from '../../domain/question/index.js';
import { reloadData } from '../../domain/data.js';
import {
  listSessions, activeSessionId, setActiveSessionId, findSession,
  refreshSessions, items as domItems, saveLabels, openLabelPicker, boardQuickAdd,
  copyText, setEntrySkipped, completeSession, completionHint, entryFeedbackState, sessionEntryKey,
} from '../../domain/sessions.js';
import * as S from './state.js';
import { buildFeedbackAiPrompt, planImportText, escapeHtml } from './importer.js';
import { view, resultBody } from './view.js';

export function createFeedbackController(root, ctx, services = {}) {
  const s = services.state || S.state;
  const io = { post, toast, listSessions, activeSessionId, setActiveSessionId, findSession,
    domItems, refreshSessions, reloadData, invalidateQuestions, setEntrySkipped, completeSession, confirm, openResultsDialog, ...services };
  let alive = true;
  let inflight = null;
  let reflections = null;
  let reflectionsHost = null;
  const offGuard = ctx?.router?.setLeaveGuard?.(() => reflections?.canLeave() ?? true);
  function currentSession() {
    const id = io.activeSessionId();
    return id && s.sessionSnapshot?.session_id === id ? s.sessionSnapshot : io.findSession(id);
  }

  function adoptSession(session) {
    s.sessionSnapshot = session;
    s.accepted = [];
    if (session) s.rows = S.mergeSessionRows(session, s.rows);
  }

  async function reloadSession(id) {
    let result;
    try { result = await io.refreshSessions(); }
    catch (error) { result = { ok: false, error: error.message }; }
    const session = result.ok && !result.stale ? io.findSession(id) : null;
    if (session && io.activeSessionId() === id) adoptSession(session);
    return { ...result, session };
  }

  function env() {
    const sessions = io.listSessions();
    const activeId = io.activeSessionId();
    const session = currentSession();
    const rows = s.rows;
    const entries = entriesNow();
    s.cursor = S.clampCursor(entries, s.cursor);
    const { ready, pending } = S.fbRowsForSubmit(rows);
    return { sessions, activeId, session, rows, entries, items: io.domItems(), counts: { ready: ready.length, pending: pending.length } };
  }

  function hydrate() {
    const host = root.querySelector('[data-reflections-host]');
    if (host !== reflectionsHost) {
      reflections?.dispose();
      reflectionsHost = host;
      reflections = host ? mountReflections(host, host.dataset.questionId, { idPrefix: `fb-ref-${host.dataset.questionId}` }) : null;
    }
    root.querySelectorAll('[data-qv-host]').forEach(el => {
      if (el.dataset.qvFor === el.dataset.key) return;
      el.dataset.qvFor = el.dataset.key;
      s.stageUid = el.dataset.uid;
      mountQuestionStage(el, el.dataset.uid, entriesNow()[s.cursor]?.question_id, el.dataset.readOnly === '1');
    });
  }

  function paint() { if (!alive) return; if (services.paint) { services.paint(s); return; } morph(root, view(s, env())); hydrate(); }

  const entriesNow = () => S.fbRailEntries(currentSession(), s.rows).map(entry =>
    s.accepted.includes(sessionEntryKey(entry)) ? { ...entry, feedback_state: 'recorded', feedback_submitted: true, recorded: true } : entry);
  const contextNow = () => {
    const session = currentSession();
    if (session?.status === 'paused' || session?.status === 'completed') return null;
    return S.currentContext(entriesNow(), s.rows, s.cursor);
  };

  // ── 光标定位到第一道未判定（换 Session / 导入后调）──
  function focusFirstOpen() {
    const entries = entriesNow();
    const open = S.firstOpenIndex(entries, s.rows);
    s.cursor = S.clampCursor(entries, open >= 0 ? open : 0);
  }

  function rebuildRows(session) {
    s.rows = session ? S.fbRowsForSession(session) : [];
    s.stageUid = '';
    focusFirstOpen();
  }

  const api = {
    paint,
    syncAfterQuestion() {
      const session = io.findSession(io.activeSessionId());
      if (!session || s.submitting || reflections?.hasPendingEdit()) return;
      adoptSession(session);
      if (!contextNow() && S.firstOpenIndex(entriesNow(), s.rows) >= 0) focusFirstOpen();
      paint();
    },
    // 同时只跑一次；并发调用（进入页面的刷新 + 从复习调度跳来的 openSession）共用同一个 promise
    refresh() {
      if (s.submitting) return;
      if (inflight) return inflight;
      s.sessionsLoading = true; s.sessionsError = ''; paint();
      inflight = (async () => {
        const id = io.activeSessionId();
        const res = await reloadSession(id);
        if ((!res.ok || (id && !res.session)) && !res.stale) s.sessionsError = res.error || '计划已不在列表中';
        if (res.session && S.firstOpenIndex(entriesNow(), s.rows) >= 0 && !contextNow()) focusFirstOpen();
        s.sessionsLoading = false; inflight = null;
        paint();
      })();
      return inflight;
    },
    selectSession(id) {
      if (s.submitting) return;
      s.formGeneration += 1;
      const same = io.activeSessionId() === id;
      io.setActiveSessionId(id || '');
      if (same) adoptSession(io.findSession(id));
      else {
        s.sessionSnapshot = io.findSession(id);
        s.accepted = [];
        rebuildRows(s.sessionSnapshot);
      }
      s.status = null; s.lastResult = null;
      paint();
    },
    async openSession(id) {
      await api.refresh();
      if (!alive) return;
      if (!io.findSession(id)) { io.toast('暂时无法读取该计划，请刷新后重试。', { kind: 'error' }); return; }
      api.selectSession(id);
    },
    addRow() {
      if (s.submitting || io.activeSessionId()) return;
      s.rows.push({ id: Date.now() + Math.random(), uid: '', score: 5, correct: null, note: '', scoreTouched: false });
      const entries = entriesNow();
      const at = entries.findIndex(entry => entry.index === s.rows.length - 1);
      s.cursor = S.clampCursor(entries, at >= 0 ? at : 0);
      paint();
    },
    go(index) {
      if (s.submitting) return;
      const entries = entriesNow();
      s.cursor = S.clampCursor(entries, index);
      paint();
    },
    step(delta) { if (entriesNow().length) api.go(s.cursor + delta); },
    nextOpen() {
      const at = S.nextOpenIndex(entriesNow(), s.rows, s.cursor);
      if (at >= 0) api.go(at);
    },
    verdict(correct) { if (s.submitting) return; const c = contextNow(); if (c && S.setVerdict(c.row, correct)) paint(); },
    score(value) { if (s.submitting) return; const c = contextNow(); if (c && S.setScore(c.row, value)) paint(); },
    scoreKey(n) { const c = contextNow(); if (!c || c.row.correct == null) return false; api.score(n); return undefined; },
    note(value) { if (s.submitting) return; const c = contextNow(); if (c) c.row.note = value; },
    setUid(value) {
      if (s.submitting) return;
      const entry = entriesNow()[s.cursor];
      if (!entry || entry.index < 0) return;
      const row = s.rows[entry.index];
      if (!row) return;
      if (io.findSession(io.activeSessionId()) && !entry.extra) return;
      row.uid = String(value || '').trim();
      row.question_id = io.domItems().find(item => item.uid === row.uid)?.question_id || '';
      s.stageUid = '';
      paint();
    },
    drop() { if (s.submitting || io.activeSessionId()) return; const c = contextNow(); if (!c) return; s.rows.splice(c.index, 1); s.stageUid = ''; paint(); },
    async toggleLabel(name) {
      const c = contextNow();
      const item = c && c.row.uid ? questionItem(c.row.question_id || c.row.uid, io.domItems()) : null;
      if (!item || !name) return;
      const labels = new Set(item.labels || []);
      labels.has(name) ? labels.delete(name) : labels.add(name);
      await saveLabels(item, [...labels]);
      paint();
    },
    openLabels(el) {
      const c = contextNow();
      const item = c && c.row.uid ? questionItem(c.row.question_id || c.row.uid, io.domItems()) : null;
      if (item) openLabelPicker(item, el);
    },
    board(el, shift) {
      const c = contextNow();
      if (c?.row?.uid) boardQuickAdd(c.row, { anchor: el, direct: !!shift });
    },
    edit() { const c = contextNow(); if (c?.row?.uid) editQuestion(c.row); },
    toggleImport() { s.importOpen = !s.importOpen; paint(); },
    // ── 导入：三个入口一套解析（importer.js 纯函数算计划，这里落到 state）──
    importText(text, options = {}) {
      if (s.submitting) return false;
      const session = currentSession();
      const find = id => session?.session_id === id ? session : io.findSession(id);
      const plan = planImportText(text, { session, findSession: find, drafts: s.rows, from: options.from });
      s.importStatus = { tone: plan.tone, html: plan.html };
      if (plan.ok) {
        s.formGeneration += 1;
        if (plan.activeId !== undefined) {
          const next = find(plan.activeId);
          const previous = next?.session_id === session?.session_id ? s.rows : [];
          io.setActiveSessionId(plan.activeId);
          s.sessionSnapshot = next;
          s.accepted = [];
          if (next) s.rows = S.mergeSessionRows(next, [...previous, ...plan.rows]);
          else s.rows = plan.rows.map(row => row.question_id ? row
            : { ...row, question_id: io.domItems().find(item => item.uid === row.uid)?.question_id || '' });
        } else s.rows = plan.rows;
        s.stageUid = ''; s.cursor = 0; s.status = null; s.lastResult = null;
        focusFirstOpen();
        if (options.clearBox) s.importText = '';
      }
      paint();
      return plan.ok;
    },
    draft(value) { s.importText = value; },
    importBox(value) { api.importText(value, { clearBox: true }); },
    async readClipboard() {
      s.importOpen = true;
      if (!navigator.clipboard || !navigator.clipboard.readText) {
        s.importStatus = { tone: 'warn', html: '这个浏览器不允许直接读剪贴板（非 HTTPS / 非 localhost 时通常如此）。请在本页空白处直接按 Ctrl / ⌘ + V，或粘到下面的框里再点「导入 JSON」。' };
        paint(); return;
      }
      let text = '';
      try { text = await navigator.clipboard.readText(); }
      catch (error) { s.importStatus = { tone: 'danger', html: `✕ 读剪贴板失败：${escapeHtml((error && error.message) || String(error))}。可能需要在浏览器里允许「剪贴板」权限，或直接按 Ctrl / ⌘ + V。` }; paint(); return; }
      if (!String(text || '').trim()) { s.importStatus = { tone: 'warn', html: '剪贴板是空的。先在 OMR 的识别结果页复制 JSON 再回来。' }; paint(); return; }
      api.importText(text, { from: 'clipboard' });
    },
    onPaste(event) {
      if (!root.classList.contains('active') && !document.getElementById('panel-feedback')?.classList.contains('active')) return;
      if (event.target.closest?.('input, textarea, select')) return;
      if (document.querySelector('dialog[open]:not(.is-closing), .modal-overlay.open')) return;
      const text = event.clipboardData?.getData('text/plain') || '';
      if (!String(text).trim()) return;
      event.preventDefault();
      s.importOpen = true;
      api.importText(text, { from: 'clipboard' });
    },
    async copyPrompt() {
      const ok = await copyText(buildFeedbackAiPrompt(io.activeSessionId(), s.rows, io.domItems()));
      s.promptStatus = ok ? { tone: 'ok', text: '✓ 已复制。把批改结果发给 AI，要求它只返回反馈 JSON。' } : { tone: 'danger', text: '✕ 复制失败，请检查剪贴板权限' };
      paint();
    },
    reopenResults() { if (s.lastResult) openResultsDialog(s.lastResult); },
    clearResults() { s.lastResult = null; paint(); },
    resetForm() {
      if (s.submitting) return;
      s.formGeneration += 1;
      io.setActiveSessionId('');
      s.sessionSnapshot = null; s.accepted = [];
      s.rows = []; s.cursor = 0; s.stageUid = ''; s.status = null; s.lastResult = null;
      paint();
    },
    async skip(skipped) {
      const session = currentSession();
      const entry = entriesNow()[s.cursor];
      const kind = entryFeedbackState(entry);
      if (s.submitting || !session || (session.status || 'active') !== 'active' || !entry?.entry_id
          || (skipped ? !['pending', 'unresolved'].includes(kind) : kind !== 'skipped')) return;
      const row = s.rows[entry.index];
      const id = session.session_id;
      s.submitting = true; paint();
      try {
        if (skipped && !(await io.confirm(`仅本次跳过第 ${entry.number} 题？`, {
          hint: `不会记为答错，也不改变题库或复习日期。${row?.correct != null ? '本次不会提交这条反馈。' : ''}`,
          okText: '仅本次跳过',
        }))) return;
        if (!alive) return;
        const result = await io.setEntrySkipped(id, entry, skipped);
        if (!result.ok) {
          await reloadSession(id);
          s.status = { tone: 'warn', text: result.error };
          return;
        }
        adoptSession(result.data);
        s.status = null;
        if (skipped) {
          const next = S.nextOpenIndex(entriesNow(), s.rows, s.cursor);
          if (next >= 0) s.cursor = next;
          else if (S.firstOpenIndex(entriesNow(), s.rows) >= 0) focusFirstOpen();
        }
      } finally { s.submitting = false; paint(); }
    },
    async finish() {
      const session = currentSession();
      if (s.submitting || !session?.progress?.can_finish || s.accepted.length) return;
      s.submitting = true; paint();
      try {
        if (!await io.confirm('结束本次复习？', { hint: completionHint(session.progress), okText: '结束本次' }) || !alive) return;
        const result = await io.completeSession(session.session_id, session.progress.signature);
        if (!result.ok) {
          await reloadSession(session.session_id);
          s.status = { tone: 'warn', text: result.error };
          return;
        }
        adoptSession(result.data);
        s.status = null;
      } finally { s.submitting = false; paint(); }
    },
    async openPlan() {
      const id = io.activeSessionId();
      if (!id || s.submitting) return;
      if (await ctx.router.go('schedule') === 'schedule') ctx.bus.emit('schedule:open-plan', id);
    },
    async submit() {
      if (s.submitting) return;
      const rows = s.rows;
      const activeId = io.activeSessionId();
      const session = currentSession();
      if (activeId && !session) { io.toast('请刷新并确认原复习计划后再提交。', { kind: 'warn' }); return; }
      if (session?.status === 'paused' || session?.status === 'completed') {
        io.toast(session.status === 'paused' ? '复习计划已暂停，请到复习调度恢复后继续。' : '复习计划已结束。', { kind: 'warn' });
        return;
      }
      const { ready } = S.fbRowsForSubmit(rows);
      if (!ready.length) { io.toast(rows.length ? '请先判定至少一道待录题。' : '当前没有待提交的反馈。', { kind: 'warn' }); return; }
      const seen = new Set();
      const dup = ready.find(row => {
        const identity = sessionEntryKey(row);
        if (!identity || seen.has(identity)) return true;
        seen.add(identity);
        return false;
      });
      if (dup) { io.toast(`UID「${dup.uid || '空白'}」重复或为空，请检查后再提交。`, { kind: 'warn' }); return; }
      const feedbacks = S.submitPayload(ready);
      const generation = s.formGeneration;
      s.submitting = true; s.status = null; paint();
      const res = await io.post('/api/feedback', { feedbacks, session_id: activeId || '' });
      if (s.formGeneration !== generation) { if (res.ok) await io.reloadData(); return; }
      if (!res.ok) {
        if (activeId) await reloadSession(activeId);
        s.submitting = false;
        s.status = { tone: 'danger', text: `提交失败：${res.error?.message || '未知错误'}` };
        paint(); return;
      }
      const results = Array.isArray(res.data?.results) ? res.data.results : [];
      const successful = results.filter(row => row.status === 'ok');
      const okCount = successful.length;
      s.lastResult = { rows: results, okCount, total: feedbacks.length, sessionId: activeId, at: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) };
      const retained = S.remainingFeedbackRows(rows, results);
      s.rows = retained;
      if (activeId) for (const row of successful) s.accepted.push(sessionEntryKey(row));
      if (alive) io.openResultsDialog(s.lastResult);
      await io.reloadData();
      await io.invalidateQuestions(successful.map(row => row.uid));
      const refreshed = activeId ? await reloadSession(activeId) : null;
      if (s.formGeneration !== generation) return;
      const tone = okCount === feedbacks.length ? 'ok' : okCount ? 'warn' : 'danger';
      const text = `本次已提交 ${okCount}/${feedbacks.length} 条`;
      let detail = '';
      if (activeId && !refreshed.session) detail = '，计划进度刷新失败，未成功条目已保留';
      else if (!activeId && retained.length) detail = `，${retained.length} 道未成功或未判定题已保留`;
      s.status = { tone, text: text + detail };
      s.submitting = false; s.cursor = 0; s.stageUid = ''; focusFirstOpen();
      paint();
    },
  };
  // 换题、换计划或提交前先处理错因草稿，避免反馈操作悄悄带走未保存内容。
  for (const name of ['refresh', 'selectSession', 'addRow', 'go', 'setUid', 'drop', 'importText', 'resetForm', 'submit', 'skip', 'finish']) {
    const action = api[name];
    api[name] = (...args) => {
      if (!reflections) return action(...args);
      const host = reflectionsHost;
      return reflections.canLeave().then(ok => {
        if (ok && alive && reflectionsHost === host) return action(...args);
        paint();
      });
    };
  }
  api.dispose = () => { alive = false; reflections?.dispose(); offGuard?.(); };
  return api;
}

function openResultsDialog(result) {
  dialog({ title: '本次处理结果', body: resultBody(result), okText: '知道了', hideCancel: true, size: 'lg' });
}
