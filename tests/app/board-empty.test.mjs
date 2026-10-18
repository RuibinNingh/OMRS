// 空板预览：有效打印范围、控制器请求归属，以及所有导出入口的前置拦截。
import test from 'node:test';
import assert from 'node:assert/strict';
import { boardExportItems, boardEmptyMessage } from '../../assets/app/features/board/model.js';
import { createBoardDetail } from '../../assets/app/features/board/detail.js';
import { createBoardPrint } from '../../assets/app/features/board/print.js';
import { configureBoards } from '../../assets/app/domain/board/boards.js';
import { stageView, statusView } from '../../assets/app/features/board/state.js';

const item = (id, extra = {}) => ({ uid: id, question_id: id, ...extra });
const board = (id = 'B1', items = [item('Q1')]) => ({ id, items, print: {}, printed_summary: { pages: 0, new_count: items.length } });
const tick = () => new Promise(resolve => setImmediate(resolve));
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function harness(initial = board()) {
  configureBoards({ reset: true, storage: () => null });
  const calls = [], cleared = [];
  const d = createBoardDetail({
    storage: () => null, pageActive: () => true, toast() {},
    setTimer: setTimeout, clearTimer: clearTimeout,
    preview: {
      boardPreviewSetBoard(id, mode) { const request = deferred(); calls.push({ id, mode, ...request }); return request.promise; },
      boardPreviewClear() { cleared.push(true); }, boardPreviewOn() {},
    },
  });
  d.adoptDetail(initial);
  return { d, calls, cleared };
}

test('打印过滤与服务端一致：缺失、停用跳过，仅新增还要排除已印题', () => {
  const b = board('B1', [item('printed', { printed: true }), item('new'), item('missing', { missing: true }), item('off', { suspended: true })]);
  assert.deepEqual(boardExportItems(b).map(x => x.uid), ['printed', 'new']);
  assert.deepEqual(boardExportItems(b, 'new').map(x => x.uid), ['new']);
  assert.deepEqual(boardExportItems(null), []);
});

test('空板和全失效板不请求预览；清掉错误、旧版面与页码，打印按钮不可用', async () => {
  for (const items of [[], [item('lost', { missing: true })], [item('off', { suspended: true })]]) {
    const h = harness();
    h.d.render();
    h.calls[0].reject(new Error('旧板失败'));
    await tick();
    const b = board('empty', items);
    h.d.adoptDetail(b);
    h.d.render();
    assert.equal(h.calls.length, 1);
    assert.equal(h.cleared.length, 1);
    assert.equal(h.d.snapshot().previewError, '');
    const s = stageView(h.d.snapshot(), { layout: { board_id: 'B1', mode: 'all', pages: 8 }, view: { page: 8 } });
    assert.equal(s.emptyMessage, items.length ? '当前没有可打印的题目' : '板里还没有题，添加题目后可预览');
    assert.deepEqual([s.pager.pages, s.pager.multi, s.pager.error], [0, false, '']);
    assert.equal(statusView(h.d.snapshot()).printable, 0);
  }
});

test('最后一道题移除后撤下预览，加题后自动恢复；旧请求失败不能污染空板', async () => {
  const h = harness();
  h.d.render();
  h.d.detail().items = [];
  h.d.render();
  h.calls[0].reject(new Error('已经清空的请求'));
  await tick();
  assert.equal(h.d.snapshot().previewError, '');
  assert.equal(h.cleared.length, 1);
  h.d.detail().items = [item('Q2')];
  h.d.render();
  assert.equal(h.calls.length, 2);
  assert.equal(h.d.snapshot().previewError, '', '重试开始即清掉旧错误');
  h.calls[1].resolve();
  await tick();
  assert.equal(h.d.snapshot().previewError, '');
});

test('重复同步共用在途请求，失败仍能显示并在下一次同步重试', async () => {
  const h = harness();
  h.d.render(); h.d.render();
  assert.equal(h.calls.length, 1);
  h.calls[0].reject(new Error('网络连接失败'));
  await tick();
  assert.equal(h.d.snapshot().previewError, '网络连接失败');
  h.d.render();
  assert.equal(h.calls.length, 2);
  h.calls[1].resolve();
  await tick();
  assert.equal(h.d.snapshot().previewError, '');
});

test('切板后旧成功不能清掉新错误，旧失败也不能覆盖当前请求结果', async () => {
  for (const failed of [true, false]) {
    const h = harness();
    h.d.render();
    h.d.adoptDetail(board('B2'));
    h.d.render();
    h.calls[1].reject(new Error('当前板失败'));
    await tick();
    if (failed) h.calls[0].reject(new Error('旧板失败'));
    else h.calls[0].resolve();
    await tick();
    assert.equal(h.d.snapshot().previewError, '当前板失败');
  }
});

test('切到另一块有题板时，已经显示的旧板错误立即消失', async () => {
  const h = harness();
  h.d.render();
  h.calls[0].reject(new Error('旧板失败'));
  await tick();
  h.d.adoptDetail(board('B2'));
  h.d.render();
  assert.equal(h.d.snapshot().previewError, '');
  h.calls[1].resolve();
});

test('同板强制重试后，旧请求不能覆盖新结果；未保存的内容变化也会使旧回调失效', async () => {
  const h = harness();
  h.d.render();
  h.d.syncPreview({ force: true });
  h.calls[1].resolve();
  h.calls[0].reject(new Error('旧代次失败'));
  await tick();
  assert.equal(h.d.snapshot().previewError, '');
  h.d.syncPreview({ force: true });
  h.d.detail().print.answers = 'append';
  h.calls[2].reject(new Error('旧答案配置失败'));
  await tick();
  assert.equal(h.d.snapshot().previewError, '');
});

test('空内容打印和下载在开窗、保存、网络请求之前停止，保留中文原因', async () => {
  for (const b of [board('empty', []), board('off', [item('off', { suspended: true })]), board('old', [item('old', { printed: true })])]) {
    const mode = b.id === 'old' ? 'new' : 'all';
    const toasts = [];
    const print = createBoardPrint({ detail: () => b, mode: () => mode,
      flush: () => { assert.fail('空内容不应保存或发起导出'); }, toast: message => toasts.push(message) });
    await print.exportCurrent(true);
    await print.exportCurrent(false);
    assert.deepEqual(toasts, [boardEmptyMessage(b, mode), boardEmptyMessage(b, mode)]);
    assert.equal(print.jobs.size, 0);
  }
});
