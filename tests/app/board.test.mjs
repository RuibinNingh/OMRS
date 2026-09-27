// 展示板纯函数（P7 第 1 步由 tests/test_board_ui.js 迁来，用例原样保留，另加本步新增的纯函数）。
// 页面纯函数在 assets/app/features/board/model.js，选板纯函数在 assets/app/domain/board/model.js；
// 旧 board.js 经过渡桥 installBoardBridge 读同名全局；选板浮层（P7 第 4 轮原生）的测试在 board-picker.test.mjs。
import assert from 'node:assert/strict';
import test from 'node:test';
import * as model from '../../assets/app/features/board/model.js';
import * as domain from '../../assets/app/domain/board/model.js';
import * as domainIndex from '../../assets/app/domain/board/index.js';
import * as saveModule from '../../assets/app/features/board/save.js';
import * as printModule from '../../assets/app/features/board/print.js';
import * as previewModule from '../../assets/app/features/board/preview.js';
import * as settingsModule from '../../assets/app/features/board/settings.js';
import * as dragModule from '../../assets/app/features/board/drag.js';
import * as pickerModule from '../../assets/app/domain/board/picker.js';

const { boardMoveItems, boardEstimateText, boardColumnWidth } = model;
const { boardUniqueUids } = domain;

test('board item movement handles up/down and invalid positions', () => {
  const items = [{ uid: 'A' }, { uid: 'B' }, { uid: 'C' }];
  assert.deepEqual(boardMoveItems(items, 2, 0).map(item => item.uid), ['C', 'A', 'B']);
  assert.deepEqual(boardMoveItems(items, 0, 1).map(item => item.uid), ['B', 'A', 'C']);
  assert.deepEqual(boardMoveItems(items, -1, 1), items);
});

test('board quick-add UID normalization removes duplicates and blanks', () => {
  assert.deepEqual(boardUniqueUids([' A ', '', 'A', null, 'B']), ['A', 'B']);
});

test('estimate text: full print shows pages and margins, incremental shows partial page', () => {
  const all = boardEstimateText({ pages: 12, page_numbers: [1, 2, 3], rendered_pages: 3, warnings: [] }, 'all', {});
  assert.match(all, /预计 <b>12<\/b> 页/);
  assert.match(all, /左右 10 \/ 上下 12mm/);
  assert.doesNotMatch(all, /告警/);
  const incremental = boardEstimateText({ pages: 13, page_numbers: [12, 13], rendered_pages: 2, partial_page: 12, warnings: ['x'] }, 'new', {});
  assert.match(incremental, /本次补印 <b>2<\/b> 页（第 12–13 页），第 12 页印在原纸上/);
  assert.match(incremental, /整板共 <b>13<\/b> 页/);
  assert.match(incremental, /1 处切图告警/);
  assert.match(boardEstimateText({ pages: 1, page_numbers: [1], rendered_pages: 1 }, 'new', {}), /（第 1 页）/);
});

test('column width matches the browser template formula (A4, 10mm side margins, 24px gutter)', () => {
  // 793.7 - 20mm - 24 = 694.11px 可分配宽度；默认 50% 时左右等宽
  assert.equal(boardColumnWidth(50), 347);
  assert.equal(boardColumnWidth(42), 403);
  assert.equal(boardColumnWidth(30), 486);
  assert.equal(boardColumnWidth('bad'), boardColumnWidth(50));
});

// ---------- 文件夹与选板浮层（P1）----------
const { boardFolderTree, boardPickerRowState, boardPickerFilter, boardPickerRecent } = domain;

const FOLDERS = [{ id: 'F1', name: '高三上·期中', order: 0 }, { id: 'F2', name: '空组', order: 1 }];
const BOARDS = [
  { id: 'B1', name: '考前速览', folder_id: 'F1', order: 1, uids: ['Q1', 'Q2'], count: 2 },
  { id: 'B2', name: '数学·压轴', folder_id: 'F1', order: 0, uids: [], count: 0 },
  { id: 'B3', name: '临时', folder_id: '', order: 0, uids: ['Q1'], count: 1 },
  { id: 'B4', name: '悬空归属', folder_id: 'F-gone', order: 1, uids: [], count: 0 },
];

test('folder tree groups by folder, sorts by order, and keeps 未归档 last', () => {
  const tree = boardFolderTree(BOARDS, FOLDERS);
  assert.deepEqual(tree.map(group => group.name), ['高三上·期中', '空组', '未归档']);
  assert.deepEqual(tree[0].boards.map(board => board.name), ['数学·压轴', '考前速览']);
  assert.deepEqual(tree[1].boards, []);                                   // 空文件夹保留，左栏要显示占位
  assert.deepEqual(tree[2].boards.map(board => board.id), ['B3', 'B4']);  // 悬空 folder_id 归入未归档，不丢板
});

test('folder tree can drop empty folders, and falls back to a single 未归档 group', () => {
  assert.deepEqual(boardFolderTree(BOARDS, FOLDERS, { dropEmpty: true }).map(g => g.name), ['高三上·期中', '未归档']);
  assert.deepEqual(boardFolderTree(BOARDS, []).map(g => g.name), ['未归档']);
  assert.deepEqual(boardFolderTree([], []).map(g => g.name), ['未归档']);
});

test('picker row state distinguishes 全新 / 部分已有 / 全部已在板中', () => {
  assert.deepEqual(boardPickerRowState(BOARDS[1], ['Q1', 'Q2']), { kind: 'new', have: 0, total: 2, pending: ['Q1', 'Q2'] });
  assert.deepEqual(boardPickerRowState(BOARDS[2], ['Q1', 'Q2']), { kind: 'partial', have: 1, total: 2, pending: ['Q2'] });
  assert.deepEqual(boardPickerRowState(BOARDS[0], ['Q1', 'Q2']), { kind: 'full', have: 2, total: 2, pending: [] });
  // 重复与空白先归一，避免「已有 2/3」把同一道题算两次
  assert.equal(boardPickerRowState(BOARDS[0], [' Q1 ', 'Q1', '']).kind, 'full');
});

test('picker filter flattens groups and matches board name or folder name', () => {
  const groups = boardFolderTree(BOARDS, FOLDERS, { dropEmpty: true });
  assert.deepEqual(boardPickerFilter(groups, '压轴').map(row => [row.board.name, row.folderName]), [['数学·压轴', '高三上·期中']]);
  assert.deepEqual(boardPickerFilter(groups, '高三').map(row => row.board.name), ['数学·压轴', '考前速览']);
  assert.deepEqual(boardPickerFilter(groups, '临时').map(row => row.folderName), ['']);   // 未归档不当文件夹名显示
  assert.deepEqual(boardPickerFilter(groups, '查无此板'), []);
  assert.equal(boardPickerFilter(groups, '   '), null);                                   // 空查询 = 不过滤
});

test('recent list puts the last-used board first and dedupes it from the rest', () => {
  const list = [
    { id: 'B1', name: 'A', updated_at: '2026-09-01' },
    { id: 'B2', name: 'B', updated_at: '2026-09-05' },
    { id: 'B3', name: 'C', updated_at: '2026-09-03' },
  ];
  assert.deepEqual(boardPickerRecent(list, 'B3').map(board => board.name), ['C', 'B']);
  assert.deepEqual(boardPickerRecent(list, '不存在').map(board => board.name), ['B', 'C']);
  assert.deepEqual(boardPickerRecent([], 'B1'), []);
});

// ---------- 每题留白与脏字段保存队列（P2）----------
const { boardDirtyMerge, boardSavePayload, boardEffectiveGap, boardItemsPayload, boardGapCm } = model;

test('effective gap: null inherits the board setting, a number overrides it, both clamp to 0–48', () => {
  assert.equal(boardEffectiveGap({ gap_lines: null }, { gap_lines: 6 }), 6);
  assert.equal(boardEffectiveGap({}, { gap_lines: 6 }), 6);                 // 没有这个键 = 继承
  assert.equal(boardEffectiveGap({ gap_lines: 0 }, { gap_lines: 6 }), 0);   // 0 是「不留白」的真实选择，不是「没设」
  assert.equal(boardEffectiveGap({ gap_lines: 9 }, { gap_lines: 6 }), 9);
  assert.equal(boardEffectiveGap({ gap_lines: 999 }, {}), 48);              // 后端上限
  assert.equal(boardEffectiveGap({ gap_lines: -3 }, {}), 0);
  assert.equal(boardEffectiveGap({ gap_lines: null }, {}), 2);              // 板设置也缺失时回默认 2
  assert.equal(boardEffectiveGap(null, null), 2);
});

test('items payload keeps null gaps as null so an empty box still means 继承', () => {
  const payload = boardItemsPayload([
    { uid: 'A', question_id: 'OP-1', gap_lines: null },
    { uid: 'B', question_id: 'OP-2', gap_lines: 0 },
    { uid: 'C', question_id: 'OP-3', gap_lines: 99, pin: 1 },
  ]);
  assert.deepEqual(payload.map(item => item.gap_lines), [null, 0, 48]);
  assert.equal(payload[2].pin, true);
  assert.equal(payload[0].added_at, '');
});

test('dirty fields accumulate instead of replacing each other', () => {
  // 「先改行内留白再拖版面滑块」曾把前一次改动整个丢掉：两个字段各自持有同一个定时器
  let dirty = null;
  dirty = boardDirtyMerge(dirty, 'items');
  dirty = boardDirtyMerge(dirty, 'print');
  dirty = boardDirtyMerge(dirty, 'items');
  assert.deepEqual(dirty, { items: true, print: true });
  assert.deepEqual(boardDirtyMerge(null, 'print'), { print: true });
  assert.equal(boardDirtyMerge(null, ''), null);
});

test('one flush = one POST carrying every dirty field', () => {
  const detail = { id: 'B1', print: { gap_lines: 4 }, items: [{ uid: 'A', question_id: 'OP-1', gap_lines: 7 }] };
  const both = boardSavePayload(detail, { items: true, print: true });
  assert.deepEqual(Object.keys(both).sort(), ['id', 'items', 'print']);
  assert.equal(both.id, 'B1');
  assert.equal(both.items[0].gap_lines, 7);
  assert.deepEqual(both.print, { gap_lines: 4 });
  // 只脏一个字段就只发一个字段：避免把没动过的 items 整体覆盖回去
  assert.deepEqual(Object.keys(boardSavePayload(detail, { print: true })), ['id', 'print']);
  assert.deepEqual(Object.keys(boardSavePayload(detail, { items: true })), ['id', 'items']);
  // 没有脏字段 / 没有板 = 不发请求（beforeunload 也走这条判断）
  assert.equal(boardSavePayload(detail, null), null);
  assert.equal(boardSavePayload(detail, {}), null);
  assert.equal(boardSavePayload(null, { items: true }), null);
});

// ---------- 每题留白的厘米换算（P3）----------
test('gap lines convert to centimetres with the export template geometry', () => {
  // 模板：.question-gap{height:calc(var(--gap-lines) * 18px)}，MM = 3.779528 px/mm
  assert.equal(boardGapCm(0), 0);
  assert.equal(boardGapCm(1), 0.5);      // 18px = 4.76mm
  assert.equal(boardGapCm(4), 1.9);
  assert.equal(boardGapCm(7), 3.3);
  assert.equal(boardGapCm(48), 22.9);
  assert.equal(boardGapCm(999), boardGapCm(48));   // 夹到后端上限，不会算出一个纸上放不下的数
  assert.equal(boardGapCm(-5), 0);
  assert.equal(boardGapCm('bad'), 0);
});

// ---------- P7 第 1 步新增：搬迁时补齐的纯函数与过渡桥契约 ----------
test('content signature tracks membership, order and missing / suspended, but not geometry', () => {
  const items = [{ uid: 'A', gap_lines: 3 }, { uid: 'B', missing: true }, { question_id: 'OP-9', suspended: true }];
  assert.equal(model.boardItemsSignature(items), 'A,B!,OP-9-');
  assert.equal(model.boardItemsSignature([{ uid: 'A', gap_lines: 9 }, items[1], items[2]]), 'A,B!,OP-9-');
  assert.notEqual(model.boardItemsSignature([items[1], items[0], items[2]]), model.boardItemsSignature(items));
  assert.equal(model.boardItemsSignature(null), '');
});

test('gap map keeps null (inherit) and clamps numbers; items without uid are skipped', () => {
  assert.deepEqual(model.boardGapMap([{ uid: 'A', gap_lines: null }, { uid: 'B', gap_lines: 99 }, { uid: 'C', gap_lines: -1 }, { gap_lines: 3 }]),
    { A: null, B: 48, C: 0 });
  assert.deepEqual(model.boardGapMap(undefined), {});
});

test('paper layout boundary: without paper nothing counts; with paper only real layout changes do', () => {
  const printedItem = { question_id: 'OP-1', uid: 'A', printed: true, gap_lines: null };
  const freshItem = { question_id: 'OP-2', uid: 'B', printed: false, gap_lines: null };
  const board = { print: { note_ratio: 0.5, gap_lines: 2, show_labels: true, show_meta: true, cut_line: 'dash', cut_label: false },
    printed_summary: { pages: 1 }, printed: { items: [{ question_id: 'OP-1' }] }, items: [printedItem, freshItem] };
  assert.equal(model.boardPaperLayoutChanged({ ...board, printed_summary: { pages: 0 } }, { print: { note_ratio: 0.3 } }), false);
  assert.equal(model.boardPaperLayoutChanged(null, { print: { note_ratio: 0.3 } }), false);
  assert.equal(model.boardPaperLayoutChanged(board, { print: { note_ratio: 0.3 } }), true);
  assert.equal(model.boardPaperLayoutChanged(board, { print: { locked: true, answers: 'append' } }), false);
  assert.equal(model.boardPaperLayoutChanged(board, { print: { cut_label: true } }), true);
  assert.equal(model.boardPaperLayoutChanged({ ...board, print: { ...board.print, cut_line: 'none' } }, { print: { cut_label: true } }), false);
  // 排序、增删不改纸面；未印题的留白也不算
  assert.equal(model.boardPaperLayoutChanged(board, { items: [freshItem, printedItem] }), false);
  assert.equal(model.boardPaperLayoutChanged(board, { items: [printedItem, { ...freshItem, gap_lines: 9 }] }), false);
  // 已印题的有效留白变了才算；全局留白变化只在影响已印题时算
  assert.equal(model.boardPaperLayoutChanged(board, { items: [{ ...printedItem, gap_lines: 5 }, freshItem] }), true);
  assert.equal(model.boardPaperLayoutChanged(board, { print: { gap_lines: 4 } }), true);
  assert.equal(model.boardPaperLayoutChanged({ ...board, items: [{ ...printedItem, gap_lines: 2 }, freshItem] }, { print: { gap_lines: 4 } }), false);
});

test('short time format falls back to the raw prefix when unparsable', () => {
  assert.equal(model.boardFormatTime(''), '');
  assert.equal(model.boardFormatTime('not-a-date-but-long'), 'not-a-date-but-l');
  assert.match(model.boardFormatTime('2026-09-04T12:05:00'), /^9\/4 12:05$/);
});

test('geometry constants stay in sync with the export template and backend', () => {
  assert.deepEqual(model.CUT_LINES, ['none', 'dash', 'solid']);
  assert.equal(model.BOARD_LINE_PX, 18);
  assert.equal(model.BOARD_MM_PX, 3.779528);
});

test('bridge contract: the two modules export disjoint names, and domain/board keeps its adapters', () => {
  // installBoardBridge 用 Object.assign 把两个模块的导出一起挂到 window，同名导出会互相覆盖
  const overlap = Object.keys(model).filter(name => Object.hasOwn(domain, name));
  assert.deepEqual(overlap, []);
  assert.equal(typeof domainIndex.boardQuickAdd, 'function');
  assert.equal(typeof domainIndex.boardChooseAndAdd, 'function');
  assert.equal(domainIndex.boardFolderTree, domain.boardFolderTree);
  // 没有题目时适配器安静地返回 undefined，不打开浮层（有题目时的行为见 board-picker.test.mjs）
  assert.equal(domainIndex.boardQuickAdd(''), undefined);
  assert.equal(domainIndex.boardQuickAdd([]), undefined);
  assert.equal(domainIndex.boardChooseAndAdd([]), undefined);
  assert.equal(domainIndex.boardChooseAndAdd('Q1'), undefined);
  assert.equal(domainIndex.boardPickerOpen, pickerModule.boardPickerOpen);
});

test('bridge contract: all board modules export disjoint names (P7 第 2 轮起含保存、打印、预览，第 3 轮起含设置、拖拽，第 4 轮起含选板浮层)', () => {
  const names = [domain, model, saveModule, printModule, previewModule, settingsModule, dragModule, pickerModule].flatMap(ns => Object.keys(ns));
  assert.deepEqual(names.filter((name, index) => names.indexOf(name) !== index), []);
  for (const name of ['createBoardSaveQueue', 'createBoardPrint', 'fetchBoardExport', 'measureBoardLayout', 'boardPreviewSetBoard', 'boardPreviewLayout',
    'createBoardSettings', 'bindBoardRowDrag', 'bindBoardTreeDrag', 'boardTreeDropPlan', 'boardPickerOpen', 'boardPickerClose', 'boardPickerIsOpen'])
    assert.ok(names.includes(name), name);
});
