// P7 第 5 轮：展示板页的视图模型（features/board/state.js）与板列表的数据所有者（domain/board/boards.js）。
// boards.js 的 I/O（post、对话框、toast、localStorage、旧 board.js 钩子）全部经 configureBoards 换成替身。
import test from 'node:test';
import assert from 'node:assert/strict';
import * as S from '../../assets/app/features/board/state.js';
import * as B from '../../assets/app/domain/board/boards.js';

const FOLDERS = [{ id: 'F1', name: '高三上', order: 0 }, { id: 'F2', name: '高三下', order: 1 }];
const BOARDS = [
  { id: 'B1', name: '三角', folder_id: 'F1', order: 0, count: 6, printed_summary: { pages: 2, new_count: 3 }, updated_at: '2026-09-27T08:01:00' },
  { id: 'B2', name: '数列', folder_id: 'F1', order: 1, count: 2, missing: 1, suspended: 1 },
  { id: 'B3', name: '散题', folder_id: '', order: 0, count: 0, note: '备注' },
];
const detail = (extra = {}) => ({ id: 'B1', name: '三角', note: '', print: { locked: false },
  items: [{ uid: 'a', subject: '数学', printed: true }, { uid: 'b', subject: '数学' }, { uid: 'c', subject: '物理', missing: true }],
  printed_summary: { pages: 0, count: 0, new_count: 0 }, ...extra });

function memory() {
  const data = new Map();
  return { getItem: key => (data.has(key) ? data.get(key) : null), setItem: (key, value) => data.set(key, String(value)) };
}
function fakes({ answers = [], flush = true, post } = {}) {
  const calls = { posts: [], toasts: [], reloads: 0, prompts: [] };
  const queue = [...answers];
  B.configureBoards({ reset: true });
  B.configureBoards({
    storage: () => fakes.store,
    post: async (path, body) => { calls.posts.push([path, body]); return post ? post(path, body) : { ok: true, data: { board: { id: 'NEW', items: [] }, folder: { id: 'FN' } } }; },
    prompt: async (title, value) => { calls.prompts.push([title, value]); return queue.shift() ?? null; },
    confirm: async () => queue.shift() ?? false,
    dialog: async spec => { calls.dialog = spec; return queue.shift() ?? { ok: false, values: {} }; },
    toast: (text, options) => calls.toasts.push([text, options?.kind || 'ok']),
    hooks: { flush: async () => flush, reload: async () => { calls.reloads += 1; }, detail: () => null },
  });
  B.adoptBoards({ boards: BOARDS, folders: FOLDERS });
  return calls;
}
fakes.store = memory();

test('statusView：没有板时空；有板时科目汇总跳过缺失、打印范围与主行动来自状态机', () => {
  assert.deepEqual(S.statusView({ detail: null }), { empty: true });
  const v = S.statusView({ detail: detail(), mode: 'all', awaiting: null });
  assert.equal(v.subjects, '数学 2');
  assert.equal(v.count, 3);
  assert.equal(v.action.type, 'preview');
  assert.equal(v.canNew, false);
  const paper = S.statusView({ detail: detail({ printed_summary: { pages: 2, count: 1, new_count: 2 } }), mode: 'new', awaiting: null });
  assert.equal(paper.scope, 'new');
  assert.equal(paper.canNew, true);
  assert.equal(paper.newCount, 2);
  assert.equal(S.statusView({ detail: detail(), mode: 'all', awaiting: { mode: 'all' } }).action.type, 'mark-printed');
});

test('treeView：文件夹组 + 恒在最后的未归档；折叠的组不列板；组标题带题数与未印数；当前板标 on', () => {
  assert.deepEqual(S.treeView({ boards: [], folders: [] }), { empty: true, count: 0, groups: [] });
  const t = S.treeView({ boards: BOARDS, folders: FOLDERS, current: 'B1', collapsed: new Set(['F2']) });
  assert.equal(t.count, 3);
  assert.deepEqual(t.groups.map(g => [g.id, g.name, g.plain, g.folded, g.boards.length]),
    [['F1', '高三上', false, false, 2], ['F2', '高三下', false, true, 0], ['', '未归档', true, false, 1]]);
  assert.equal(t.groups[0].newCount, 3);
  assert.equal(t.groups[0].title, '高三上：2 板 · 8 题 · 3 题还没印上纸');
  assert.equal(t.groups[0].boards[0].on, true);
  assert.equal(t.groups[2].boards[0].title, '备注');
  const folded = S.treeView({ boards: BOARDS, folders: FOLDERS, collapsed: new Set(['F1']) });
  assert.equal(folded.groups[0].boards.length, 0);
});

test('boardMetaBits：题数、已印页数与未印题数分别呈现，缺失和停用可见', () => {
  assert.deepEqual(S.boardMetaBits(BOARDS[0]).slice(0, 3), [{ text: '6 题' }, { text: '已印 2 页', tone: 'ok' }, { text: '3 题未印', tone: 'new' }]);
  assert.deepEqual(S.boardMetaBits(BOARDS[1]).map(b => b.text), ['2 题', '缺失 1', '停用 1']);
  assert.equal(S.boardMetaBits(BOARDS[1])[1].tone, 'warn');
});

test('stageView / estimateView：视图、警告计数、翻页条读数；仅新增的读数按导出范围', () => {
  assert.deepEqual(S.stageView({ detail: null }), { empty: true });
  const items = [{ uid: 'a' }, { uid: 'b', missing: true }, { uid: 'c', suspended: true }, { uid: 'd', suspended: true, missing: true }];
  const s = S.stageView({ detail: detail({ items }), view: 'weird', mode: 'all' }, { layout: { pages: 3, page_numbers: [1, 2, 3], warnings: [1] }, view: { page: 2 }, zoom: 1 });
  assert.equal(s.view, 'paper');
  assert.deepEqual([s.missing, s.suspended, s.count], [2, 1, 4]);
  assert.deepEqual([s.pager.multi, s.pager.page, s.pager.pages, s.pager.zoom], [true, 2, 3, '1']);
  assert.deepEqual(s.pager.estimate, { scope: 'all', pages: 3, rendered: 0, range: '第 1–3 页', partial: 0, warnings: 1 });
  assert.equal(S.stageView({ detail: detail(), view: 'list' }).pager.estimate, null, '版面还没回来时是「正在排版」');
  // mode 是 new 但没有纸面：导出与读数都按「全部」（旧 boardEffectiveMode）
  assert.equal(S.stageView({ detail: detail(), mode: 'new' }, { layout: { pages: 1 } }).pager.estimate.scope, 'all');
  assert.equal(S.estimateView({ pages: 4, rendered_pages: 1, page_numbers: [4], partial_page: 3 }, 'new').range, '第 4 页');
  assert.equal(S.firstNewUid([{ uid: 'x', printed: true }, { uid: 'y', missing: true }, { uid: 'z' }]), 'z');
  assert.deepEqual(s.pager.motion, { kind: 'fade', duration: 280 });
});

test('展示板动效偏好：非法值回默认，时长按 50ms 步进并写入浏览器本地', () => {
  const data = new Map();
  const storage = { getItem: key => data.get(key) || null, setItem: (key, value) => data.set(key, value) };
  assert.deepEqual(S.normalizeMotion(), { kind: 'fade', duration: 280 });
  assert.deepEqual(S.normalizeMotion({ kind: 'unknown', duration: 9999 }), { kind: 'fade', duration: 800 });
  assert.deepEqual(S.normalizeMotion({ kind: 'paper', duration: 280 }), { kind: 'paper', duration: 280 });
  assert.deepEqual(S.normalizeMotion({ kind: 'slide', duration: 123 }), { kind: 'slide', duration: 100 });
  assert.deepEqual(S.saveMotionPreference({ kind: 'paper', duration: 450 }, storage), { kind: 'paper', duration: 450 });
  assert.deepEqual(S.readMotionPreference(storage), { kind: 'paper', duration: 450 });
  assert.equal(JSON.parse(data.get('omrs-board-motion')).kind, 'paper');
  S.setMotion({ kind: 'fade', duration: 280 }, storage);
});

test('菜单：板菜单列出别的文件夹与未归档；文件夹菜单到头时禁用上移 / 下移', () => {
  const values = S.boardMenuItems(BOARDS[0], FOLDERS).filter(i => !i.divider).map(i => i.value);
  assert.deepEqual(values, ['rename', 'note', 'duplicate', 'export', 'move:F2', 'move:', 'move-new', 'delete']);
  assert.ok(!S.boardMenuItems(BOARDS[2], FOLDERS).some(i => i.value === 'move:'), '未归档的板不再列「移到未归档」');
  const first = S.folderMenuItems(FOLDERS[0], FOLDERS);
  assert.deepEqual(first.filter(i => i.disabled).map(i => i.value), ['up']);
  assert.deepEqual(S.folderMenuItems(FOLDERS[1], FOLDERS).filter(i => i.disabled).map(i => i.value), ['down']);
});

test('boards：采纳、订阅通知、当前板与上次用的板、首选板、折叠状态存本地', () => {
  fakes();
  let hits = 0;
  const off = B.onBoards(() => { hits += 1; });
  B.adoptBoards({ boards: BOARDS, folders: FOLDERS });
  B.boardRemember('B2');
  assert.equal(B.boardCurrentId(), 'B2');
  assert.equal(B.boardLastId(), 'B2');
  B.boardRemember('');
  assert.equal(B.boardCurrentId(), '');
  assert.equal(B.boardLastId(), 'B2', '清当前板不动记忆');
  assert.equal(B.boardPreferredId(), 'B2');
  B.adoptBoards({ boards: BOARDS.filter(b => b.id !== 'B2'), folders: FOLDERS });
  assert.equal(B.boardPreferredId(), 'B1', '记住的板没了就落到第一块');
  assert.deepEqual([...B.boardFolderToggle('F1')], ['F1']);
  assert.deepEqual([...B.boardFolderCollapsed()], ['F1']);
  B.boardFolderToggle('F1', false);
  assert.equal(B.boardFolderCollapsed().size, 0);
  assert.equal(hits, 6);
  off();
  B.adoptBoards({});
  assert.equal(hits, 6, '退订后不再通知');
  assert.deepEqual([B.boardList(), B.boardFolders()], [[], []]);
});

test('boards：悬停说明写上次用的板；没有板时提示先新建', () => {
  fakes();
  B.boardRemember('B3');
  assert.equal(B.boardHintText(), '加入展示板（上次：散题）· Shift 点击直接加入');
  B.adoptBoards({});
  assert.equal(B.boardHintText(), '加入展示板（还没有板，会先新建）');
});

test('createBoard：冲刷失败就放弃；取消对话框不发请求；成功后设为当前板、重读、toast', async () => {
  let calls = fakes({ flush: false });
  assert.equal(await B.createBoard(), null);
  assert.equal(calls.prompts.length, 0);
  calls = fakes({ answers: [null] });
  assert.equal(await B.createBoard(null, 'F1'), null);
  assert.equal(calls.posts.length, 0);
  calls = fakes({ answers: ['新板'] });
  const board = await B.createBoard([{ question_id: 'q-u1' }], 'F1');
  assert.equal(board.id, 'NEW');
  assert.deepEqual(calls.posts, [['/api/board/create', { name: '新板', question_refs: [{ question_id: 'q-u1' }], folder_id: 'F1' }]]);
  assert.equal(B.boardCurrentId(), 'NEW');
  assert.equal(calls.reloads, 1);
  assert.equal(calls.toasts[0][0], '已新建《新板》，加入 0 题');
});

test('saveBoardName / renameBoard：同名或空名不发请求；失败弹错误 toast', async () => {
  let calls = fakes();
  assert.equal(await B.saveBoardName('B1', '三角'), false);
  assert.equal(await B.saveBoardName('B1', '  '), false);
  assert.equal(calls.posts.length, 0);
  assert.equal(await B.saveBoardName('B1', ' 三角·改 '), true);
  assert.deepEqual(calls.posts[0], ['/api/board/update', { id: 'B1', name: '三角·改' }]);
  calls = fakes({ answers: ['别名'], post: async () => ({ ok: false, error: { message: '磁盘满' } }) });
  assert.equal(await B.renameBoard('B1'), false);
  assert.deepEqual(calls.toasts, [['重命名失败：磁盘满', 'error']]);
  assert.equal(calls.reloads, 0);
});

test('deleteBoard：删的是当前板时清掉当前板再重读；取消确认不发请求', async () => {
  let calls = fakes({ answers: [false] });
  await B.deleteBoard('B1');
  assert.equal(calls.posts.length, 0);
  calls = fakes({ answers: [true] });
  B.boardRemember('B1');
  await B.deleteBoard('B1');
  assert.deepEqual(calls.posts, [['/api/board/delete', { id: 'B1' }]]);
  assert.equal(B.boardCurrentId(), '');
  assert.equal(calls.toasts[0][0], '已删除《三角》');
});

test('文件夹：新建时带上要移进去的板；上移到头不动；删除有板的文件夹按选择保留或连板删除', async () => {
  let calls = fakes({ answers: ['新夹'] });
  await B.createFolder('B3');
  assert.deepEqual(calls.posts, [['/api/board/folder/create', { name: '新夹' }], ['/api/board/move', { id: 'B3', folder_id: 'FN' }]]);
  calls = fakes();
  await B.reorderFolder('F1', -1);
  await B.reorderFolder('F2', 1);
  assert.equal(calls.posts.length, 0);
  await B.reorderFolder('F2', -1);
  assert.deepEqual(calls.posts, [['/api/board/folder/update', { id: 'F2', order: 0 }]]);
  calls = fakes({ answers: [{ ok: true, values: { 'bd-fd-keep': false, 'bd-fd-drop': true } }] });
  await B.deleteFolder('F1');
  assert.match(calls.dialog.hint, /2 个板/);
  assert.deepEqual(calls.posts, [['/api/board/folder/delete', { id: 'F1', keep_boards: false }]]);
  calls = fakes({ answers: [true] });
  await B.deleteFolder('F2');
  assert.deepEqual(calls.posts, [['/api/board/folder/delete', { id: 'F2', keep_boards: true }]]);
  assert.equal(calls.toasts[0][0], '已删除文件夹「高三下」');
});

test('applyTreeDrop：文件夹排序与移板两种落点', async () => {
  const calls = fakes();
  await B.applyTreeDrop({ type: 'folder-order', id: 'F2', order: 0 });
  await B.applyTreeDrop({ type: 'move', boardId: 'B3', folderId: 'F1', index: 1 });
  await B.applyTreeDrop(null);
  assert.deepEqual(calls.posts, [['/api/board/folder/update', { id: 'F2', order: 0 }], ['/api/board/move', { id: 'B3', folder_id: 'F1', index: 1 }]]);
  assert.equal(calls.reloads, 2);
});

// ---------- P7 第 6 轮：列表 / 画廊 / 检查器 / 加题对话框的视图模型，排序，板详情端口 ----------
import { boardSortItems } from '../../assets/app/features/board/model.js';
import { connectBoardDetail, boardDetailPort } from '../../assets/app/domain/board/detail-port.js';

test('itemFlags：缺失 / 停用优先且不再标纸面状态；有纸面时已印带页码、未印为新增、改过另挂一个', () => {
  const text = (item, paper = true) => S.itemFlags(item, paper).map(f => `${f.tone}:${f.text}`);
  assert.deepEqual(text({ missing: true, printed: true }), ['muted:缺失']);
  assert.deepEqual(text({ suspended: true, printed: true }), ['muted:停用']);
  assert.deepEqual(text({ printed: true, printed_page: 3, changed: true }), ['paper:已印 p.3', 'changed:已改动']);
  assert.deepEqual(text({}), ['new:未印']);
  assert.deepEqual(text({}, false), [], '没有纸面记录时不标新增');
});

test('gapReadout：自定的与继承的留白读数（列表行、画廊卡、检查器同源）', () => {
  assert.deepEqual(S.gapReadout({ gap_lines: null }, { gap_lines: 3 }).text, '留白 3 行（继承）');
  const own = S.gapReadout({ gap_lines: 5 }, { gap_lines: 3 });
  assert.equal(own.text, '留白 5 行');
  assert.equal(own.inherited, false);
  assert.match(own.long, /^5 行 ≈ [\d.]+ cm$/);
});

test('dueView：与题库同一分档', () => {
  assert.equal(S.dueView(null), null);
  assert.deepEqual(S.dueView(-2), { text: '逾期 2 天', tone: 'danger' });
  assert.deepEqual(S.dueView(0), { text: '今日到期', tone: 'warn' });
  assert.equal(S.dueView(5).tone, 'info');
  assert.equal(S.dueView(30).tone, '');
});

test('contentView：纸面与题目列表同时存在；列表行带序号、选中、到期，缺失题不算到期', () => {
  const snap = view => ({ detail: detail({ printed_summary: { pages: 1 } }), view, selected: 'b' });
  assert.equal(S.contentView(snap('paper')).kind, 'list');
  assert.equal(S.contentView({ detail: null, view: 'list' }).kind, 'none');
  const list = S.contentView(snap('list'), { dueDays: () => 1 });
  assert.equal(list.kind, 'list');
  assert.deepEqual(list.rows.map(r => [r.no, r.uid, r.selected]), [[1, 'a', false], [2, 'b', true], [3, 'c', false]]);
  assert.equal(list.rows[1].due.text, '1 天后');
  assert.equal(list.rows[2].due, null);
  assert.equal(list.rows[0].flags[0].text, '已印');
  assert.equal(S.contentView({ detail: detail({ items: [] }), view: 'gallery' }).empty, true);
});

test('inspectorView：没选中时只有版式与纸面；选中后给第 N 题、留白与锁定说明；纸面续排位置', () => {
  const base = detail({ print: { locked: true, note_ratio: .42, gap_lines: 4, cut_line: 'none', answers: 'append' },
    printed_summary: { pages: 2, count: 1, cursor: { page: 2, y: 88.6 }, changed_count: 1 } });
  const none = S.inspectorView({ detail: base, selected: '' });
  assert.equal(none.selected, false);
  assert.equal(none.item, null);
  assert.deepEqual(none.motion, { kind: 'fade', duration: 280 });
  assert.deepEqual([none.layout.ratio, none.layout.gap, none.layout.cut, none.layout.answers, none.layout.locked], [42, 4, 'none', 'append', true]);
  assert.deepEqual([none.paper.has, none.paper.cursorPage, none.paper.cursorY, none.paper.changed], [true, 2, 89, 1]);
  const one = S.inspectorView({ detail: base, selected: 'a' });
  assert.equal(one.item.no, 1);
  assert.equal(one.item.own, '');
  assert.equal(one.item.inherited, 4);
  assert.match(one.item.note, /锁定时修改实际留白需确认/);
  assert.equal(S.inspectorView({ detail: null }).empty, true);
  assert.equal(S.inspectorView({ detail: detail(), selected: '' }).paper.has, false);
});

test('加题对话框：筛选条件与旧 boardAddFilterState 同义；已在板里的标灰且全选跳过', () => {
  const f = S.addFilters({ ...S.ADD_DEFAULTS, text: '  Sin ', ktag: '诱导公式', labels: ['重点'] });
  assert.equal(f.text, 'sin');
  assert.equal(f.knowledgeTag, '诱导公式');
  assert.deepEqual([f.labelMode, f.suspended, f.sort], ['any', '', 'mastery-asc']);
  const visible = [{ uid: 'a', mastery: .5 }, { uid: 'b' }, { uid: 'c' }];
  const rows = S.addRows(visible, new Set(['a']), new Set(['c']));
  assert.deepEqual(rows.map(r => [r.uid, r.in, r.on]), [['a', true, true], ['b', false, false], ['c', false, true]]);
  assert.equal(rows[0].mastery, 50);
  assert.deepEqual([...S.addSelectAll(visible, new Set(['a']), new Set())].sort(), ['b', 'c']);
});

test('排序菜单：boardSortItems 返回新数组，未知选项按科目 / 分类 / UID', () => {
  const items = [{ uid: 'z', subject: '物理', mastery: .9, due_date: '', added_at: '2' }, { uid: 'a', subject: '数学', mastery: .1, due_date: '2026-01-01', added_at: '1' }];
  assert.deepEqual(boardSortItems(items, 'mastery').map(i => i.uid), ['a', 'z']);
  assert.deepEqual(boardSortItems(items, 'due').map(i => i.uid), ['a', 'z']);
  assert.deepEqual(boardSortItems(items, 'added').map(i => i.uid), ['a', 'z']);
  assert.deepEqual(boardSortItems(items, 'reverse').map(i => i.uid), ['a', 'z']);
  assert.equal(boardSortItems(items, 'subject').length, 2);
  assert.deepEqual(items.map(i => i.uid), ['z', 'a'], '不改原数组');
});

test('板详情端口：没接上时是安全的空实现；接上后按调用时的实现转调', async () => {
  const calls = [];
  connectBoardDetail({ add: async (id, uids, options) => { calls.push(['add', id, uids, options]); return { id }; }, bogus: () => {} });
  assert.deepEqual(await boardDetailPort.add('B1', ['x']), { id: 'B1' });
  assert.deepEqual(calls, [['add', 'B1', ['x'], {}]]);
  connectBoardDetail({ flush: async () => false });
  assert.equal(await boardDetailPort.flush(), false);
});
