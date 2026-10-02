// 展示板保存队列（assets/app/features/board/save.js，P7 第 2 步）：按字段记脏、合并成一次 POST、在途串行化、
// 发送后的新编辑优先、失败保留脏字段。定时器与请求都用替身，不碰网络。
import assert from 'node:assert/strict';
import test from 'node:test';
import { createBoardSaveQueue, boardAdoptSaved } from '../../assets/app/features/board/save.js';

function harness(options = {}) {
  const state = { detail: options.detail === undefined ? { id: 'B1', print: { gap_lines: 2 }, items: [{ uid: 'A', gap_lines: null }], printed_summary: { pages: 0 } } : options.detail };
  const posts = [], adopted = [], failures = [], timers = [];
  let drained = 0, cleared = 0;
  const pending = [];
  const queue = createBoardSaveQueue({
    detail: () => state.detail,
    post: (path, body) => {
      posts.push({ path, body: JSON.parse(JSON.stringify(body)) });
      if (options.manual) return new Promise((resolve, reject) => pending.push({ resolve, reject }));
      if (options.fail) return Promise.reject(new Error('断网'));
      return Promise.resolve({ board: { ...state.detail, saved: posts.length } });
    },
    adopt: (board, info) => { adopted.push({ board, info }); state.detail = board; },
    drained: () => { drained += 1; },
    failed: (error, opts) => failures.push({ message: error.message, opts }),
    setTimer: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimer: () => { cleared += 1; },
  });
  return { state, queue, posts, adopted, failures, timers, pending, drained: () => drained, cleared: () => cleared };
}

test('没有当前板时记脏无效；没有脏字段时 flush 直接成功且不发请求', async () => {
  const h = harness({ detail: null });
  h.queue.mark('items');
  assert.equal(h.queue.dirty(), null);
  assert.equal(await h.queue.flush(), true);
  assert.equal(h.posts.length, 0);
});

test('多次记脏合并成一次 POST，去抖定时器只保留最后一个，清空后通知 drained', async () => {
  const h = harness();
  h.queue.mark('items'); h.queue.mark('print'); h.queue.mark('items');
  assert.deepEqual(h.queue.dirty(), { items: true, print: true });
  assert.equal(h.timers.length, 3);
  assert.ok(h.timers.every(timer => timer.ms === 500));
  assert.ok(h.cleared() >= 3, '每次记脏都先清掉上一个定时器');
  assert.equal(h.queue.busy(), true);
  await h.timers.at(-1).fn();
  assert.equal(h.posts.length, 1);
  assert.equal(h.posts[0].path, '/api/board/update');
  assert.deepEqual(Object.keys(h.posts[0].body).sort(), ['id', 'items', 'print']);
  assert.equal(h.queue.dirty(), null);
  assert.equal(h.queue.busy(), false);
  assert.equal(h.drained(), 1);
  assert.equal(h.adopted[0].info.hadPaper, false);
});

test('在途时新改的字段以本地为准，并在响应后继续保存；并发 flush 串行化', async () => {
  const h = harness({ manual: true });
  h.queue.mark('items');
  const first = h.queue.flush();
  await Promise.resolve();
  assert.equal(h.posts.length, 1);
  h.state.detail = { ...h.state.detail, print: { gap_lines: 9 } };
  h.queue.mark('print');
  const second = h.queue.flush();              // 必须等在途那次
  assert.equal(h.posts.length, 1);
  h.pending.shift().resolve({ board: { id: 'B1', print: { gap_lines: 2 }, items: [], printed_summary: { pages: 0 } } });
  await new Promise(resolve => setTimeout(resolve, 0));
  assert.equal(h.adopted[0].board.print.gap_lines, 9, '发送后又改的 print 不被旧响应覆盖');
  assert.deepEqual(h.adopted[0].board.items, [], '没再改的 items 以服务端为准');
  assert.equal(h.posts.length, 2);
  assert.deepEqual(Object.keys(h.posts[1].body).sort(), ['id', 'print']);
  h.pending.shift().resolve({ board: { ...h.state.detail } });
  assert.equal(await first, true);
  assert.equal(await second, true);
  assert.equal(h.posts.length, 2);
  assert.equal(h.drained() >= 1, true);
});

test('失败时字段放回脏队列（与之后的编辑合并），返回 false，silent 透传给 failed；下次 flush 重试', async () => {
  const h = harness({ fail: true });
  h.queue.mark('items');
  assert.equal(await h.queue.flush({ silent: true }), false);
  assert.deepEqual(h.queue.dirty(), { items: true });
  assert.deepEqual(h.failures, [{ message: '断网', opts: { silent: true } }]);
  assert.equal(h.drained(), 0);
  assert.equal(await h.queue.flush(), false);
  assert.equal(h.posts.length, 2);
});

test('保存期间切到别的板：响应不写回当前板', async () => {
  const h = harness({ manual: true });
  h.queue.mark('items');
  const saving = h.queue.flush();
  await Promise.resolve();
  h.state.detail = { id: 'B2', items: [], print: {} };
  h.pending.shift().resolve({ board: { id: 'B1' } });
  assert.equal(await saving, true);
  assert.equal(h.adopted.length, 0);
});

test('drop 只拿掉指定字段；takePayload 交出载荷并清空队列', () => {
  const h = harness();
  h.queue.mark('items'); h.queue.mark('print');
  h.queue.drop('items');
  assert.deepEqual(h.queue.dirty(), { print: true });
  h.queue.drop('print');
  assert.equal(h.queue.dirty(), null);
  h.queue.drop('print');
  assert.equal(h.queue.takePayload(), null);
  h.queue.mark('print');
  const payload = h.queue.takePayload();
  assert.deepEqual(Object.keys(payload).sort(), ['id', 'print']);
  assert.equal(h.queue.dirty(), null);
});

test('有纸面的板保存后告诉调用方原来有纸面（纸面被服务端清掉时要重绘）', async () => {
  const h = harness({ detail: { id: 'B1', print: {}, items: [], printed_summary: { pages: 2 } } });
  h.queue.mark('print');
  await h.queue.flush();
  assert.equal(h.adopted[0].info.hadPaper, true);
});

test('boardAdoptSaved：只保留 dirty 里列出的本地字段', () => {
  const saved = { id: 'B1', print: { a: 1 }, items: [1], name: '新' };
  const live = { id: 'B1', print: { a: 2 }, items: [2], name: '旧' };
  assert.deepEqual(boardAdoptSaved(saved, live, null), saved);
  assert.deepEqual(boardAdoptSaved(saved, live, { print: true }), { ...saved, print: { a: 2 } });
  assert.deepEqual(boardAdoptSaved(saved, live, { items: true, print: true }), { ...saved, print: { a: 2 }, items: [2] });
});

test('版本冲突保留本地修改，停止后续重试与关页写入，重新读取须主动丢弃', async () => {
  let attempts = 0;
  const board = { id: 'conflict', revision: 1, items: [], print: { gap_lines: 7 } };
  const queue = createBoardSaveQueue({
    detail: () => board, post: async () => { attempts += 1; throw Object.assign(new Error('已变化'), { code: 'revision_conflict', status: 409 }); },
    adopt: () => assert.fail('冲突不得覆盖本地'), setTimer: () => 1, clearTimer: () => {},
  });
  queue.mark('print');
  assert.equal(await queue.flush(), false);
  assert.equal(queue.conflicted(), true);
  assert.deepEqual(queue.dirty(), { print: true });
  queue.mark('items');
  assert.equal(await queue.flush(), false);
  assert.equal(attempts, 1);
  assert.equal(queue.takePayload(), null);
  assert.equal(board.print.gap_lines, 7);
  queue.discard();
  assert.equal(queue.conflicted(), false);
  assert.equal(queue.dirty(), null);
});
