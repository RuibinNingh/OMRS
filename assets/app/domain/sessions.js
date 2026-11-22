/**
 * 复习 Session（P6 第 3 轮起所有权在这里）：列表的加载、快照、发布，单个 Session 的详情与删除，以及进度计算。
 * - refreshSessions()：拉 /api/sessions；后发先至时只认最新一次（旧响应、旧失败都丢弃）。成功时换快照、写旧 SESSIONS 镜像；
 *   失败时保留旧列表、记下原因。两种情况都经 bus 发 'sessions'（页面据此重绘或显示错误）。返回 { ok, error }，不抛出。
 * - removeSession(id)：删除成功后先在本地去掉，并让进行中的旧加载作废（它的结果里还有这个 Session）。
 * - 当前选中 ACTIVE_FB_SESSION、题目查找、标记、加入展示板、写剪贴板等仍转调旧全局（反馈录入页只经这里碰旧代码）。
 */
import { get, post } from '../core/api.js';
import { itemsNow } from './data.js';
import { openLabelPicker as labelPicker, saveQuestionLabels } from './labels/index.js';
import { boardQuickAdd as addToBoard } from './board/index.js';

let selectedSessionId = '';

let list = [];
let loading = false;
let error = '';
let seq = 0;
let publish = () => {};
let fetchImpl;

export function connectSessions({ emit, fetch } = {}) {
  publish = typeof emit === 'function' ? emit : () => {};
  fetchImpl = fetch;
}
const opts = () => (fetchImpl ? { fetchImpl } : {});

function mirror(next) {
  list = next;
}

export const listSessions = () => list;
export const sessionsState = () => ({ loading, error });
export const openSessions = () => list.filter(s => (s.status || 'active') === 'active');

export async function refreshSessions() {
  const mine = ++seq;
  loading = true;
  error = '';
  publish('sessions', list);
  const res = await get('/api/sessions?include_unavailable=1', opts());
  if (mine !== seq) return { ok: res.ok, error: res.ok ? '' : res.error?.message || '', stale: true };
  loading = false;
  if (res.ok) mirror(Array.isArray(res.data?.sessions) ? res.data.sessions : []);
  else error = res.error?.message || '未知错误';
  publish('sessions', list);
  return { ok: res.ok, error };
}

export function removeSession(id) {
  seq += 1;
  loading = false;
  mirror(list.filter(s => s.session_id !== id));
  publish('sessions', list);
}

/** 单个 Session 的详情（含 items、feedback_uids、pending_count）。返回 { ok, data, error }。 */
export async function fetchSession(id) {
  const res = await get(`/api/session?id=${encodeURIComponent(id)}`, opts());
  return { ok: res.ok, data: res.data, error: res.ok ? '' : res.error?.message || '未知错误' };
}

/** 删除（撤销该 Session 与它的反馈）。只有服务端回 status ok 且 deleted true 才算成功。 */
export async function deleteSession(id) {
  const res = await post('/api/session/delete', { session_id: id }, opts());
  if (!res.ok) return { ok: false, error: res.error?.message || '未知错误' };
  if (res.data?.status !== 'ok' || res.data?.deleted !== true) return { ok: false, error: res.data?.msg || '计划不存在或已删除，请刷新计划列表' };
  removeSession(id);
  return { ok: true, error: '' };
}

async function writeSession(path, id, body, accepts) {
  const res = await post(path, { session_id: id, ...body }, opts());
  if (!res.ok) return { ok: false, status: res.status, error: res.error?.message || '未知错误' };
  const session = res.data?.session;
  if (res.data?.status !== 'ok' || session?.session_id !== id || !accepts(session)) {
    return { ok: false, error: res.data?.msg || '计划状态未更新，请刷新后重试' };
  }
  seq += 1;
  loading = false;
  error = '';
  mirror(list.map(value => value.session_id === id ? { ...value, ...session } : value));
  publish('sessions', list);
  return { ok: true, data: session };
}

export const setSessionPaused = (id, paused) => writeSession(
  `/api/session/${paused ? 'pause' : 'resume'}`, id, {}, session => session.status === (paused ? 'paused' : 'active'));
export const setEntrySkipped = (id, entry, skipped) => writeSession(
  '/api/session/entry-skip', id, { entry_id: entry.entry_id, question_id: entry.question_id, skipped }, () => true);
export const completeSession = (id, signature) => writeSession(
  '/api/session/complete', id, { signature }, session => session.status === 'completed');

// ── 进度（纯函数；反馈录入页经 features/feedback/state.js 再导出为 fbSessionProgress）──
export function sessionEntries(session) {
  if (Array.isArray(session?.entries)) return session.entries;
  const seen = new Set();
  const recorded = new Set(session?.feedback_uids || []);
  return (session?.uids || []).map(uid => String(uid || '').trim()).filter(uid => uid && !seen.has(uid) && seen.add(uid))
    .map(uid => ({ uid, uid_at_creation: uid, availability: 'active', feedback_submitted: recorded.has(uid) }));
}
export const sessionEntryKey = entry => entry?.entry_id || entry?.question_id || entry?.uid || '';
export function sessionUniqueUids(session) { return sessionEntries(session).map(entry => entry.uid || entry.uid_at_creation || ''); }
export function entryFeedbackState(entry) {
  return entry?.feedback_state || (entry?.feedback_submitted ? 'recorded'
    : entry?.availability === 'unresolved' ? 'unresolved'
    : entry?.availability === 'archived' || entry?.availability === 'suspended' ? 'unavailable' : 'pending');
}

export const feedbackStateLabel = {
  recorded: '已录', pending: '待录', unavailable: '不可录', skipped: '本次跳过', unresolved: '身份待确认',
};

export function progressText(progress, { ended = false, ready = false } = {}) {
  const parts = [];
  if (ended) parts.push('已结束');
  if (ended && !progress.recorded) parts.push('无反馈');
  else parts.push(`已录 ${progress.recorded}`);
  if (!ended) parts.push(`待录 ${progress.pending}`);
  for (const state of ['unavailable', 'skipped', 'unresolved']) {
    if (progress[state]) parts.push(`${feedbackStateLabel[state]} ${progress[state]}`);
  }
  if (ready && progress.can_finish) parts.push('可结束');
  return parts.join(' · ');
}

export function completionHint(progress) {
  return `已录 ${progress.recorded} · 本次跳过 ${progress.skipped} · 不可录 ${progress.unavailable}。结束后只保留这些处置与已提交的反馈。`;
}

export function sessionProgress(session) {
  const all = sessionEntries(session);
  const authoritative = session?.progress;
  const feedback_entries = all.filter(entry => entryFeedbackState(entry) === 'recorded');
  const pending_entries = all.filter(entry => authoritative ? entryFeedbackState(entry) === 'pending' : !entry.feedback_submitted);
  if (authoritative) return { ...authoritative, feedback_entries, pending_entries,
    feedback_uids: feedback_entries.map(entry => entry.uid || entry.uid_at_creation || ''),
    pending_uids: pending_entries.map(entry => entry.uid || entry.uid_at_creation || ''),
    feedback_count: authoritative.recorded, pending_count: authoritative.pending,
    complete: authoritative.total > 0 && authoritative.recorded === authoritative.total };

  return { total: all.length, ...(Array.isArray(session?.entries) ? { feedback_entries, pending_entries } : {}),
    feedback_uids: feedback_entries.map(entry => entry.uid || entry.uid_at_creation || ''),
    pending_uids: pending_entries.map(entry => entry.uid || entry.uid_at_creation || ''),
    feedback_count: feedback_entries.length, pending_count: pending_entries.length,
    complete: all.length > 0 && pending_entries.length === 0 };
}
export const bindSessionEntry = (session_id, entry_id, question_id) => post('/api/session/bind', { session_id, entry_id, question_id }, opts());

// ── 反馈录入页用的旧全局转调（原有）──
export const activeSessionId = () => selectedSessionId;
export function setActiveSessionId(id) { selectedSessionId = id || ''; }
export const findSession = id => list.find(session => session.session_id === id) || null;
export const items = () => [...itemsNow()];
export const itemByUid = uid => itemsNow().find(item => item.uid === String(uid || '').trim()) || null;
export const saveLabels = saveQuestionLabels;
export function openLabelPicker(uid, anchor) { if (uid) labelPicker(uid, anchor); }
export function boardQuickAdd(uid, options) { if (uid) addToBoard(uid, options); }
export async function copyText(text) {
  try { if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; } } catch (_) {}
  const box = document.createElement('textarea');
  box.value = text; box.className = 'clipboard-temp'; document.body.append(box); box.select();
  try { return document.execCommand('copy'); } catch (_) { return false; } finally { box.remove(); }
}

/** 测试用：清空模块状态。 */
export function resetSessions() { list = []; loading = false; error = ''; seq = 0; publish = () => {}; fetchImpl = undefined; selectedSessionId = ''; }
