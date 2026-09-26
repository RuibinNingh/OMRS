/**
 * 复习 Session（P6 第 3 轮起所有权在这里）：列表的加载、快照、发布，单个 Session 的详情与删除，以及进度计算。
 * - refreshSessions()：拉 /api/sessions；后发先至时只认最新一次（旧响应、旧失败都丢弃）。成功时换快照、写旧 SESSIONS 镜像；
 *   失败时保留旧列表、记下原因。两种情况都经 bus 发 'sessions'（页面据此重绘或显示错误）。返回 { ok, error }，不抛出。
 * - removeSession(id)：删除成功后先在本地去掉，并让进行中的旧加载作废（它的结果里还有这个 Session）。
 * - 当前选中 ACTIVE_FB_SESSION、题目查找、标记、加入展示板、写剪贴板等仍转调旧全局（反馈录入页只经这里碰旧代码）。
 */
import { get, post } from '../core/api.js';

const g = globalThis;
const fn = name => (typeof g[name] === 'function' ? g[name] : null);

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
  // SESSIONS 是旧 core.js 的 let：直接给标识符赋值（同 domain/data.js 的 DATA）。
  if (typeof SESSIONS !== 'undefined') SESSIONS = next; // eslint-disable-line no-global-assign
}

export const listSessions = () => list;
export const sessionsState = () => ({ loading, error });
export const openSessions = () => list.filter(s => (s.status || 'active') === 'active');

export async function refreshSessions() {
  const mine = ++seq;
  loading = true;
  error = '';
  publish('sessions', list);
  const res = await get('/api/sessions', opts());
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

// ── 进度（纯函数；反馈录入页经 features/feedback/state.js 再导出为 fbSessionProgress）──
export function sessionUniqueUids(session) {
  const seen = new Set();
  return (session?.uids || []).map(uid => String(uid || '').trim()).filter(uid => uid && !seen.has(uid) && seen.add(uid));
}
export function sessionProgress(session) {
  const all = sessionUniqueUids(session);
  const available = new Set((session?.feedback_uids || []).map(uid => String(uid || '').trim()));
  const feedback_uids = all.filter(uid => available.has(uid));
  const pending_uids = all.filter(uid => !available.has(uid));
  return { total: all.length, feedback_uids, pending_uids, feedback_count: feedback_uids.length, pending_count: pending_uids.length,
    complete: all.length > 0 && pending_uids.length === 0 };
}

// ── 反馈录入页用的旧全局转调（原有）──
export const activeSessionId = () => (typeof ACTIVE_FB_SESSION !== 'undefined' ? (ACTIVE_FB_SESSION || '') : '');
// ACTIVE_FB_SESSION 是 core.js 里的 let：写 globalThis.ACTIVE_FB_SESSION 会另建一个 window 属性，旧代码读不到，必须直接赋值。
export function setActiveSessionId(id) {
  if (typeof ACTIVE_FB_SESSION !== 'undefined') ACTIVE_FB_SESSION = id || ''; // eslint-disable-line no-global-assign
  else g.ACTIVE_FB_SESSION = id || '';
}
export const findSession = id => list.find(session => session.session_id === id) || null;

export const items = () => (fn('getItems') ? g.getItems() : []);
export const itemByUid = uid => (fn('getItemByUid') ? g.getItemByUid(String(uid || '').trim()) : null);
export async function saveLabels(uid, labels) {
  const save = fn('saveQuestionLabels');
  if (save && uid) return save(uid, labels);
}
export function openLabelPicker(uid, anchor) {
  const open = fn('openLabelPicker');
  if (open && uid) open(uid, anchor);
}
export function boardQuickAdd(uid, options) {
  const add = fn('boardQuickAdd');
  if (add && uid) add(uid, options);
}
export const copyText = text => (fn('copyTextToClipboard') ? g.copyTextToClipboard(text) : Promise.resolve(false));

/** 测试用：清空模块状态。 */
export function resetSessions() { list = []; loading = false; error = ''; seq = 0; publish = () => {}; fetchImpl = undefined; }
