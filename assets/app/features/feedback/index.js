/**
 * 反馈录入工作台（features 页面，页面契约见 AI/frontend/architecture.md §3）。
 * - 契约：page = { id, title, workbench, mount(root, ctx) → unmount, actions, keys }；actions / keys 命名空间与作用域都是 'feedback'。
 * - 渲染：每次状态变化 paint() → morph(root, view(state, env))；题面挂载点由 hydrate() 交给 domain/questions（qview），
 *   key=uid，判定 / 打分 / 写备注都不换挂载点（题面 KaTeX、图片、滚动保留）。
 * - 数据：Session 列表与选中态经 domain/sessions.js 读旧全局；提交后经 domain 刷新；标记定义变化听 bus 'labels'；
 *   复习调度页的进入 / 删除、标记重绘等旧入口经过渡桥发 bus（'feedback:session' / 'feedback:reset' / 'feedback:clear-results' / 'feedback:render' / 'sessions'）。
 * - 快捷键走 core/keys.js；答题卡「粘贴」用挂载期的 paste 监听（core/keys.js 只管 keydown，而 http 局域网只有 paste 事件能拿到剪贴板，见 AI/omr-import.md）。
 */
import { morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { toast } from '../../ui/toast.js';
import { dialog } from '../../ui/dialog.js';
import { editQuestion, invalidateQuestions, mountQuestionStage } from '../../domain/question/index.js';
import { reloadData } from '../../domain/data.js';
import {
  listSessions, activeSessionId, setActiveSessionId, findSession,
  refreshSessions, items as domItems, itemByUid, saveLabels, openLabelPicker, boardQuickAdd,
  copyText,
} from '../../domain/sessions.js';
import * as S from './state.js';
import { planImportText, escapeHtml } from './importer.js';
import { view, resultBody } from './view.js';

const s = S.state;
let ctl = null;

function createController(root, ctx) {
  let inflight = null;
  function env() {
    const sessions = listSessions();
    const activeId = activeSessionId();
    const session = findSession(activeId);
    const rows = s.rows;
    const entries = S.fbRailEntries(session, rows);
    s.cursor = S.clampCursor(entries, s.cursor);
    const { ready, pending } = S.fbRowsForSubmit(rows);
    return { sessions, activeId, session, rows, entries, items: domItems(), counts: { ready: ready.length, pending: pending.length } };
  }

  function hydrate() {
    root.querySelectorAll('[data-qv-host]').forEach(el => {
      if (el.dataset.qvFor === el.dataset.key) return;
      el.dataset.qvFor = el.dataset.key;
      s.stageUid = el.dataset.uid;
      mountQuestionStage(el, el.dataset.uid);
    });
  }

  function paint() { morph(root, view(s, env())); hydrate(); }

  const entriesNow = () => S.fbRailEntries(findSession(activeSessionId()), s.rows);
  const contextNow = () => S.currentContext(entriesNow(), s.rows, s.cursor);

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
    // 同时只跑一次；并发调用（进入页面的刷新 + 从复习调度跳来的 openSession）共用同一个 promise
    refresh() {
      if (inflight) return inflight;
      s.sessionsLoading = true; s.sessionsError = ''; paint();
      inflight = (async () => {
        const res = await refreshSessions(); // 不抛出；失败时保留旧列表并给原因
        if (!res.ok && !res.stale) s.sessionsError = res.error || '读取失败';
        s.sessionsLoading = false; inflight = null;
        if (ctl) paint();
      })();
      return inflight;
    },
    selectSession(id) {
      setActiveSessionId(id || '');
      rebuildRows(findSession(id));
      s.status = null; s.lastResult = null;
      paint();
    },
    async openSession(id) {
      await api.refresh();
      if (!findSession(id)) { toast('暂时无法读取该计划，请刷新后重试。', { kind: 'error' }); return; }
      api.selectSession(id);
    },
    addRow() {
      s.rows.push({ id: Date.now() + Math.random(), uid: '', score: 5, correct: null, note: '', scoreTouched: false });
      const entries = entriesNow();
      const at = entries.findIndex(entry => entry.index === s.rows.length - 1);
      s.cursor = S.clampCursor(entries, at >= 0 ? at : 0);
      paint();
    },
    go(index) {
      const entries = entriesNow();
      s.cursor = S.clampCursor(entries, index);
      paint();
    },
    step(delta) { if (entriesNow().length) api.go(s.cursor + delta); },
    nextOpen() {
      const at = S.nextOpenIndex(entriesNow(), s.rows, s.cursor);
      if (at >= 0) api.go(at);
    },
    verdict(correct) { const c = contextNow(); if (c && S.setVerdict(c.row, correct)) paint(); },
    score(value) { const c = contextNow(); if (c && S.setScore(c.row, value)) paint(); },
    scoreKey(n) { const c = contextNow(); if (!c || c.row.correct == null) return false; api.score(n); return undefined; },
    note(value) { const c = contextNow(); if (c) c.row.note = value; },
    setUid(value) {
      const entry = entriesNow()[s.cursor];
      if (!entry || entry.index < 0) return;
      const row = s.rows[entry.index];
      if (!row) return;
      row.uid = String(value || '').trim();
      s.stageUid = '';
      paint();
    },
    drop() { const c = contextNow(); if (!c) return; s.rows.splice(c.index, 1); s.stageUid = ''; paint(); },
    async toggleLabel(name) {
      const c = contextNow();
      const item = c && c.row.uid ? itemByUid(c.row.uid) : null;
      if (!item || !name) return;
      const labels = new Set(item.labels || []);
      labels.has(name) ? labels.delete(name) : labels.add(name);
      await saveLabels(item.uid, [...labels]);
      paint();
    },
    openLabels(el) {
      const c = contextNow();
      const item = c && c.row.uid ? itemByUid(c.row.uid) : null;
      if (item) openLabelPicker(item.uid, el);
    },
    board(el, shift) {
      const c = contextNow();
      if (c?.row?.uid) boardQuickAdd(c.row.uid, { anchor: el, direct: !!shift });
    },
    edit() { const c = contextNow(); if (c?.row?.uid) editQuestion(c.row.uid); },
    toggleImport() { s.importOpen = !s.importOpen; paint(); },
    // ── 导入：三个入口一套解析（importer.js 纯函数算计划，这里落到 state）──
    importText(text, options = {}) {
      const plan = planImportText(text, { session: findSession(activeSessionId()), findSession, from: options.from });
      s.importStatus = { tone: plan.tone, html: plan.html };
      if (plan.ok) {
        if (plan.activeId !== undefined) setActiveSessionId(plan.activeId);
        s.rows = plan.rows; s.stageUid = ''; s.cursor = 0; s.status = null; s.lastResult = null;
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
      const ok = await copyText(buildFeedbackAiPrompt());
      s.promptStatus = ok ? { tone: 'ok', text: '✓ 已复制。把批改结果发给 AI，要求它只返回反馈 JSON。' } : { tone: 'danger', text: '✕ 复制失败，请检查剪贴板权限' };
      paint();
    },
    reopenResults() { if (s.lastResult) openResultsDialog(s.lastResult); },
    clearResults() { s.lastResult = null; if (ctl) paint(); },
    resetForm() {
      setActiveSessionId('');
      s.rows = []; s.cursor = 0; s.stageUid = ''; s.status = null; s.lastResult = null;
      if (ctl) paint();
    },
    async submit() {
      if (s.submitting) return;
      const rows = s.rows;
      if (!rows.length) { toast(activeSessionId() ? '当前 Session 已没有待录入题目' : '请先添加反馈条目', { kind: 'warn' }); return; }
      const { ready, pending } = S.fbRowsForSubmit(rows);
      if (!ready.length) { toast(rows.length ? '当前批次还没有完成判定，请至少点选一道题的「对」或「错」。' : '请先添加反馈条目', { kind: 'warn' }); return; }
      const seen = new Set();
      const dup = ready.find(row => { const uid = (row.uid || '').trim(); if (!uid || seen.has(uid)) return true; seen.add(uid); return false; });
      if (dup) { toast(`UID「${dup.uid || '空白'}」重复或为空，请检查后再提交。`, { kind: 'warn' }); return; }
      const activeId = activeSessionId();
      const session = findSession(activeId);
      const submitted = new Set(session?.feedback_uids || []);
      const repeat = ready.find(row => submitted.has((row.uid || '').trim()));
      if (repeat) { toast(`题目「${repeat.uid}」已经录入过反馈，请不要重复提交。若要修正，请到「历史记录」中操作。`, { kind: 'warn' }); return; }
      const feedbacks = ready.map(row => ({ uid: row.uid, sub_score: row.score, is_correct: row.correct, note: row.note }));
      s.submitting = true; s.status = null; paint();
      const res = await post('/api/feedback', { feedbacks, session_id: activeId || '' });
      s.submitting = false;
      if (!res.ok) { s.status = { tone: 'danger', text: `提交失败：${res.error?.message || '未知错误'}` }; paint(); return; }
      const results = Array.isArray(res.data?.results) ? res.data.results : [];
      const okCount = results.filter(row => row.status === 'ok').length;
      s.lastResult = { rows: results, okCount, total: feedbacks.length, sessionId: activeId, at: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) };
      openResultsDialog(s.lastResult);
      await reloadData();
      await invalidateQuestions(feedbacks.map(row => row.uid));
      try { await refreshSessions(); } catch (error) { /* 列表刷新失败不挡提交结果 */ }
      if (activeId) {
        const updated = findSession(activeId);
        const remaining = updated ? S.fbSessionProgress(updated).pending_count : 0;
        s.status = { tone: 'ok', text: `本次已提交 ${okCount}/${feedbacks.length} 条，${remaining ? `还剩 ${remaining} 题待录入` : '本 Session 已全部录入'}` };
        rebuildRows(updated);
      } else {
        s.rows = pending; s.cursor = 0; s.stageUid = '';
        s.status = { tone: 'ok', text: `本次已提交 ${okCount}/${feedbacks.length} 条${pending.length ? `，${pending.length} 道未判定题已保留` : ''}` };
        focusFirstOpen();
      }
      paint();
    },
  };
  return api;
}

function openResultsDialog(result) {
  dialog({ title: '本次处理结果', body: resultBody(result), okText: '知道了', hideCancel: true, size: 'lg' });
}

function buildFeedbackAiPrompt() {
  const activeId = activeSessionId();
  const selected = s.rows.filter(row => (row.uid || '').trim());
  const sessionLine = activeId ? `当前 Session_ID：${activeId}` : '当前未选择 Session；如果我没有另行说明，请输出空 session_id。';
  const scoped = selected.length
    ? selected.map((row, i) => `${i + 1}. ${row.uid}`).join('\n')
    : domItems().slice(0, 200).map((item, i) => `${i + 1}. ${item.uid}（${item.subject || ''}/${item.category || ''}）`).join('\n');
  return [
    '你是 OMRS 错题复习反馈整理助手。我会给你一份纸面批改结果、口述复盘、表格或截图内容。请只把它整理成 OMRS 可导入的反馈 JSON，不要解释。', '',
    '规则：',
    '1. 每条反馈必须对应一个准确 UID；如果无法确定 UID，就不要输出该条。',
    '2. is_correct 只能是 true 或 false。答对/全对/正确=true；答错/错误/不会/漏做=false。',
    '3. sub_score 是 0-10 的整数。未给分时：答对默认 10，答错默认 4；明显完全不会可给 0-2。',
    '4. note 写简短备注，如页码、错因、计算失误；没有就空字符串。',
    '5. 只输出一个 JSON 对象，可被 JSON.parse 直接解析。不要 Markdown 代码块，不要多余文字。', '',
    sessionLine, '', '可用 UID 清单：', scoped || '（暂无预置 UID；请按我提供的 UID 输出）', '',
    '输出格式：', '{"type":"omrs-feedback","version":1,"session_id":"","items":[{"uid":"","is_correct":true,"sub_score":10,"note":""}]}',
  ].join('\n');
}

const onButton = event => !!event.target?.closest?.('button, a[href], [role="button"], summary');
const active = fn => (...args) => (ctl ? fn(...args) : false);

export const page = {
  id: 'feedback',
  title: '反馈录入',
  workbench: true,
  mount(root, ctx) {
    ctl = createController(root, ctx);
    const onPaste = event => ctl?.onPaste(event);
    document.addEventListener('paste', onPaste);
    const offs = [
      ctx.bus.on('labels', () => ctl?.paint()),
      ctx.bus.on('sessions', () => ctl?.paint()),
      ctx.bus.on('feedback:render', () => ctl?.paint()),
      ctx.bus.on('feedback:session', id => ctl?.openSession(id)),
      ctx.bus.on('feedback:reset', () => ctl?.resetForm()),
      ctx.bus.on('feedback:clear-results', () => ctl?.clearResults()),
      () => document.removeEventListener('paste', onPaste),
    ];
    ctl.paint();
    ctl.refresh(); // 进入即拉最新 Session 进度（取代旧 enter 钩子 refreshSessions）
    return () => { offs.forEach(off => off()); ctl = null; };
  },
  actions: {
    // data-change 挂在 select 的外层（ui/select 不收 action），值从事件目标读
    session: ({ event }) => ctl?.selectSession(event.target.value),
    refresh: () => ctl?.refresh(),
    addRow: () => ctl?.addRow(),
    go: ({ arg }) => ctl?.go(arg),
    verdict: ({ arg }) => ctl?.verdict(arg === '1'),
    score: ({ value }) => ctl?.score(value),
    note: ({ value }) => ctl?.note(value),
    uid: ({ value }) => ctl?.setUid(value),
    drop: () => ctl?.drop(),
    label: ({ arg }) => ctl?.toggleLabel(arg),
    labels: ({ el }) => ctl?.openLabels(el),
    board: ({ el, event }) => ctl?.board(el, event.shiftKey),
    submit: () => ctl?.submit(),
    toggleImport: () => ctl?.toggleImport(),
    readClipboard: () => ctl?.readClipboard(),
    draft: ({ value }) => ctl?.draft(value),
    importBox: () => ctl?.importBox(document.getElementById('fb-json')?.value || ''),
    copyPrompt: () => ctl?.copyPrompt(),
    reopenResults: () => ctl?.reopenResults(),
  },
  keys: {
    j: active(() => ctl.step(1)),
    arrowdown: active(() => ctl.step(1)),
    k: active(() => ctl.step(-1)),
    arrowup: active(() => ctl.step(-1)),
    1: active(() => ctl.verdict(true)),
    2: active(() => ctl.verdict(false)),
    ...Object.fromEntries([0, 3, 4, 5, 6, 7, 8, 9].map(n => [String(n), active(() => ctl.scoreKey(n))])),
    enter: active(event => (onButton(event) ? false : ctl.nextOpen())),
    e: active(() => ctl.edit()),
    'mod+enter': active(() => ctl.submit()),
  },
};
