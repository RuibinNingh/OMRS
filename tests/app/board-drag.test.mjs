// 展示板拖拽排序（assets/app/features/board/drag.js，P7 第 4 步）：落点纯函数、键盘目标位置，
// 以及用最小 DOM 替身跑一遍行 / 左栏树的拖拽绑定（含拖拽中按 Esc：只有 dragend、没有 drop）。
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  boardRowDropPlan, boardTreeDropPlan, boardKeyReorderTarget, boardKeySelectTarget, bindBoardRowDrag, bindBoardTreeDrag,
} from '../../assets/app/features/board/drag.js';

const camel = attr => attr.replace(/^data-/, '').replace(/-([a-z])/g, (_, c) => c.toUpperCase());
function node(dataset = {}) {
  const classes = new Set();
  return { dataset, classList: { add: c => classes.add(c), remove: (...cs) => cs.forEach(c => classes.delete(c)), contains: c => classes.has(c) },
    closest(selector) { return selector.split(',').some(part => camel(part.trim().slice(1, -1)) in this.dataset) ? this : null; } };
}
function container() {
  const handlers = {};
  return { dataset: {}, handlers, addEventListener: (type, fn) => { handlers[type] = fn; }, querySelectorAll: () => [],
    fire: (type, target) => handlers[type]?.({ target, preventDefault() {}, dataTransfer: { setData() {} } }) };
}

test('行拖拽落点：有效且不同才移动', () => {
  assert.deepEqual(boardRowDropPlan(2, '0', 3), { from: 2, to: 0 });
  assert.equal(boardRowDropPlan(1, 1, 3), null);
  assert.equal(boardRowDropPlan(-1, 1, 3), null);
  assert.equal(boardRowDropPlan(0, 5, 3), null);
  assert.equal(boardRowDropPlan(0, 'x', 3), null);
});

test('左栏树落点：文件夹排序、板落在板上、板移到文件夹', () => {
  const folders = [{ id: 'F1', order: 0 }, { id: 'F2', order: 3 }];
  const boards = [{ id: 'B1', folder_id: 'F1', order: 0 }, { id: 'B2', folder_id: 'F2', order: 4 }, { id: 'B3', folder_id: '', order: 1 }];
  assert.deepEqual(boardTreeDropPlan({ kind: 'folder', id: 'F1' }, { boardFolderDrag: 'F2' }, boards, folders), { type: 'folder-order', id: 'F1', order: 3 });
  assert.equal(boardTreeDropPlan({ kind: 'folder', id: 'F1' }, { boardFolderDrag: 'F1' }, boards, folders), null);
  assert.deepEqual(boardTreeDropPlan({ kind: 'board', id: 'B1' }, { boardDrag: 'B2' }, boards, folders), { type: 'move', boardId: 'B1', folderId: 'F2', index: 4 });
  assert.equal(boardTreeDropPlan({ kind: 'board', id: 'B1' }, { boardDrag: 'B1' }, boards, folders), null);
  assert.deepEqual(boardTreeDropPlan({ kind: 'board', id: 'B1' }, { boardFolderDrop: '' }, boards, folders), { type: 'move', boardId: 'B1', folderId: '' });
  assert.equal(boardTreeDropPlan({ kind: 'board', id: 'B1' }, { boardFolderDrop: 'F1' }, boards, folders), null, '同一个文件夹不动');
  assert.equal(boardTreeDropPlan({ kind: 'board', id: 'gone' }, { boardFolderDrop: 'F2' }, boards, folders), null);
  assert.equal(boardTreeDropPlan(null, { boardFolderDrop: 'F2' }, boards, folders), null);
});

test('键盘：Ctrl/⌘+↑↓ 的目标位置，↑↓ 换选中行', () => {
  assert.equal(boardKeyReorderTarget(1, 'arrowup', 3), 0);
  assert.equal(boardKeyReorderTarget(0, 'arrowup', 3), -1);
  assert.equal(boardKeyReorderTarget(2, 'arrowdown', 3), -1);
  assert.equal(boardKeyReorderTarget(-1, 'arrowdown', 3), -1);
  assert.equal(boardKeySelectTarget(-1, 'arrowdown', 3), 0);
  assert.equal(boardKeySelectTarget(2, 'arrowdown', 3), 2);
  assert.equal(boardKeySelectTarget(0, 'arrowup', 3), 0);
  assert.equal(boardKeySelectTarget(0, 'arrowdown', 0), -1);
});

test('行拖拽绑定：幂等；拖放写入一次；拖拽中按 Esc（只有 dragend）不写；没有当前板不写', async () => {
  const content = container(), moves = [];
  let ready = true;
  const hooks = { ready: () => ready, length: () => 3, move: async (from, to) => moves.push([from, to]) };
  assert.equal(bindBoardRowDrag(content, hooks), true);
  assert.equal(bindBoardRowDrag(content, hooks), false);
  assert.equal(bindBoardRowDrag(null, hooks), false);
  const rows = [0, 1, 2].map(i => node({ boardRow: `U${i}`, boardIndex: String(i) }));
  content.fire('dragstart', rows[2]); await content.fire('drop', rows[0]);
  assert.deepEqual(moves, [[2, 0]]);
  content.fire('dragstart', rows[1]); content.fire('dragend'); await content.fire('drop', rows[0]);
  assert.deepEqual(moves, [[2, 0]], 'Esc 取消后落下不处理');
  ready = false;
  content.fire('dragstart', rows[1]); await content.fire('drop', rows[0]);
  assert.deepEqual(moves, [[2, 0]]);
});

test('左栏树拖拽绑定：落点交给 plan，结果交给 apply；dragend 后的 drop 不处理', async () => {
  const list = { ...container(), dataset: {} }, plans = [], applied = [];
  bindBoardTreeDrag(list, { plan: (drag, target) => { plans.push([drag, target]); return { type: 'move', boardId: drag.id, folderId: target.boardFolderDrop }; },
    apply: async plan => applied.push(plan) });
  const board = node({ boardDrag: 'B1' }), folder = node({ boardFolderDrop: 'F2' });
  list.fire('dragstart', board); await list.fire('drop', folder);
  assert.deepEqual(plans[0][0], { kind: 'board', id: 'B1' });
  assert.deepEqual(applied, [{ type: 'move', boardId: 'B1', folderId: 'F2' }]);
  list.fire('dragstart', board); list.fire('dragend'); await list.fire('drop', folder);
  assert.equal(applied.length, 1);
});
