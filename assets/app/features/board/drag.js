/**
 * 展示板拖拽排序（P7 第 4 步从 assets/board.js 搬来，行为不变）：
 * - 舞台列表行拖拽 → 题目换位（boardMoveItems）；
 * - 左栏树：板拖到文件夹行 = 移过去，板拖到板行 = 落在那个位置，文件夹行之间拖 = 文件夹排序；
 * - 键盘：Ctrl/⌘+↑↓ 移动选中题，↑↓ 换选中行（纯函数，快捷键处理仍在 board.js）。
 * 拖拽中按 Esc 由浏览器取消：只触发 dragend 不触发 drop，这里在 dragend 清掉拖拽状态，所以不会误移。
 * 放置位置的计算是纯函数；DOM 绑定幂等（data-bound 标记），实际写入经调用方注入的回调。
 */
const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };

/** 行拖拽落点：from、to 都有效且不同才移动，否则返回 null。 */
export function boardRowDropPlan(from, to, length) {
  const a = num(from, -1), b = num(to, -1);
  if (a < 0 || b < 0 || a === b || a >= length || b >= length) return null;
  return { from: a, to: b };
}

/**
 * 左栏树的落点：drag = {kind:'board'|'folder', id}；target 是落点元素的 dataset
 * （boardFolderDrag / boardDrag / boardFolderDrop）。返回
 * {type:'folder-order', id, order} | {type:'move', boardId, folderId, index?} | null。
 */
export function boardTreeDropPlan(drag, target, boards, folders) {
  if (!drag || !target) return null;
  if (drag.kind === 'folder') {
    const to = (folders || []).find(item => item.id === target.boardFolderDrag);
    return to && to.id !== drag.id ? { type: 'folder-order', id: drag.id, order: num(to.order, 0) } : null;
  }
  if (target.boardDrag) {
    const onto = (boards || []).find(board => board.id === target.boardDrag);
    return onto && onto.id !== drag.id ? { type: 'move', boardId: drag.id, folderId: onto.folder_id, index: num(onto.order, 0) } : null;
  }
  const folderId = target.boardFolderDrop ?? '';
  const source = (boards || []).find(board => board.id === drag.id);
  return source && source.folder_id !== folderId ? { type: 'move', boardId: drag.id, folderId } : null;
}

/** Ctrl/⌘+↑↓：选中题要去的位置；越界或没选中返回 -1。 */
export function boardKeyReorderTarget(index, key, length) {
  const to = index + (key === 'arrowup' ? -1 : 1);
  return index >= 0 && to >= 0 && to < length ? to : -1;
}

/** ↑↓ 换选中行：没选中时落到第一行，到头停住。 */
export function boardKeySelectTarget(index, key, length) {
  if (!length) return -1;
  return index < 0 ? 0 : Math.max(0, Math.min(length - 1, index + (key === 'arrowup' ? -1 : 1)));
}

/** 舞台列表的行拖拽。hooks.move(from, to) 负责写入；hooks.ready() 为 false 时（没有当前板）落下不处理。 */
export function bindBoardRowDrag(content, hooks) {
  if (!content || content.dataset.bound === '1') return false;
  content.dataset.bound = '1';
  let from = -1;
  const clear = () => content.querySelectorAll('.dragging,.drag-over').forEach(node => node.classList.remove('dragging', 'drag-over'));
  content.addEventListener('dragstart', event => {
    const row = event.target.closest('[data-board-row]');
    if (!row) return;
    from = num(row.dataset.boardIndex, -1);
    row.classList.add('dragging');
    try { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', row.dataset.boardIndex); } catch (error) { /* 部分浏览器不给写 */ }
  });
  content.addEventListener('dragend', () => { from = -1; clear(); });
  content.addEventListener('dragover', event => {
    const row = event.target.closest('[data-board-row]');
    if (!row || from < 0) return;
    event.preventDefault();
    content.querySelectorAll('.drag-over').forEach(node => node.classList.remove('drag-over'));
    row.classList.add('drag-over');
  });
  content.addEventListener('drop', async event => {
    const row = event.target.closest('[data-board-row]');
    if (!row || !hooks.ready() || from < 0) return;
    event.preventDefault();
    const plan = boardRowDropPlan(from, row.dataset.boardIndex, hooks.length());
    from = -1;
    if (plan) await hooks.move(plan.from, plan.to);
  });
  return true;
}

/** 左栏树的拖拽。hooks.plan(drag, targetDataset) 算落点（通常是 boardTreeDropPlan），hooks.apply(plan) 负责写入。 */
export function bindBoardTreeDrag(list, hooks) {
  if (!list || list.dataset.treeBound === '1') return false;
  list.dataset.treeBound = '1';
  let drag = null;
  const clear = () => list.querySelectorAll('.drag-over,.dragging').forEach(node => node.classList.remove('drag-over', 'dragging'));
  const targetOf = event => event.target.closest?.(drag.kind === 'folder' ? '[data-board-folder-drag]' : '[data-board-folder-drop],[data-board-drag]');
  list.addEventListener('dragstart', event => {
    const board = event.target.closest?.('[data-board-drag]');
    const folder = event.target.closest?.('[data-board-folder-drag]');
    if (board) drag = { kind: 'board', id: board.dataset.boardDrag };
    else if (folder) drag = { kind: 'folder', id: folder.dataset.boardFolderDrag };
    else return;
    (board || folder).classList.add('dragging');
    try { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', drag.id); } catch (error) { /* 同上 */ }
  });
  list.addEventListener('dragend', () => { drag = null; clear(); });
  list.addEventListener('dragover', event => {
    if (!drag) return;
    const target = targetOf(event);
    if (!target || target.classList.contains('dragging')) return;
    event.preventDefault();
    list.querySelectorAll('.drag-over').forEach(node => node.classList.remove('drag-over'));
    target.classList.add('drag-over');
  });
  list.addEventListener('drop', async event => {
    if (!drag) return;
    const target = targetOf(event);
    const moving = drag;
    drag = null;
    clear();
    if (!target) return;
    event.preventDefault();
    const plan = hooks.plan(moving, target.dataset);
    if (plan) await hooks.apply(plan);
  });
  return true;
}
