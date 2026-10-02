import { questionItem } from './ref.js';
/**
 * qview 的挂载与交互（从旧 assets/qview.js、questions.js 迁入）：题目详情缓存、挂载 / 失效重绘、工具按钮委托、题图缺失降级。
 *
 * - 详情缓存归本模块（P6 起）：旧画廊、展示板、导出读的 QUESTION_CACHE / QUESTION_PENDING 是过渡桥挂的只读全局，指向这里的对象。
 * - 挂载点由 qvRender 标上 data-qv-mount，它同时是 qview 的尺寸容器（qview.css 的 `container: qv`），
 *   所以「窄了就单栏」由挂载点宽度决定，页面不用再各自补容器查询。
 * - 题目弹窗在 modal.js（ui/dialog 外壳），Markdown 编辑器在 editor.js；写操作在 ops.js。
 *   这几个文件与本文件互相 import，只在调用时取对方的函数，模块求值顺序无关。
 */
import { raw } from '../../core/html.js';
import { render } from '../../core/dom.js';
import { get } from '../../core/api.js';
import { qvHtml, qvOptions } from './view.js';
import { editQuestion, suspendQuestion, resumeQuestion, deleteQuestion } from './ops.js';
import { closeModal, bindModalKeys } from './modal.js';
import { itemOf } from '../items.js';
import { boardQuickAdd } from '../board/index.js';
import { openLabelPicker } from '../labels/index.js';

const cache = {};
const pending = {};
const detailCache = () => cache;
const pendingCache = () => pending;
/** 过渡桥用：旧代码读的 QUESTION_CACHE / QUESTION_PENDING（只读全局）。 */
export const detailCacheObject = () => cache;
export const pendingDetailsObject = () => pending;

const mounts = new Map();     // 挂载点元素 → { uid, opts }
const contexts = {};          // 上下文名 → uid 序列，供弹窗翻页

export const cachedDetail = uid => {
  const detail = detailCache()[uid];
  const item = questionItem(uid);
  if (detail?.question_id && item?.question_id && detail.question_id !== item.question_id) { delete detailCache()[uid]; return null; }
  return detail || null;
};
/** 题目被删除 / 迁移 / 改正文后丢掉旧详情，下次挂载重新拉取。 */
export function dropDetail(uid) { delete detailCache()[String(uid || '').trim()]; }

/** 拉详情（去重、缓存）。失败时缓存一份带 _fallback 的降级副本，qview 据此显示「无法加载 + 重试」。 */
export function ensureDetail(uid, questionId = '') {
  const key = String(uid || '').trim();
  if (!key) return Promise.resolve(null);
  const identity = questionId || questionItem(key)?.question_id || '';
  const existing = cachedDetail(key);
  if (existing && (!identity || existing.question_id === identity)) return Promise.resolve(existing);
  const pendingKey = `${key}|${identity}`;
  if (pending[pendingKey]) return pending[pendingKey];
  pending[pendingKey] = (async () => {
    let detail;
    try {
      const query = identity ? `question_id=${encodeURIComponent(identity)}` : `uid=${encodeURIComponent(key)}`;
      const res = await get(`/api/question?${query}`);
      if (!res.ok || !res.data || res.data.error) throw new Error(res.error?.message || res.data?.error || '题目详情读取失败');
      if (identity && res.data.question_id !== identity) throw new Error('题目身份已变化，请刷新后重试');
      detail = res.data;
    } catch (error) {
      const item = questionItem(identity || key) || {};
      detail = { uid: key, question_id: identity, subject: item.subject || '', category: item.category || '', difficulty: item.difficulty || '',
        question: '（无法加载题目预览）', notes: '', answer: '', history: '', tag: item.tag || '',
        knowledge_tags: item.knowledge_tags || [], _fallback: true };
    } finally { delete pending[pendingKey]; }
    const current = questionItem(key);
    if (!identity || !current?.question_id || current.question_id === identity) cache[key] = detail;
    return detail;
  })();
  return pending[pendingKey];
}

export function qvSetContext(name, uids) {
  contexts[name] = [...new Set((uids || []).map(uid => String(uid || '').trim()).filter(Boolean))];
  return contexts[name];
}
export const qvContext = name => contexts[name] || [];

/** 挂载：拉详情 → 渲染 → 登记。切到别的题时丢弃晚到的结果。target 可以是选择器或元素。 */
export async function qvRender(target, uid, opts) {
  const mount = typeof target === 'string' ? document.querySelector(target) : target;
  if (!mount) return null;
  const key = String(uid || '').trim();
  if (!key) { mounts.delete(mount); render(mount, raw('')); return null; }
  mount.dataset.qvMount = '1';
  const question_id = opts?.question_id || questionItem(key)?.question_id || '';
  const request = { uid: key, question_id, opts: qvOptions({ ...opts, question_id }) };
  mounts.set(mount, request);
  if (!detailCache()[key]) render(mount, raw('<div class="qv-loading">正在加载题目…</div>'));
  const detail = await ensureDetail(key, question_id);
  const current = mounts.get(mount);
  if (current !== request) return null;
  current.detail = detail;
  render(mount, raw(qvHtml(detail, questionItem(question_id || key) || {}, current.opts)));
  return detail;
}

export function qvUnmount(mount) { if (mount) mounts.delete(mount); }

function pruned() {
  const live = [];
  mounts.forEach((state, mount) => { if (mount.isConnected) live.push([mount, state]); else mounts.delete(mount); });
  return live;
}

/** 失效重绘：清该题详情缓存，重绘所有挂着它的容器。 */
export async function qvInvalidate(uid) {
  const key = String(uid || '').trim();
  if (!key) return;
  delete detailCache()[key];
  await Promise.all(pruned().filter(([, s]) => s.uid === key).map(([mount, s]) => qvRender(mount, key, s.opts)));
}

/** 批量失效：给 uids 清谁，不给则清空全部（历史修正可能波及任意题）。 */
export async function qvInvalidateMany(uids) {
  if (Array.isArray(uids)) {
    await Promise.all([...new Set(uids.map(uid => String(uid || '').trim()).filter(Boolean))].map(qvInvalidate));
    return;
  }
  const cache = detailCache();
  Object.keys(cache).forEach(key => { delete cache[key]; });
  await Promise.all(pruned().map(([mount, s]) => qvRender(mount, s.uid, s.opts)));
}

/** 纯重绘（不动缓存）：换行模式等显示设置变化后把已挂载的视图按新设置画一遍。 */
export function qvRerenderAll() {
  pruned().forEach(([mount, s]) => {
    const detail = s.detail || cachedDetail(s.uid);
    if (detail) render(mount, raw(qvHtml(detail, questionItem(s.question_id || s.uid) || {}, s.opts)));
  });
}

/** 「在题目库打开」：关弹窗、切到题库并按 UID 搜索（停用题同时放开停用筛选）；经过渡桥的 questionsLoadPreset 交给题库页。 */
function openInLibrary(uid) {
  closeModal();
  globalThis.__omrs?.router.go('questions');
  globalThis.__omrs?.emit('questions:preset', { 'q-search': uid, 'q-filter-suspended': itemOf(uid).suspended ? 'all' : '' });
}

const ACTIONS = {
  edit: uid => editQuestion(uid),
  board: (uid, button, event) => boardQuickAdd(uid, { anchor: button, direct: event.shiftKey }),
  labels: (uid, button) => openLabelPicker(uid, button),
  suspend: uid => suspendQuestion(uid),
  resume: uid => resumeQuestion(uid),
  delete: uid => deleteQuestion(uid),
  open: uid => openInLibrary(uid),
};

function onClick(event) {
  const button = event.target.closest?.('[data-qv-act]');
  if (!button) return;
  const uid = button.closest('.qv')?.dataset.qvUid || '';
  const state = mounts.get(button.closest('[data-qv-mount]'));
  const action = button.dataset.qvAct;
  if (action === 'reveal') { state?.opts?.onReveal?.(state.uid || uid); return; }
  if (action === 'retry') { qvInvalidate(state?.uid || uid); return; }
  if (uid && ACTIONS[action]) ACTIONS[action](action === 'open' ? uid : { uid, question_id: state?.question_id || state?.detail?.question_id || '' }, button, event);
}

/** 题图加载失败时就地换成文件名提示（旧 questions.js 的 document 级 error 捕获，改成类名而不是行内样式）。 */
function onImageError(event) {
  const img = event.target;
  if (!img?.matches?.('img[data-omrs-image]')) return;
  const note = img.ownerDocument.createElement('span');
  note.className = 'md-img-missing';
  note.textContent = `[图片缺失: ${img.dataset.omrsImage}]`;
  img.replaceWith(note);
}

let bound = false;
/** 由过渡桥在启动时调用一次：绑工具按钮委托、题图降级、弹窗翻页快捷键。 */
export function bindQuestionDom(doc = document) {
  if (bound) return;
  bound = true;
  doc.addEventListener('click', onClick);
  doc.addEventListener('error', onImageError, true);
  bindModalKeys();
}
