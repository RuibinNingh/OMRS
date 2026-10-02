import { questionRefs } from '../question/ref.js';
/**
 * 展示板列表的数据所有者（P7 第 5 轮起）：板列表、文件夹、当前板、上次用的板、文件夹折叠状态，以及板 / 文件夹的写操作。
 * 取代旧 assets/board.js 的 BOARD_DATA / BOARD_FOLDERS / BOARD_CURRENT、boardLastId / boardRemember / boardFolderCollapsed /
 * boardFolderToggle / boardHintText，与 boardCreate / boardRename / boardEditNote / boardDuplicate / boardDelete /
 * boardFolderCreate / Rename / Reorder / Delete / boardMoveToFolder（旧名里仍有调用方的经过渡桥挂回，见 legacy-bridge.js）。
 *
 * - 读：boardList() / boardFolders() / boardCurrentId() / boardFind(id)；订阅 onBoards(fn) → off（列表、当前板、折叠变化后通知）。
 * - 列表由 features/board/detail.js 的 reloadData() 拉取后 adoptBoards() 采纳（它同时管当前板详情的并发序号）。
 * - 写操作之前经钩子冲刷保存队列（失败就放弃），之后经钩子整页重读；钩子缺省走 detail-port.js（由 detail.js 接上），测试经 configureBoards 换。
 * - 折叠状态与上次用的板属于本机 UI 状态，只存 localStorage，不进 boards.json。
 */
import { html } from '../../core/html.js';
import { post as apiPost } from '../../core/api.js';
import { prompt, confirm, dialog } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { boardDetailPort } from './detail-port.js';

export const BOARD_LAST_KEY = 'omrs-board-last';
export const BOARD_FOLD_KEY = 'omrs-board-folders-collapsed';

const state = { boards: [], folders: [], current: '', catalogRevision: null };
const listeners = new Set();
const defaults = () => ({ post: apiPost, prompt, confirm, dialog, toast, storage: () => globalThis.localStorage, hooks: boardDetailPort });
let deps = defaults();

/** 测试替身：{ post, prompt, confirm, dialog, toast, storage, hooks }；{ reset: true } 恢复缺省并清空列表。 */
export function configureBoards(patch = {}) {
  if (patch.reset) { deps = defaults(); state.boards = []; state.folders = []; state.current = ''; state.catalogRevision = null; listeners.clear(); return; }
  deps = { ...deps, ...patch };
}

function notify() {
  listeners.forEach(fn => { try { fn(); } catch (error) { console.error('[board] 列表订阅出错', error); } });
}
export function onBoards(fn) { listeners.add(fn); return () => listeners.delete(fn); }

export const boardList = () => state.boards;
export const boardFolders = () => state.folders;
export const boardCurrentId = () => state.current;
export const boardFind = id => state.boards.find(board => board.id === id) || null;
const folderOf = id => state.folders.find(folder => folder.id === id) || null;

/** 采纳 /api/boards 的结果（展示板页与选板浮层共用这一份）。 */
export function adoptBoards({ boards, folders, catalog_revision } = {}) {
  if (Number.isInteger(catalog_revision)) state.catalogRevision = catalog_revision;
  state.boards = Array.isArray(boards) ? boards : [];
  state.folders = Array.isArray(folders) ? folders : [];
  notify();
}

/** 写入使用已读取版本，不在提交前获取新版本掩盖并发冲突。 */
export function boardWritePayload(path, body, current = null) {
  const result = { ...body };
  if (!path.startsWith('/api/board/')) return result;
  const catalog = path.includes('/folder/') || ['/api/board/create', '/api/board/move', '/api/board/duplicate', '/api/board/delete'].includes(path) || 'folder_id' in body || 'name' in body;
  const board = body.id && !path.includes('/folder/');
  const target = current?.id === body.id ? current : boardFind(body.id);
  if (board && Number.isInteger(target?.revision) && result.expected_revision === undefined) result.expected_revision = target.revision;
  if (catalog && Number.isInteger(state.catalogRevision) && result.expected_catalog_revision === undefined) result.expected_catalog_revision = state.catalogRevision;
  return result;
}
export function adoptBoardVersions(data) {
  if (Number.isInteger(data?.catalog_revision)) state.catalogRevision = data.catalog_revision;
  if (data?.board?.id) {
    const target = boardFind(data.board.id);
    if (target) Object.assign(target, { revision: data.board.revision });
  }
}

function store() { try { return deps.storage() || null; } catch (error) { return null; } }
export function boardLastId() { try { return store()?.getItem(BOARD_LAST_KEY) || ''; } catch (error) { return ''; } }
/** 设为当前板；有 id 时同时记成「上次用的板」（空 id 只清当前板，不动记忆）。 */
export function boardRemember(id) {
  state.current = id || '';
  try { if (id) store()?.setItem(BOARD_LAST_KEY, id); } catch (error) { /* 隐私模式 */ }
  notify();
}
/** 重读时该落在哪块板：当前板 → 上次用的板 → 第一块；都没有时为空。 */
export function boardPreferredId() {
  const preferred = state.current || boardLastId();
  return (boardFind(preferred) || state.boards[0])?.id || '';
}

export function boardFolderCollapsed() {
  try { return new Set(JSON.parse(store()?.getItem(BOARD_FOLD_KEY) || '[]')); } catch (error) { return new Set(); }
}
export function boardFolderToggle(id, force) {
  if (!id) return undefined;
  const set = boardFolderCollapsed();
  const next = force === undefined ? !set.has(id) : !!force;
  if (next) set.add(id); else set.delete(id);
  try { store()?.setItem(BOARD_FOLD_KEY, JSON.stringify([...set])); } catch (error) { /* 隐私模式 */ }
  notify();
  return set;
}

/** 「加入展示板」按钮的悬停说明：上次用的板随时会变，悬停 / 聚焦时现算。 */
export function boardHintText() {
  const last = boardFind(boardLastId()) || state.boards[0];
  return last ? `加入展示板（上次：${last.name}）· Shift 点击直接加入` : '加入展示板（还没有板，会先新建）';
}

// ---------- 写操作 ----------
async function send(path, body) {
  const res = await deps.post(path, boardWritePayload(path, body, deps.hooks.detail()));
  if (!res?.ok) throw Object.assign(new Error(res?.error?.message || '请求失败'), res?.error);
  adoptBoardVersions(res.data);
  return res.data || {};
}
const fail = (what, error) => deps.toast(`${what}：${error.message}`, { kind: 'error' });
const byId = id => boardFind(id) || (deps.hooks.detail()?.id === id ? deps.hooks.detail() : null);

export async function createBoard(initialUids = null, folderId = '') {
  const question_refs = questionRefs(initialUids || []);
  if (!(await deps.hooks.flush())) return null;
  const folder = folderOf(folderId);
  const name = await deps.prompt('新建展示板', '', {
    placeholder: '如：考前速览·三角函数',
    hint: folder ? `放进「${folder.name}」；板名只在系统内使用，纸面标题固定为「错题集」。` : '板名只在系统内使用，纸面标题固定为「错题集」。',
  });
  if (!name) return null;
  try {
    const result = await send('/api/board/create', { name, question_refs, folder_id: folderId || '' });
    boardRemember(result.board.id);
    await deps.hooks.reload();
    deps.toast(`已新建《${name}》${initialUids?.length ? `，加入 ${result.board.items.length} 题` : ''}`);
    return result.board;
  } catch (error) { fail('新建展示板失败', error); return null; }
}

/** 改板名（对话框与状态条上的就地改名共用）；返回是否已保存。 */
export async function saveBoardName(id, name) {
  const board = byId(id);
  const next = String(name || '').trim();
  if (!board || !next || next === board.name) return false;
  try { await send('/api/board/update', { id, name: next }); await deps.hooks.reload(); return true; } catch (error) { fail('重命名失败', error); return false; }
}
export async function renameBoard(id) {
  const board = byId(id);
  if (!board) return false;
  const name = await deps.prompt('重命名展示板', board.name);
  return name ? saveBoardName(id, name) : false;
}
export async function editBoardNote(id) {
  const board = byId(id);
  if (!board) return;
  const note = await deps.prompt('展示板备注', board.note || '', { placeholder: '如：9/10 月考前用', hint: '只在系统内显示，不上纸。' });
  if (note === null) return;
  try { await send('/api/board/update', { id, note }); await deps.hooks.reload(); } catch (error) { fail('保存备注失败', error); }
}
export async function duplicateBoard(id) {
  if (!(await deps.hooks.flush())) return;
  const board = byId(id);
  if (!board) return;
  const name = await deps.prompt('复制展示板为', `${board.name} 副本`, { hint: '复制题目引用与版面设置；纸面记录不复制（新板对应新纸）。' });
  if (!name) return;
  try {
    const result = await send('/api/board/duplicate', { id, name });
    boardRemember(result.board.id);
    await deps.hooks.reload();
    deps.toast(`已复制为《${name}》`);
  } catch (error) { fail('复制失败', error); }
}
export async function deleteBoard(id) {
  if (!(await deps.hooks.flush())) return;
  const board = byId(id);
  if (!board) return;
  const ok = await deps.confirm(`删除展示板「${board.name}」？`, { hint: '只删除这个板（含它的纸面记录），题目本身不受影响。', okText: '删除', danger: true });
  if (!ok) return;
  try {
    await send('/api/board/delete', { id });
    if (state.current === id) boardRemember('');
    await deps.hooks.reload();
    deps.toast(`已删除《${board.name}》`);
  } catch (error) { fail('删除展示板失败', error); }
}

export async function createFolder(seedBoardId = '') {
  const name = await deps.prompt('新建文件夹', '', { placeholder: '如：高三上·期中', hint: '只用来在左栏和选板浮层里分组，不影响纸面。' });
  if (!name) return null;
  try {
    const result = await send('/api/board/folder/create', { name });
    if (seedBoardId) await send('/api/board/move', { id: seedBoardId, folder_id: result.folder.id });
    await deps.hooks.reload();
    deps.toast(`已新建文件夹「${name}」`);
    return result.folder;
  } catch (error) { fail('新建文件夹失败', error); return null; }
}
export async function renameFolder(id) {
  const folder = folderOf(id);
  if (!folder) return;
  const name = await deps.prompt('重命名文件夹', folder.name);
  if (!name || name === folder.name) return;
  try { await send('/api/board/folder/update', { id, name }); await deps.hooks.reload(); } catch (error) { fail('重命名失败', error); }
}
/** 文件夹上移 / 下移一位；到头时什么都不做。 */
export async function reorderFolder(id, step) {
  const folder = folderOf(id);
  if (!folder) return;
  const to = (Number(folder.order) || 0) + step;
  if (to < 0 || to > state.folders.length - 1) return;
  await setFolderOrder(id, to);
}
async function setFolderOrder(id, order) {
  try { await send('/api/board/folder/update', { id, order }); await deps.hooks.reload(); } catch (error) { fail('调整顺序失败', error); }
}
export async function deleteFolder(id) {
  const folder = folderOf(id);
  if (!folder) return;
  const inside = state.boards.filter(board => board.folder_id === id);
  let keep = true;
  if (inside.length) {
    const res = await deps.dialog({
      title: `删除文件夹「${folder.name}」？`, hint: `里面有 ${inside.length} 个板。`, okText: '删除文件夹', danger: true,
      body: html`<div class="brd-fdel">
        <label><input type="radio" name="bd-fd" id="bd-fd-keep" checked><span>把这些板移到未归档<small>板和纸面记录都保留</small></span></label>
        <label><input type="radio" name="bd-fd" id="bd-fd-drop"><span>连同 ${inside.length} 个板一起删除<small>板的纸面记录一并消失，题目本身不受影响</small></span></label></div>`,
    });
    if (!res.ok) return;
    keep = res.values['bd-fd-drop'] !== true;
  } else if (!(await deps.confirm(`删除空文件夹「${folder.name}」？`, { okText: '删除', danger: true }))) return;
  try {
    await send('/api/board/folder/delete', { id, keep_boards: keep });
    await deps.hooks.reload();
    deps.toast(keep && inside.length ? `已删除文件夹，${inside.length} 个板移到未归档` : `已删除文件夹「${folder.name}」`);
  } catch (error) { fail('删除文件夹失败', error); }
}
/** 把板移进文件夹（空 folderId = 未归档）；index 给了就落在该位置。 */
export async function moveBoard(boardId, folderId, index) {
  try { await send('/api/board/move', { id: boardId, folder_id: folderId ?? '', index }); await deps.hooks.reload(); } catch (error) { fail('移动失败', error); }
}
/** 左栏树拖放的落点（features/board/drag.js 的 boardTreeDropPlan 算出）。 */
export async function applyTreeDrop(plan) {
  if (!plan) return;
  if (plan.type === 'folder-order') await setFolderOrder(plan.id, plan.order);
  else await moveBoard(plan.boardId, plan.folderId, plan.index ?? undefined);
}
