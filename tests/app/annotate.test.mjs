import test from 'node:test';
import assert from 'node:assert/strict';
import { boxLabels, cleanBox, countRoles, createHistory, dragBox, filterImages, nextTodo, pointIn, stepId, summary, tooSmall, transferBoxes, zoomStep } from '../../assets/app/features/annotate/state.js';
import { createAnnotateStore } from '../../assets/app/features/annotate/store.js';
import { SHORTCUTS, exportHref } from '../../assets/app/features/annotate/view.js';

function fakeTimers() {
  let next = 1;
  const tasks = new Map();
  return {
    setTimeout(fn) { const id = next++; tasks.set(id, fn); return id; },
    clearTimeout(id) { tasks.delete(id); },
    async run() { for (const [id, fn] of [...tasks]) { tasks.delete(id); await fn(); } },
    get size() { return tasks.size; },
  };
}

const img = (id, extra = {}) => ({ id, file: `${id}.png`, width: 100, height: 400, status: 'todo', boxes: [], ...extra });
const box = (role, x, y, w, h) => ({ role, x, y, w, h });

function fakeApi(images) {
  const calls = [];
  return {
    calls,
    async get(path) { calls.push(['get', path]); return { ok: true, data: { images: structuredClone(images) } }; },
    async post(path, body) {
      calls.push(['post', path, structuredClone(body)]);
      if (path === '/api/annotate/save') return { ok: true, data: { image: { id: body.id, status: body.status || 'todo' } } };
      return { ok: true, data: { id: body.id } };
    },
    async upload(files) { calls.push(['upload', files.length]); return { ok: true, data: { images: [img('new')], duplicates: [{ id: 'a' }] } }; },
  };
}

test('dragBox 画框、移动与缩放都夹在 0–1 内', () => {
  const drawn = dragBox('draw', { x: .5, y: .5 }, { x: .2, y: .9 }, null);
  for (const [key, want] of Object.entries({ x: .2, y: .5, w: .3, h: .4 })) assert.ok(Math.abs(drawn[key] - want) < 1e-9, key);
  const moved = dragBox('move', { x: .1, y: .1 }, { x: .9, y: .1 }, box('question', .6, .1, .3, .2));
  assert.equal(moved.x, .7);
  const sized = dragBox('resize', { x: .1, y: .1 }, { x: -.5, y: .1 }, box('question', .2, .2, .3, .3), 'w');
  assert.equal(sized.x, 0);
  assert.ok(Math.abs(sized.w - .5) < 1e-9);
  assert.deepEqual(pointIn(150, 50, { left: 100, top: 0, width: 100, height: 100 }), { x: .5, y: .5 });
  assert.equal(tooSmall(box('question', 0, 0, .01, .5), 400, 800), true);
});

test('沿用上一张：上部框按像素锚定，其余按比例', () => {
  const from = { width: 100, height: 400, boxes: [box('question', .1, .1, .8, .2), box('answer', .1, .5, .8, .4)] };
  const to = { width: 100, height: 800, boxes: [] };
  const out = transferBoxes(from, to);
  assert.equal(out[0].y, .05);
  assert.equal(out[0].h, .1);
  assert.equal(out[1].y, .5);
  assert.equal(out[1].role, 'answer');
});

test('计数、编号、筛选、导航与缩放档位', () => {
  const boxes = [box('question', 0, 0, 1, 1), box('answer', 0, 0, 1, 1), box('question', 0, 0, 1, 1)];
  assert.deepEqual(countRoles(boxes), { question: 2, answer: 1 });
  assert.deepEqual(boxLabels(boxes), ['题目 1', '答案 1', '题目 2']);
  const list = [img('a', { status: 'done' }), img('b'), img('c', { status: 'done' }), img('d')];
  assert.deepEqual(filterImages(list, 'todo').map(i => i.id), ['b', 'd']);
  assert.deepEqual(summary(list), { total: 4, done: 2, todo: 2 });
  assert.equal(stepId(list, 'a', -1), 'a');
  assert.equal(stepId(list, 'b', 1), 'c');
  assert.equal(nextTodo(list, 'b'), 'd');
  assert.equal(nextTodo(list, 'd'), 'b');
  assert.equal(nextTodo([img('x', { status: 'done' })], 'x'), null);
  assert.equal(zoomStep(1, 1), 1.25);
  assert.equal(zoomStep(1, -1), .8);
  assert.equal(zoomStep(3, 1), 3);
  assert.equal(zoomStep(.5, 0), 1);
  assert.deepEqual(cleanBox({ role: 'x', x: 1 / 3, y: 0, w: .5, h: .5 }).role, 'question');
});

test('撤销栈：记录、撤销、重做，新改动清掉重做', () => {
  const h = createHistory();
  h.record('a', []);
  const one = [box('question', 0, 0, .5, .5)];
  assert.deepEqual(h.undo('a', one), []);
  assert.deepEqual(h.redo('a', []), one);
  h.record('a', one);
  assert.equal(h.size('a').future, 0);
  assert.equal(h.undo('b', []), null);
});

test('store：读取后停在第一张未完成，改框去抖保存，Enter 完成并跳下一张', async () => {
  const timers = fakeTimers();
  const api = fakeApi([img('a', { status: 'done', boxes: [box('question', .1, .1, .5, .2)] }), img('b'), img('c')]);
  const notes = [];
  const store = createAnnotateStore({ api, timers, notify: (text, kind) => notes.push([kind, text]) });
  await store.load();
  assert.equal(store.state.cur, 'b');
  store.setBoxes([box('question', .1, .1, .3, .3)]);
  assert.equal(timers.size, 1);
  await timers.run();
  const save = api.calls.find(c => c[1] === '/api/annotate/save');
  assert.deepEqual(save[2], { id: 'b', boxes: [box('question', .1, .1, .3, .3)] });
  assert.equal(store.state.saving, 'idle');
  await store.finish();
  await store.flush();
  assert.equal(store.state.cur, 'c');
  const done = api.calls.filter(c => c[1] === '/api/annotate/save').pop();
  assert.equal(done[2].status, 'done');
  assert.equal(await store.finish(), false, '没有框时 Enter 不完成');
  assert.equal(notes.pop()[0], 'warn');
  assert.equal(await store.finish({ allowEmpty: true }), true);
});

test('store：角色切换改选中框，撤销恢复，沿用上一张，删除选中框', async () => {
  const timers = fakeTimers();
  const api = fakeApi([img('a', { status: 'done', boxes: [box('question', .1, .1, .5, .2)] }), img('b')]);
  const store = createAnnotateStore({ api, timers });
  await store.load();
  assert.equal(store.copyPrevious(), true);
  assert.equal(store.current().boxes.length, 1);
  store.state.sel = 0; store.state.picked = false;   // 刚画完的框：按 A 只切换画框角色
  store.setRole('answer');
  assert.equal(store.current().boxes[0].role, 'question');
  store.setRole('question');
  store.select(0);
  store.setRole('answer');
  assert.equal(store.current().boxes[0].role, 'answer');
  store.undo();
  assert.equal(store.current().boxes[0].role, 'question');
  store.redo();
  assert.equal(store.current().boxes[0].role, 'answer');
  store.select(0);
  assert.equal(store.removeSelected(), true);
  assert.equal(store.current().boxes.length, 0);
  store.fullImage();
  assert.deepEqual(store.current().boxes[0], box('answer', 0, 0, 1, 1));
});

test('store：上传合并新图、删除当前图后停在相邻一张', async () => {
  const timers = fakeTimers();
  const api = fakeApi([img('a'), img('b')]);
  const notes = [];
  const store = createAnnotateStore({ api, timers, notify: (text, kind) => notes.push([kind, text]) });
  await store.load();
  await store.upload([{ name: 'x.png' }]);
  assert.equal(store.state.images.length, 3);
  assert.match(notes.pop()[1], /1 张重复/);
  store.open('b');
  await store.removeImage();
  assert.equal(store.state.cur, 'new');
  assert.deepEqual(store.state.images.map(i => i.id), ['a', 'new']);
});

test('快捷键表与导出链接', () => {
  assert.ok(SHORTCUTS.every(([, rows]) => rows.every(([combos, text]) => combos.length && text)));
  assert.equal(exportHref('yolo'), '/api/annotate/export?format=yolo');
});

test('批量入口：只收图片，按路径自然排序', async () => {
  const { imageFiles, isImage } = await import('../../assets/app/features/annotate/folder.js');
  const f = (name, type = 'image/png', relPath) => ({ name, type, relPath });
  const { files, skipped } = imageFiles([f('shot_10.png'), f('notes.txt', 'text/plain'), f('shot_2.png'), f('b/1.jpg', ''), f('a.gif', 'image/gif', 'a/a.gif')]);
  assert.equal(skipped, 1);
  assert.deepEqual(files.map(x => x.name), ['a.gif', 'b/1.jpg', 'shot_2.png', 'shot_10.png']);
  assert.equal(isImage(f('x.webp', 'image/webp')), false);
});

test('store：上传队列分批串行、边传边并入、只弹一条汇总', async () => {
  const batches = [];
  let n = 0;
  const api = { ...fakeApi([]), async upload(files) { batches.push(files.length); return { ok: true, data: { images: files.map(() => img(`u${n++}`)), duplicates: [] } }; } };
  const notes = [];
  const store = createAnnotateStore({ api, timers: fakeTimers(), notify: (text, kind) => notes.push([kind, text]) });
  await store.load();
  const first = store.upload(Array.from({ length: 10 }, (_, i) => ({ name: `${i}.png` })));
  const second = store.upload([{ name: 'late.png' }]);
  assert.equal(first, second, '传输中追加进同一个队列');
  assert.deepEqual(store.state.uploading, { done: 0, total: 11 });
  await first;
  assert.deepEqual(batches, [8, 3]);
  assert.equal(store.state.images.length, 11);
  assert.equal(store.state.cur, 'u0');
  assert.equal(store.state.uploading, null);
  assert.deepEqual(notes, [['ok', '已上传 11 张']]);
});

test('自动滚动速度：边缘外才滚，越远越快，有上限', async () => {
  const { edgeSpeed } = await import('../../assets/app/features/annotate/canvas.js');
  assert.equal(edgeSpeed(500, 0, 1000), 0);
  assert.ok(edgeSpeed(990, 0, 1000) > 0 && edgeSpeed(10, 0, 1000) < 0);
  assert.ok(edgeSpeed(1100, 0, 1000) > edgeSpeed(990, 0, 1000));
  assert.equal(edgeSpeed(5000, 0, 1000), 90);
});
