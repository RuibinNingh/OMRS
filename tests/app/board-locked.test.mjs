// P7 第 1 步由 tests/test_board_locked_incremental.js 迁来，用例只增不减。P7 第 6 轮起旧 assets/board.js 已删，
// 板详情归 features/board/detail.js：原来在 vm 里真跑旧脚本，现在用 createBoardDetail 注入替身，动作、确认、脏字段与
// 保存逻辑照常执行，只替换 I/O（get / post / 对话框 / toast / 预览）。用例里原来的字符串动作改成对 detail 的调用，断言不变；
// 检查器文案改查 state.js 的 inspectorView（模板只是把它原样画出来）。
import test from 'node:test';
import assert from 'node:assert/strict';
import { createBoardDetail } from '../../assets/app/features/board/detail.js';
import { boardStatusModel } from '../../assets/app/features/board/model.js';
import { inspectorView } from '../../assets/app/features/board/state.js';
import { configureBoards, adoptBoards, boardRemember, boardCurrentId } from '../../assets/app/domain/board/boards.js';
const clone = value => JSON.parse(JSON.stringify(value));

function harness({ paper = true, locked = true, confirm = false, extra = {} } = {}) {
  const posts = [], gets = [], confirms = [], toasts = [], rejected = [], beacons = [];
  const initial = { id: 'BD-test', name: '锁定板', print: { locked, note_ratio: .5, gap_lines: 2,
    answers: 'none', show_labels: true, show_meta: true, cut_line: 'dash', cut_label: false },
    printed: { pages: paper ? 2 : 0, items: paper ? [{ question_id: 'OP-000001', uid: 'old' }] : [] },
    printed_summary: { pages: paper ? 2 : 0, count: paper ? 1 : 0, new_count: 1, cursor: { page: 2, y: 123 } },
    items: [{ question_id: 'OP-000001', uid: 'old', printed: paper, gap_lines: null },
            { question_id: 'OP-000002', uid: 'new', printed: false, gap_lines: null }] };
  configureBoards({ reset: true });
  configureBoards({ storage: () => null });
  const store = new Map();
  let d = null;
  d = createBoardDetail({
    // 重读：列表只有这一块板，详情原样读回当前内存里的那份（原来的替身是把 boardReloadData 换成空函数）
    get: async path => { gets.push(path); return path === '/api/boards' ? { boards: [d.detail()], folders: [] } : { board: d.detail() }; },
    post: async (url, payload) => { posts.push({ url, payload: clone(payload) }); return { board: { ...d.detail(), added: 1 } }; },
    toast: (...args) => toasts.push(args),
    confirm: async (...args) => { confirms.push(args); return confirm; },
    dialog: async () => ({ ok: false, values: {} }),
    items: () => [], labels: () => [],
    storage: () => ({ getItem: key => (store.has(key) ? store.get(key) : null), setItem: (key, value) => store.set(key, String(value)) }),
    preview: {}, pageActive: () => false, gotoBoard: () => {}, openQuestion: () => {},
    setTimer: () => 1, clearTimer: () => {},
    beacon: (url, blob) => { beacons.push([url, blob]); return true; },
    rejected: () => rejected.push(1),
    ...extra,
  });
  d.adoptDetail(initial);
  boardRemember(initial.id);
  adoptBoards({ boards: [initial] });
  return { d, posts, gets, confirms, toasts, rejected, beacons, detail: () => clone(d.detail()) };
}

test('统一加题入口：锁定板无需破坏性确认，新增打印范围保持 new', async () => {
  const h = harness();
  const before = h.detail().printed;
  const result = await h.d.addToBoard('BD-test', ['new', 'new']);
  assert.equal(h.confirms.length, 0);
  assert.ok(result);
  assert.deepEqual(clone(h.posts), [{ url: '/api/board/items/add', payload: { id: 'BD-test', uids: ['new'] } }]);
  assert.deepEqual(h.detail().printed, before);
  assert.equal(boardStatusModel(h.d.detail(), 'new', null).scope, 'new');
  assert.equal(h.d.settings().granted(), false, '安全操作不应授予下一次破坏性修改权限');
});

test('切板读取失败时选中项与详情仍指向原板', async () => {
  const h = harness({ extra: { get: async () => { throw new Error('网络中断'); } } });
  await h.d.load('BD-other');
  assert.equal(boardCurrentId(), 'BD-test');
  assert.equal(h.d.detail().id, 'BD-test');
  assert.match(h.toasts.at(-1)[0], /网络中断/);
});

test('重置或切换范围后，旧打印窗口消息不能恢复已清空纸面', async () => {
  const h = harness({ confirm: true });
  const popup = {};
  h.d.print().windows.set(popup, { boardId: 'BD-test', mode: 'all', layout: null });
  h.d.print().jobs.delete('BD-test');
  const handler = event => h.d.handleMessage(event);   // 浏览器里由 installBoardWindow 挂到 window 的 message
  await handler({ source: {}, data: { type: 'omrs-board-printed' } });
  await handler({ source: popup, data: {
    type: 'omrs-board-printed', boardId: 'BD-test', mode: 'all',
    layout: { board_id: 'BD-test', mode: 'all', pages: 1,
      items: [{ question_id: 'OP-000001', uid: 'old', segments: [{page: 1}] }] },
  }});
  assert.equal(h.posts.length, 0);
  assert.equal(h.confirms.length, 0);
});

test('锁定说明表达纸面保护边界，不把增删排序说成全部重印', () => {
  const h = harness();
  h.d.select('old');
  const ins = inspectorView(h.d.snapshot());
  assert.doesNotMatch(ins.layout.lockHint, /排序或增删题目会先确认/);
  assert.match(ins.layout.lockHint, /增删.*排序.*保留纸面/);
  assert.match(ins.item.note, /锁定.*确认.*清空纸面/);
  assert.doesNotMatch(ins.item.note, /也不会改纸面记录/);
  h.d.detail().printed_summary.new_count = 0;
  assert.doesNotMatch(boardStatusModel(h.d.detail(), 'all', null).why, /顺序才需要重印/);
});

const safeChanges = [
  ["removeItem('new')", d => d.removeItem('new'), '/api/board/items/remove'],
  ["removeItem('old')", d => d.removeItem('old'), '/api/board/items/remove'],
  ["sort('reverse')", d => d.sort('reverse'), '/api/board/update'],
  ['persistItems([])', d => d.persistItems([]), '/api/board/update'],
  ['persistItems([...items, third])', d => d.persistItems([...d.detail().items, { uid: 'third', question_id: 'OP-000003' }]), '/api/board/update'],
  ["setItemGap('new', 13)", d => d.setItemGap('new', 13), '/api/board/update'],
  ["setItemGap('old', 2)", d => d.setItemGap('old', 2), '/api/board/update'],
  ["applyPrintField('note_ratio', 50)", d => d.applyPrintField('note_ratio', 50), null],
  ["applyPrintField('answers', 'append')", d => d.applyPrintField('answers', 'append'), '/api/board/update'],
];
for (const [action, run, url] of safeChanges) test(`不影响纸面无需确认：${action}`, async () => {
  const h = harness();
  await run(h.d);
  await h.d.flush();
  assert.equal(h.confirms.length, 0);
  assert.equal(h.d.settings().granted(), false);
  assert.equal(h.posts.length, url ? 1 : 0);
  if (url) assert.equal(h.posts[0].url, url);
  if (action.includes("'new', 13")) assert.equal(h.posts[0].payload.items[1].gap_lines, 13);
  if (action.includes('reverse')) assert.deepEqual(clone(h.posts[0].payload.items.map(i => i.uid)), ['new', 'old']);
  if (action.includes("removeItem('old')")) assert.match(h.toasts[0][0], /纸面记录保留其占位/);
});

test('关闭切割线时修改未生效的线标签无需确认', async () => {
  const h = harness();
  h.d.detail().print.cut_line = 'none';
  await h.d.applyPrintField('cut_label', true);
  await h.d.flush();
  assert.equal(h.confirms.length, 0);
  assert.equal(h.posts[0]?.payload.print.cut_label, true);
});

test('按标记同步先等待本地 items 保存，避免覆盖刚追加的题目', async () => {
  const h = harness({ extra: {
    labels: () => [{ name: '重点', archived: false, count: 1 }],
    items: () => [{ uid: 'new', labels: ['重点'], suspended: false }],
    dialog: async () => ({ ok: true, values: { 'bd-sync-0': true } }),
  } });
  h.d.saveQueue().mark('items');
  await h.d.syncLabel();
  assert.deepEqual(h.posts.map(post => post.url), [
    '/api/board/update', '/api/board/items/add', '/api/board/update',
  ]);
});

test('全局留白只影响未打印题时无需确认', async () => {
  const h = harness();
  h.d.detail().items[0].gap_lines = 2;
  await h.d.applyPrintField('gap_lines', 11);
  await h.d.flush();
  assert.equal(h.confirms.length, 0);
  assert.equal(h.posts[0]?.payload.print.gap_lines, 11);
});

test('没有纸面时锁定不弹破坏性确认', async () => {
  const h = harness({ paper: false });
  await h.d.applyPrintField('note_ratio', 42);
  await h.d.flush();
  assert.equal(h.confirms.length, 0);
  assert.equal(h.posts[0]?.payload.print.note_ratio, .42);
});

const destructive = [
  ["applyPrintField('note_ratio', 42)", d => d.applyPrintField('note_ratio', 42)],
  ["setItemGap('old', 9)", d => d.setItemGap('old', 9)],
  ["applyPrintField('gap_lines', 9)", d => d.applyPrintField('gap_lines', 9)],
  ['persistItems(items.map(gap 9))', d => d.persistItems(d.detail().items.map(i => ({ ...i, gap_lines: 9 })))],
];
for (const [action, run] of destructive) {
  test(`真正影响已印区域取消后零写入：${action}`, async () => {
    const h = harness();
    const before = h.detail();
    await run(h.d);
    await h.d.flush();
    assert.equal(h.confirms.length, 1);
    assert.equal(h.posts.length, 0);
    assert.deepEqual(h.detail(), before);
    assert.equal(h.d.saveQueue().dirty(), null);
  });
}

// ---------- P7 第 6 轮：detail.js 自己的行为 ----------

test('锁定确认被拒：先让页面放掉焦点（rejected），聚焦中的输入框才能被重绘改回旧值', async () => {
  const h = harness();
  await h.d.setItemGap('old', 9);
  assert.equal(h.rejected.length, 1);
  await h.d.applyPrintField('note_ratio', 42);
  assert.equal(h.rejected.length, 2);
});

test('打印范围：切换清掉上一次「等待记录」；没有纸面的板载入后回到「打印全部」', async () => {
  const h = harness();
  h.d.markAwaiting('all');
  assert.ok(h.d.snapshot().awaiting);
  h.d.setMode('new');
  assert.equal(h.d.mode(), 'new');
  assert.equal(h.d.snapshot().awaiting, null);
  const empty = harness({ paper: false });
  empty.d.setMode('new');
  await empty.d.load('BD-test');
  assert.equal(empty.d.mode(), 'all');
});

test('并发重读只采纳最后一次：先发后到的旧列表不覆盖新数据', async () => {
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  const calls = [];
  const h = harness({ extra: { get: async path => {
    calls.push(path);
    if (path === '/api/boards' && calls.length === 1) { await gate; return { boards: [{ id: 'STALE', name: '旧' }], folders: [] }; }
    return path === '/api/boards' ? { boards: [{ id: 'BD-test', name: '锁定板' }], folders: [] } : { board: { id: 'BD-test', name: '新', items: [] } };
  } } });
  const first = h.d.reloadData();
  await h.d.reloadData();
  release();
  await first;
  assert.equal(h.d.detail().name, '新');
});

test('在途详情读取不能覆盖随后编辑且保存冲突的本地留白', async () => {
  let release, started;
  const gate = new Promise(resolve => { release = resolve; });
  const reading = new Promise(resolve => { started = resolve; });
  const h = harness({ locked: false, extra: {
    get: async () => { started(); await gate; return { board: { id: 'BD-test', items: [{ uid: 'old', gap_lines: null }] } }; },
    post: async () => { throw Object.assign(new Error('其它客户端已写入'), { status: 409 }); },
  } });
  const load = h.d.load('BD-test');
  await reading;
  await h.d.setItemGap('old', 6);
  assert.equal(await h.d.flush(), false);
  release();
  await load;
  assert.equal(h.d.detail().items[0].gap_lines, 6);
  assert.equal(h.d.saveQueue().conflicted(), true);
  assert.equal(h.d.saveQueue().takePayload(), null);
});

test('关页落盘：有脏字段时用 sendBeacon 交出同一份载荷，没有脏字段时不发', () => {
  const h = harness({ locked: false });
  h.d.beforeUnload();
  assert.equal(h.beacons.length, 0);
  h.d.detail().print.note_ratio = .42;
  h.d.markDirty('print');
  h.d.beforeUnload();
  assert.equal(h.beacons.length, 1);
  assert.equal(h.beacons[0][0], '/api/board/update');
});

test('视图只存本地；选中的题随快照给页面，换板后不在板里的选中清空', async () => {
  const h = harness();
  assert.equal(h.d.view(), 'paper');
  h.d.setView('gallery');
  assert.equal(h.d.snapshot().view, 'gallery');
  h.d.setView('bogus');
  assert.equal(h.d.view(), 'paper');
  h.d.select('new');
  assert.equal(h.d.snapshot().selected, 'new');
  h.d.detail().items = h.d.detail().items.filter(item => item.uid !== 'new');
  await h.d.load('BD-test');
  assert.equal(h.d.selected(), '');
});
