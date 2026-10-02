import { questionRefs } from '../question/ref.js';
/**
 * 选板浮层（P7 第 4 轮起原生，原 assets/board_picker.js）：所有「加入展示板」入口的唯一实现——题目库、题目弹窗、数据复盘、
 * 反馈录入、收件箱、展示板页都经 domain/board/index.js 的 boardQuickAdd / boardChooseAndAdd 或过渡桥挂回的同名全局打开它。
 * 设计要点：动作发生前先看见目标板，并且当场能改；单击行即完成，没有「确定」按钮。
 *
 * - 渲染：根节点建一次，内容 morph(picker-view.js)；行模型与点击决策是 model.js 的纯函数。
 * - 挂载：ui/overlay 的客人（hostGuest）——叠在模态对话框（题目弹窗）上时放进对话框，否则进 body；再进浏览器顶层（popover）。
 *   叠在对话框上时 Esc 由 ui/overlay 代关（escape:true），对话框关闭时浮层随之关闭，焦点回到对话框里的触发按钮。
 * - 键盘：core/keys 的浮层键盘层（pushKeyLayer）：↑↓ 移动、Enter 加入、Ctrl / ⌘ + Enter 连加（浮层不关）、Esc 关闭、
 *   ←/→ 折叠 / 展开高亮行所在的文件夹；焦点不在搜索框时打字直接进搜索框。层是独占的，浮层开着时背后页面的快捷键不触发。
 * - 点外面关闭：document 上的 click 捕获监听，打开后下一轮才挂（同一次点击不会立刻把它关掉）；叠在浮层上面的弹层不算外面。
 * - 数据与加题经 source.js（板列表读 boards.js，加题 / 重读 / 打开经 detail-port.js 到 features/board/detail.js）；接口经 core/api。测试用 configureBoardPicker 换替身。
 */
import { html } from '../../core/html.js';
import { toElement, morph } from '../../core/dom.js';
import { get, post } from '../../core/api.js';
import { pushKeyLayer } from '../../core/keys.js';
import { hostGuest, releaseGuest } from '../../ui/overlay.js';
import { toast } from '../../ui/toast.js';
import { dialog, prompt } from '../../ui/dialog.js';
import { boardUniqueUids, boardPickerItems, boardPickerDefaultActive, boardPickerStep, boardPickerFoldTarget, boardPickerRowAfterGroup, boardPickerPlan, boardPickerPosition } from './model.js';
import { boardPickerView, boardPickerNewBody } from './picker-view.js';
import { boardWritePayload, adoptBoardVersions } from './boards.js';
import { boardSource } from './source.js';

const DEFAULTS = Object.freeze({ source: boardSource, get, post, toast, dialog, prompt });
let deps = { ...DEFAULTS };
let current = null;
let seq = 0;

/** 测试用：换掉数据来源、接口与对话框（传 null 恢复默认）。 */
export function configureBoardPicker(next) { deps = next ? { ...deps, ...next } : { ...DEFAULTS }; }
/** 浮层是否开着（旧 board.js 的页面快捷键据此让位）。 */
export const boardPickerIsOpen = () => !!current;
/** 当前浮层的根节点（没有则 null）。 */
export const boardPickerNode = () => current?.node || null;

async function postBoard(path, body) {
  const result = await deps.post(path, boardWritePayload(path, body));
  if (result?.ok) adoptBoardVersions(result.data);
  return result;
}
async function need(pending) {
  const result = await pending;
  if (!result?.ok) throw new Error(result?.error?.message || '请求失败');
  return result.data || {};
}
const say = (text, options = {}) => deps.toast(text, { kind: 'ok', ...options });
const fail = (text, error) => deps.toast(`${text}：${error?.message || error}`, { kind: 'error' });

async function fetchBoards() {
  const data = await need(deps.get('/api/boards'));
  deps.source.adopt(data);
}

function render(reset = false) {
  const p = current;
  if (!p) return;
  const src = deps.source;
  const model = boardPickerItems({ boards: p.boards, folders: p.folders, uids: p.uids, query: p.query, lastId: src.lastId(), collapsed: src.collapsed(), added: p.added });
  p.items = model.items;
  p.rows = model.rows;
  if (reset || p.active >= p.rows.length) p.active = boardPickerDefaultActive(p.rows);
  morph(p.node, boardPickerView({ title: p.title, count: p.uids.length, query: p.query, items: p.items, rows: p.rows, active: p.active, empty: model.empty, addedCount: p.added.size, idBase: p.idBase }));
  p.node.querySelector('.bpicker-opt.is-active')?.scrollIntoView?.({ block: 'nearest' });
}

function place() {
  const p = current;
  if (!p) return;
  const box = p.node;
  const win = box.ownerDocument.defaultView;
  const anchor = p.anchor;
  if (!anchor?.isConnected || typeof anchor.getBoundingClientRect !== 'function') { box.classList.add('is-centered'); return; }
  box.classList.remove('is-centered');
  const rect = box.getBoundingClientRect();
  const at = boardPickerPosition(anchor.getBoundingClientRect(), rect, { width: win.innerWidth, height: win.innerHeight });
  box.style.setProperty('--bpicker-x', `${at.left}px`);
  box.style.setProperty('--bpicker-y', `${at.top}px`);
}

function move(step) {
  const p = current;
  if (!p || !p.rows.length) return;
  p.foldAnchor = '';
  p.active = boardPickerStep(p.active, step, p.rows.length);
  render();
}

// ← 折叠高亮行所在的文件夹，高亮移到组后面的第一行并记住这个组；紧接着按 → 展开的就是它，高亮回到组里第一行
function fold(collapse) {
  const p = current;
  if (!p) return false;
  const id = (!collapse && p.foldAnchor) || boardPickerFoldTarget(p.items, p.rows[p.active]?.key);
  if (!id) return false;   // 没有可折叠的组：←/→ 照常在搜索框里移动光标
  deps.source.toggleFolder(id, collapse);
  p.foldAnchor = collapse ? id : '';
  render();
  const key = boardPickerRowAfterGroup(p.items, id);
  const at = p.rows.findIndex(row => row.key === key);
  if (at >= 0 && at !== p.active) { p.active = at; render(); }
  return true;
}

function commitActive(additive) {
  const p = current;
  const row = p?.rows[p.active];
  if (row) void commit(row.board, additive);
}

async function refresh() {
  const p = current;
  if (!p) return;
  try { await fetchBoards(); } catch (error) { return; }
  if (current !== p) return;
  p.boards = deps.source.boards().filter(board => board.id !== p.exclude);
  p.folders = deps.source.folders();
  render(true);
}

async function commit(board, additive) {
  const p = current;
  if (!p) return;
  const src = deps.source;
  const plan = boardPickerPlan(board, p, additive);
  if (plan.kind === 'open') {
    boardPickerClose();
    await src.open(board.id);
    return;
  }
  if (plan.kind === 'undo') {
    p.added.delete(board.id);
    try {
      await need(postBoard('/api/board/items/remove', { id: board.id, question_refs: plan.uids.map(question_id => ({ question_id })) }));
      await refresh();
    } catch (error) {
      p.added.set(board.id, plan.uids);
      render();
      fail('撤回失败', error);
    }
    return;
  }
  p.touched = true;
  if (plan.additive) {
    const result = await src.add(board.id, plan.uids.map(id => p.references.get(id)), { silent: true });
    if (result?.added_question_ids?.length) p.added.set(board.id, result.added_question_ids);
    await refresh();
    return;
  }
  const from = p.moveFrom ? (src.boards().find(item => item.id === p.moveFrom)?.name || '') : '';
  boardPickerClose();
  const result = await src.add(board.id, plan.uids.map(id => p.references.get(id)), { moveFromName: from });
  if (result && p.moveFrom && p.moveFrom !== board.id) {
    try {
      await need(postBoard('/api/board/items/remove', { id: p.moveFrom, question_refs: [...p.references.values()] }));
      await src.reload();
    } catch (error) { fail('已加入目标板，原板移除失败', error); }
  }
}

async function createBoard(name, uids, folderId) {
  const src = deps.source;
  try {
    const body = { name, question_refs: uids };
    if (folderId !== undefined) body.folder_id = folderId;
    const created = await need(postBoard('/api/board/create', body));
    src.remember(created.board.id);
    src.adoptDetail(created.board);
    await src.reload();
    say(`已新建《${name}》${uids.length ? `，加入 ${created.board.items.length} 题` : ''}`);
    return created.board;
  } catch (error) { fail('新建展示板失败', error); return null; }
}

async function newBoard() {
  const p = current;
  if (!p) return;
  const uids = [...p.references.values()];
  const folders = p.folders;
  const hint = p.folderHint;
  const seed = p.query.trim();
  boardPickerClose();
  const res = await deps.dialog({
    title: `新建展示板${uids.length ? ` · ${uids.length} 道题` : ''}`,
    okText: '新建并加入',
    body: boardPickerNewBody({ seed, folders, current: hint }),
    hint: '板名只在系统内使用，纸面标题固定为「错题集」。',
    focus: '#bpk-new-name',
  });
  if (!res?.ok) return;
  const name = String(res.values?.['bpk-new-name'] || '').trim();
  if (name) await createBoard(name, uids, res.values['bpk-new-folder'] ?? hint);
}

// 一个板都没有：不必先弹一个空浮层再让用户点「新建」
async function newFromEmpty(uids) {
  const name = await deps.prompt('新建展示板', '', { placeholder: '如：考前速览·三角函数', hint: '还没有板，先建一个；板名只在系统内使用。' });
  if (name) await createBoard(String(name).trim(), uids);
}

// Shift + 点击：跳过浮层直接进上次的板（一个板都没有时返回 false，照常走浮层 / 新建）
async function addDirect(uids) {
  const src = deps.source;
  const all = src.boards();
  const target = all.find(board => board.id === src.lastId()) || all[0];
  if (!target) return false;
  const board = await src.add(target.id, uids, { silent: true });
  if (!board) return true;
  const added = (board.added_question_ids || []).map(question_id => ({ question_id }));
  const undo = async () => {
    try {
      await need(postBoard('/api/board/items/remove', { id: board.id, question_refs: added }));
      await src.reload();
      say('已撤销加入');
    } catch (error) { fail('撤销失败', error); }
  };
  say(added.length ? `已直接加入《${board.name}》（现共 ${board.items.length} 题）` : `这些题已经在《${board.name}》里了`, {
    actions: added.length ? [
      { label: '撤销', onClick: undo },
      { label: '换个板…', onClick: () => boardPickerOpen(added, { exclude: board.id, moveFrom: board.id }) },
    ] : [],
  });
  return true;
}

function mount(refs, boards, options) {
  const uids = refs.map(ref => ref.question_id);
  const doc = options.document || document;
  const win = doc.defaultView;
  const src = deps.source;
  const label = options.moveFrom ? '移动到' : '加入展示板';
  const node = toElement(html`<div class="bpicker" role="dialog" aria-label="${label}"></div>`, doc);
  const p = {
    node, uids, references: new Map(refs.map(ref => [ref.question_id, ref])), boards, folders: src.folders(), title: options.moveFrom ? '移动到…' : '加入展示板',
    exclude: options.exclude || '', moveFrom: options.moveFrom || '',
    folderHint: src.boards().find(board => board.id === src.lastId())?.folder_id || '',
    added: new Map(), query: '', items: [], rows: [], active: -1, touched: false, foldAnchor: '',
    onDone: options.onDone, anchor: options.anchor || null, opener: doc.activeElement, idBase: `bpicker-${++seq}`,
  };
  current = p;
  p.host = hostGuest(node, { close: () => boardPickerClose(), escape: true });
  if ('popover' in node) {
    node.setAttribute('popover', 'manual');
    try { node.showPopover(); } catch (_) { /* 顶层不可用时退回 z-index */ }
  }
  render(true);
  place();
  const search = node.querySelector('[data-bpk="search"]');
  p.popKeys = pushKeyLayer({
    arrowdown: () => move(1),
    arrowup: () => move(-1),
    enter: () => commitActive(false),
    'mod+enter': () => commitActive(true),
    escape: () => boardPickerClose(),
    arrowleft: () => fold(true),
    arrowright: () => fold(false),
    // 焦点没在搜索框时（触屏不自动聚焦、或用 Tab 走到了行上）也能直接打字过滤；不拦下这个键，字照常进搜索框
    any: event => {
      if (event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey && doc.activeElement !== search) search.focus({ preventScroll: true });
      return false;
    },
  });
  p.onReflow = event => { if (!(event?.type === 'scroll' && node.contains(event.target))) place(); };
  // 挡住「点外面关闭」的只有叠在浮层上面的弹层（如新建对话框）；包含浮层的宿主对话框（题目弹窗）不算
  p.onOutside = event => {
    if (current !== p || event.composedPath().includes(node)) return;
    const above = [...doc.querySelectorAll('.modal-overlay.open, dialog[open]')].some(layer => !layer.contains(node));
    if (!above) boardPickerClose();
  };
  win.addEventListener('resize', p.onReflow);
  win.addEventListener('scroll', p.onReflow, true);
  p.outsideTimer = setTimeout(() => { if (current === p) doc.addEventListener('click', p.onOutside, true); }, 0);
  node.addEventListener('input', event => {
    if (!event.target.matches?.('[data-bpk="search"]')) return;
    p.query = event.target.value;
    p.foldAnchor = '';
    render(true);
  });
  node.addEventListener('click', event => {
    const target = event.target.closest?.('[data-bpk], [data-bpk-fold], [data-bpk-board]');
    if (!target || current !== p) return;
    if (target.dataset.bpk === 'close') { boardPickerClose(); return; }
    if (target.dataset.bpk === 'new') { void newBoard(); return; }
    if (target.dataset.bpk === 'search') return;
    if (target.dataset.bpkFold !== undefined) { p.foldAnchor = ''; src.toggleFolder(target.dataset.bpkFold); render(true); return; }
    const board = p.boards.find(item => item.id === target.dataset.bpkBoard);
    if (board) void commit(board, event.metaKey || event.ctrlKey);
  });
  // 触屏不自动聚焦，免得弹起软键盘挡住列表
  if (!win.matchMedia?.('(pointer: coarse)')?.matches) win.requestAnimationFrame(() => { if (current === p) search.focus({ preventScroll: true }); });
}

/** 关闭浮层：解绑、移除，焦点随浮层丢失时还给打开它的元素；onDone(touched) 在最后调用。 */
export function boardPickerClose() {
  const p = current;
  if (!p) return;
  current = null;
  const doc = p.node.ownerDocument;
  const win = doc.defaultView;
  p.popKeys?.();
  clearTimeout(p.outsideTimer);
  doc.removeEventListener('click', p.onOutside, true);
  win.removeEventListener('resize', p.onReflow);
  win.removeEventListener('scroll', p.onReflow, true);
  const active = doc.activeElement;
  const lost = !active || active === doc.body || p.node.contains(active);
  p.node.remove();
  releaseGuest(p.node);   // 在对话框里时由 ui/overlay 把焦点还给触发按钮
  if (p.host === doc.body && lost && p.opener?.isConnected && p.opener !== doc.body) p.opener.focus?.({ preventScroll: true });
  if (typeof p.onDone === 'function') p.onDone(p.touched);
}

/**
 * 打开浮层。uids 可以是单个 uid 或数组。options：anchor（有则锚定弹出，无则居中弱模态：toast 按钮、快捷键都走这条）、
 * direct（Shift + 点击：直接进上次的板）、exclude / moveFrom（「换个板…」：不列出原板，加入后从原板移除）、onDone(touched)。
 * 已经开着时再调用 = 关闭（切换）。
 */
export async function boardPickerOpen(uids, options = {}) {
  let clean;
  try { clean = questionRefs(Array.isArray(uids) ? uids : [uids]); }
  catch (error) { fail('无法加入展示板', error); return; }
  if (!clean.length) return;
  if (current) { boardPickerClose(); return; }
  const src = deps.source;
  if (!src.boards().length || !src.folders().length) {
    try { await fetchBoards(); } catch (error) { /* 用已有缓存 */ }
    if (current) return;   // 等接口期间已经有另一个浮层打开（双击）
  }
  if (options.direct && await addDirect(clean)) return;
  const candidates = src.boards().filter(board => board.id !== options.exclude);
  if (!candidates.length) { await newFromEmpty(clean); return; }
  mount(clean, candidates, options);
}
