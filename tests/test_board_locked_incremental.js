'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../assets/board.js'), 'utf8');
const clone = value => JSON.parse(JSON.stringify(value));

function harness({ paper = true, locked = true, confirm = false } = {}) {
  const posts = [], confirms = [], toasts = [], handlers = {};
  const detail = { id: 'BD-test', name: '锁定板', print: { locked, note_ratio: .5, gap_lines: 2,
    answers: 'none', show_labels: true, show_meta: true, cut_line: 'dash', cut_label: false },
    printed: { pages: paper ? 2 : 0, items: paper ? [{ question_id: 'OP-000001', uid: 'old' }] : [] },
    printed_summary: { pages: paper ? 2 : 0, count: paper ? 1 : 0, new_count: 1, cursor: { page: 2, y: 123 } },
    items: [{ question_id: 'OP-000001', uid: 'old', printed: paper, gap_lines: null },
            { question_id: 'OP-000002', uid: 'new', printed: false, gap_lines: null }] };
  const ctx = vm.createContext({ console, initial: detail, posts, confirms, toasts,
    setTimeout: () => 1, clearTimeout: () => {}, CSS: { escape: x => x },
    localStorage: { getItem: () => null, setItem: () => {} },
    window: { addEventListener: (name, fn) => (handlers[`window:${name}`] ||= []).push(fn) },
    document: { addEventListener: (name, fn) => (handlers[name] ||= []).push(fn),
      querySelector: () => null, querySelectorAll: () => [], getElementById: () => null },
    uiConfirm: async (...args) => { confirms.push(args); return confirm; },
    uiToast: (...args) => toasts.push(args),
    clampNumber: (x, lo, hi, fallback) => Number.isFinite(Number(x)) ? Math.max(lo, Math.min(hi, Number(x))) : fallback,
    asNumber: (x, fallback) => Number.isFinite(Number(x)) ? Number(x) : fallback,
    escapeHtml: String, escapeAttr: String,
  });
  vm.runInContext(source, ctx);
  // 只替换 I/O 与渲染边界；实际动作、确认、脏字段与保存逻辑照常执行。
  vm.runInContext(`BOARD_DETAIL = initial; BOARD_CURRENT = initial.id; BOARD_DATA = [initial];
    boardReloadData = async () => {}; boardPushRelayout = () => {};
    boardScheduleEstimate = () => {}; boardRender = () => {};
    boardPost = async (url, payload) => { posts.push({url, payload: JSON.parse(JSON.stringify(payload))});
      return {board: {...BOARD_DETAIL, added: 1}}; };`, ctx);
  return { ctx, posts, confirms, toasts, handlers, run: code => vm.runInContext(code, ctx),
    detail: () => clone(vm.runInContext('BOARD_DETAIL', ctx)) };
}

test('统一加题入口：锁定板无需破坏性确认，新增打印范围保持 new', async () => {
  const h = harness();
  const before = h.detail().printed;
  const result = await h.run("boardAddToBoard('BD-test', ['new', 'new'])");
  assert.equal(h.confirms.length, 0);
  assert.ok(result);
  assert.deepEqual(clone(h.posts), [{ url: '/api/board/items/add', payload: { id: 'BD-test', uids: ['new'] } }]);
  assert.deepEqual(h.detail().printed, before);
  assert.equal(h.run("boardStatusModel(BOARD_DETAIL, 'new', null).scope"), 'new');
  assert.equal(h.run('BOARD_LAYOUT_GRANTED'), false, '安全操作不应授予下一次破坏性修改权限');
});

test('重置或切换范围后，旧打印窗口消息不能恢复已清空纸面', async () => {
  const h = harness({ confirm: true });
  h.run(`const popup = {}; const stale = {boardId: 'BD-test', mode: 'all', layout: null};
    BOARD_WINDOWS.set(popup, stale); BOARD_PRINT_JOBS.delete('BD-test');`);
  const handler = h.handlers['window:message'][0];
  await handler({ source: {}, data: { type: 'omrs-board-printed' } });
  const popup = h.run('Array.from(BOARD_WINDOWS.keys())[0]');
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
  h.run("BOARD_SELECTED_UID = 'old'");
  assert.doesNotMatch(h.run('boardInspectorLayoutHtml()'), /排序或增删题目会先确认/);
  assert.match(h.run('boardInspectorLayoutHtml()'), /增删.*排序.*保留纸面/);
  assert.match(h.run('boardInspectorItemHtml()'), /锁定.*确认.*清空纸面/);
  assert.doesNotMatch(h.run('boardInspectorItemHtml()'), /也不会改纸面记录/);
  h.run('BOARD_DETAIL.printed_summary.new_count = 0');
  assert.doesNotMatch(h.run("boardStatusModel(BOARD_DETAIL, 'all', null).why"), /顺序才需要重印/);
});

const safeChanges = [
  ["boardRemoveItem('new')", '/api/board/items/remove'],
  ["boardRemoveItem('old')", '/api/board/items/remove'],
  ["boardSort('reverse')", '/api/board/update'],
  ["boardPersistItems([])", '/api/board/update'],
  ["boardPersistItems([...BOARD_DETAIL.items, {uid:'third', question_id:'OP-000003'}])", '/api/board/update'],
  ["boardSetItemGap('new', 13)", '/api/board/update'],
  ["boardSetItemGap('old', 2)", '/api/board/update'],
  ["boardApplyPrintField('note_ratio', 50)", null],
  ["boardApplyPrintField('answers', 'append')", '/api/board/update'],
];
for (const [action, url] of safeChanges) test(`不影响纸面无需确认：${action}`, async () => {
  const h = harness();
  await h.run(action);
  await h.run('boardFlushSave()');
  assert.equal(h.confirms.length, 0);
  assert.equal(h.run('BOARD_LAYOUT_GRANTED'), false);
  assert.equal(h.posts.length, url ? 1 : 0);
  if (url) assert.equal(h.posts[0].url, url);
  if (action.includes("'new', 13")) assert.equal(h.posts[0].payload.items[1].gap_lines, 13);
  if (action.includes('reverse')) assert.deepEqual(clone(h.posts[0].payload.items.map(i => i.uid)), ['new', 'old']);
  if (action.includes("boardRemoveItem('old')")) assert.match(h.toasts[0][0], /纸面记录保留其占位/);
});

test('关闭切割线时修改未生效的线标签无需确认', async () => {
  const h = harness();
  h.run("BOARD_DETAIL.print.cut_line = 'none'");
  await h.run("boardApplyPrintField('cut_label', true)");
  await h.run('boardFlushSave()');
  assert.equal(h.confirms.length, 0);
  assert.equal(h.posts[0]?.payload.print.cut_label, true);
});

test('按标记同步先等待本地 items 保存，避免覆盖刚追加的题目', async () => {
  const h = harness();
  h.run(`LABELS = [{name: '重点', archived: false, count: 1}];
    lblChip = () => '';
    getItems = () => [{uid: 'new', labels: ['重点'], suspended: false}];
    uiDialog = async () => ({ok: true, values: {'bd-sync-0': true}});
    BOARD_DIRTY = {items: true};`);
  await h.run('boardSyncLabel()');
  assert.deepEqual(h.posts.map(post => post.url), [
    '/api/board/update', '/api/board/items/add', '/api/board/update',
  ]);
});

test('全局留白只影响未打印题时无需确认', async () => {
  const h = harness();
  h.run('BOARD_DETAIL.items[0].gap_lines = 2');
  await h.run("boardApplyPrintField('gap_lines', 11)");
  await h.run('boardFlushSave()');
  assert.equal(h.confirms.length, 0);
  assert.equal(h.posts[0]?.payload.print.gap_lines, 11);
});

test('没有纸面时锁定不弹破坏性确认', async () => {
  const h = harness({paper: false});
  await h.run("boardApplyPrintField('note_ratio', 42)");
  await h.run('boardFlushSave()');
  assert.equal(h.confirms.length, 0);
  assert.equal(h.posts[0]?.payload.print.note_ratio, .42);
});

for (const action of ["boardApplyPrintField('note_ratio', 42)", "boardSetItemGap('old', 9)",
  "boardApplyPrintField('gap_lines', 9)",
  "boardPersistItems(BOARD_DETAIL.items.map(i => ({...i, gap_lines: 9})))"]) {
  test(`真正影响已印区域取消后零写入：${action}`, async () => {
    const h = harness();
    const before = h.detail();
    await h.run(action);
    await h.run('boardFlushSave()');
    assert.equal(h.confirms.length, 1);
    assert.equal(h.posts.length, 0);
    assert.deepEqual(h.detail(), before);
    assert.equal(h.run('BOARD_DIRTY'), null);
  });
}
