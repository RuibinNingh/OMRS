// 展示板打印协调（assets/app/features/board/print.js，P7 第 3 步）：待记录任务、纸面记录的校验、
// 独立打印窗口的回传、重置。只测不开窗口、不建 iframe 的路径；开窗与下载由 tests/smoke_board_integrity.py 覆盖。
import assert from 'node:assert/strict';
import test from 'node:test';
import { createBoardPrint } from '../../assets/app/features/board/print.js';

const LAYOUT = { board_id: 'B1', mode: 'all', pages: 2, items: [] };
function harness(options = {}) {
  const log = { posts: [], toasts: [], confirms: [], recorded: [], reset: [], reloads: 0, renders: 0 };
  const state = { detail: 'detail' in options ? options.detail : { id: 'B1', name: '板', printed_summary: { pages: 1, new_count: options.newCount ?? 1 } } };
  const print = createBoardPrint({
    detail: () => state.detail,
    mode: () => options.mode || 'all',
    flush: async () => options.flush ?? true,
    post: async (path, body) => { log.posts.push({ path, body }); return { board: { id: body.id, printed_summary: { count: 3, pages: 2 } } }; },
    reload: async () => { log.reloads += 1; },
    renderStatus: () => { log.renders += 1; },
    toast: (text, opts) => log.toasts.push([text, opts]),
    confirm: async (title, opts) => { log.confirms.push([title, opts]); return options.confirm ?? true; },
    previewLayout: () => options.preview || null,
    recorded: (board, boardId) => log.recorded.push([board.id, boardId]),
    reset: board => log.reset.push(board.id),
  });
  return { print, log, state };
}

test('markAwaiting 没给任务时只借用同板同范围的预览版面（深拷贝），并重绘状态条', () => {
  const same = harness({ preview: { ...LAYOUT } });
  same.print.markAwaiting('all');
  const job = same.print.awaiting();
  assert.deepEqual(job.layout, LAYOUT);
  assert.notEqual(job.layout, LAYOUT);
  assert.equal(same.log.renders, 1);
  const other = harness({ preview: { ...LAYOUT, mode: 'new' } });
  other.print.markAwaiting('all');
  assert.equal(other.print.awaiting().layout, null);
  const none = harness({ detail: null });
  none.print.markAwaiting('all');
  assert.equal(none.print.jobs.size, 0);
});

test('recordPrinted 校验版面归属、范围、任务是否作废与保存结果', async () => {
  const h = harness();
  await assert.rejects(h.print.recordPrinted('B1', 'all', { board_id: 'B2' }), /版面所属展示板不匹配/);
  await assert.rejects(h.print.recordPrinted('B1', 'all', { mode: 'new' }), /版面打印范围不匹配/);
  await assert.rejects(h.print.recordPrinted('B1', 'all', LAYOUT, { boardId: 'B1' }), /任务已失效/);
  const unsaved = harness({ flush: false });
  await assert.rejects(unsaved.print.recordPrinted('B1', 'all', LAYOUT), /设置尚未保存/);
  assert.equal(h.log.posts.length + unsaved.log.posts.length, 0);
});

test('recordPrinted 成功：POST 纸面、清掉待记录、标记任务、交回板并重载', async () => {
  const h = harness();
  h.print.markAwaiting('all', { boardId: 'B1', mode: 'all', layout: LAYOUT });
  const job = h.print.awaiting();
  await h.print.recordPrinted('B1', 'all', LAYOUT, job);
  assert.deepEqual(h.log.posts, [{ path: '/api/board/printed', body: { id: 'B1', mode: 'all', layout: LAYOUT } }]);
  assert.equal(h.print.awaiting(), null);
  assert.equal(job.recorded, true);
  assert.deepEqual(h.log.recorded, [['B1', 'B1']]);
  assert.equal(h.log.reloads, 1);
  assert.match(h.log.toasts.at(-1)[0], /已记录纸面：共 3 题 \/ 2 页/);
});

test('打印窗口回传：陌生窗口与作废任务忽略；版面消息只更新快照；「已打印」确认后记录', async () => {
  const h = harness();
  const popup = {}, job = { boardId: 'B1', mode: 'all', html: '<html>', layout: null };
  h.print.windows.set(popup, job);
  const message = type => ({ source: popup, data: { type, boardId: 'B1', mode: 'all', layout: LAYOUT } });
  await h.print.handleMessage({ source: {}, data: { type: 'omrs-board-printed', boardId: 'B1', mode: 'all', layout: LAYOUT } });
  await h.print.handleMessage(message('omrs-board-printed'));               // 任务不是当前板持有的那份
  assert.equal(h.log.confirms.length, 0);
  h.print.markAwaiting('all', job);
  await h.print.handleMessage(message('omrs-board-layout'));
  assert.deepEqual(job.layout, LAYOUT);
  assert.equal(job.html, null, '拿到实际版面后不再保留 HTML');
  assert.equal(h.log.posts.length, 0);
  await h.print.handleMessage({ source: popup, data: { type: 'omrs-board-printed', boardId: 'B1', mode: 'new', layout: LAYOUT } });
  assert.equal(h.log.confirms.length, 0, '消息的范围与任务不符');
  await h.print.handleMessage(message('omrs-board-printed'));
  assert.equal(h.log.confirms.length, 1);
  assert.equal(h.log.posts.length, 1);
  assert.equal(job.recorded, true);
  assert.equal(job.recording, false);
  await h.print.handleMessage(message('omrs-board-printed'));
  assert.equal(h.log.posts.length, 1, '记录过的任务不再记录');
});

test('markPrinted：取消不写；有任务版面时按任务快照记录，范围取任务的', async () => {
  const cancel = harness({ confirm: false });
  cancel.print.markAwaiting('new', { boardId: 'B1', mode: 'new', layout: { ...LAYOUT, mode: 'new' } });
  await cancel.print.markPrinted();
  assert.equal(cancel.log.posts.length, 0);
  assert.match(cancel.log.confirms[0][0], /新增题目/);
  assert.equal(cancel.print.awaiting().recording, false);
  const h = harness();
  h.print.markAwaiting('new', { boardId: 'B1', mode: 'new', layout: { ...LAYOUT, mode: 'new' } });
  await h.print.markPrinted();
  assert.equal(h.log.posts[0].body.mode, 'new');
  assert.equal(h.print.awaiting(), null);
});

test('resetPrinted：确认后先作废待记录任务，再 POST 重置并交回板', async () => {
  const no = harness({ confirm: false });
  no.print.markAwaiting('all', { boardId: 'B1', mode: 'all' });
  await no.print.resetPrinted();
  assert.equal(no.log.posts.length, 0);
  assert.ok(no.print.awaiting());
  const h = harness();
  h.print.markAwaiting('all', { boardId: 'B1', mode: 'all' });
  await h.print.resetPrinted();
  assert.equal(h.print.awaiting(), null);
  assert.deepEqual(h.log.posts, [{ path: '/api/board/printed/reset', body: { id: 'B1' } }]);
  assert.deepEqual(h.log.reset, ['B1']);
  assert.equal(h.log.toasts.at(-1)[0], '纸面记录已重置');
});

test('exportCurrent 的前置判断：没选板、仅新增却没有新增题', async () => {
  const none = harness({ detail: null });
  await none.print.exportCurrent(false);
  assert.equal(none.log.toasts[0][0], '请先选择一个展示板');
  const empty = harness({ mode: 'new', newCount: 0 });
  await empty.print.exportCurrent(false);
  assert.equal(empty.log.toasts[0][0], '没有新增题目需要打印');
  assert.equal(empty.log.posts.length, 0);
});
