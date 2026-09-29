import test from 'node:test';
import assert from 'node:assert/strict';
import { createInboxStore, mergePatch, inboxCounts } from '../../assets/app/features/create/inbox-store.js';
import { readyCards, cardKey, parseKey, cardValue, targetPath, regionKinds, allText, missingRequired, suggestions, commitSummary } from '../../assets/app/features/create/cards-state.js';
import { statsModel, policyForm, policyPayload, exportHref, cleanupSummary, bytes, percent } from '../../assets/app/features/create/train-state.js';
import { cropPlan, previewSize, boxKey, JPEG_PIXELS } from '../../assets/app/features/create/crop.js';
import { detectSummary } from '../../assets/app/features/create/inbox-ops.js';

function fakeTimers() {
  let next = 1;
  const tasks = new Map();
  return {
    setTimeout(fn, ms) { const id = next++; tasks.set(id, { fn, ms, repeat: false }); return id; },
    clearTimeout(id) { tasks.delete(id); },
    setInterval(fn, ms) { const id = next++; tasks.set(id, { fn, ms, repeat: true }); return id; },
    clearInterval(id) { tasks.delete(id); },
    async run() { for (const [id, task] of [...tasks]) { if (!task.repeat) tasks.delete(id); await task.fn(); } },
    get size() { return tasks.size; },
  };
}

function fakeApi(routes) {
  const calls = [];
  const respond = async (method, path, body) => {
    calls.push({ method, path, body });
    const handler = routes[`${method} ${path.split('?')[0]}`];
    return handler ? handler(body, path) : { ok: false, error: { message: `未登记 ${path}` } };
  };
  return { calls, get: path => respond('GET', path), post: (path, body) => respond('POST', path, body) };
}

const item = (id, extra = {}) => ({ id, file: `${id}.png`, width: 100, height: 200, status: 'pending', layout: 'zuoyebang', regions: [], cards: {}, ...extra });

test('保存补丁在防抖期内合并，题卡按编号合并', () => {
  assert.deepEqual(mergePatch({ status: 'ready', cards: { 1: { a: 1 } } }, { cards: { 2: { b: 2 } } }),
    { status: 'ready', cards: { 1: { a: 1 }, 2: { b: 2 } } });
  assert.deepEqual(inboxCounts([item('a'), item('b', { status: 'boxed' }), item('c', { status: 'discarded' }), item('d', { status: 'ready' })]),
    { pending: 1, boxed: 1, ready: 1 });
});

test('saveSoon 去抖合并为一次请求；flush 立即写出；notify 报告失败', async () => {
  const timers = fakeTimers();
  const events = [];
  const notes = [];
  const api = fakeApi({
    'GET /api/inbox/items': () => ({ ok: true, data: { items: [item('a'), item('b')] } }),
    'POST /api/inbox/item/update': body => (body.id === 'b' ? { ok: false, error: { message: '磁盘满' } } : { ok: true, data: { item: { ...item('a'), status: 'boxed', layout: body.layout } } }),
  });
  const store = createInboxStore({ api, timers, emit: type => events.push(type), notify: (text, kind) => notes.push([text, kind]) });
  await store.load();
  const a = store.item('a');
  a.layout = 'photo';
  store.saveSoon(a, { cards: { 1: { subject: '数学' } } });
  store.saveSoon(a, { cards: { 2: { subject: '物理' } } });
  assert.equal(store.unsaved(), 1);
  assert.equal(timers.size, 1);
  await timers.run();
  await store.flush();
  const updates = api.calls.filter(call => call.path === '/api/inbox/item/update');
  assert.equal(updates.length, 1);
  assert.deepEqual(Object.keys(updates[0].body.cards), ['1', '2']);
  assert.equal(updates[0].body.layout, 'photo');
  assert.equal(store.item('a').status, 'boxed');
  store.saveSoon(store.item('b'));
  await store.flush();
  assert.equal(store.unsaved(), 0);
  assert.deepEqual(notes.at(-1), ['保存失败：磁盘满', 'warn']);
  assert.ok(events.includes('inbox:changed'));
});

test('响应晚于新改动时不覆盖本地；拖框期间只同步状态', async () => {
  let release;
  const api = fakeApi({
    'GET /api/inbox/items': () => ({ ok: true, data: { items: [item('a')] } }),
    'POST /api/inbox/item/update': () => new Promise(resolve => { release = () => resolve({ ok: true, data: { item: { ...item('a'), status: 'boxed', regions: [] } } }); }),
  });
  const store = createInboxStore({ api, timers: fakeTimers() });
  await store.load();
  const local = store.item('a');
  const saving = store.save(local);
  await Promise.resolve(); await Promise.resolve();
  local.regions.push({ id: 'r1' });
  store.saveSoon(local);
  release();
  await saving;
  assert.equal(store.item('a'), local, '修订号变了，服务端旧版本不回写');
  store.state.cur = 'a';
  store.state.dragging = true;
  const second = store.save(local);
  await Promise.resolve(); await Promise.resolve();
  release();
  await second;
  assert.equal(store.item('a'), local, '拖动中的图片对象保持不变');
  assert.equal(local.status, 'boxed');
});

test('读取失败清空列表并提示；重载后清掉已不存在的勾选与当前图', async () => {
  let fail = false;
  const notes = [];
  const api = fakeApi({ 'GET /api/inbox/items': () => (fail ? { ok: false, error: { message: '断网' } } : { ok: true, data: { items: [item('a'), item('b', { status: 'discarded' })] } }) });
  const store = createInboxStore({ api, timers: fakeTimers(), notify: text => notes.push(text) });
  store.state.sel.add('a'); store.state.sel.add('b'); store.state.sel.add('gone');
  store.state.cur = 'b';
  await store.load();
  assert.deepEqual([...store.state.sel], ['a']);
  assert.equal(store.state.cur, null);
  fail = true;
  assert.equal(await store.load(), false);
  assert.deepEqual(store.state.items, []);
  assert.equal(notes.at(-1), '读取收件箱失败：断网');
});

test('切换工作区：进处理区默认第一张，离开处理区写出待存改动', async () => {
  const api = fakeApi({
    'GET /api/inbox/items': () => ({ ok: true, data: { items: [item('done', { status: 'done' }), item('a'), item('b')] } }),
    'POST /api/inbox/item/update': body => ({ ok: true, data: { item: item(body.id, { layout: body.layout }) } }),
  });
  const timers = fakeTimers();
  const store = createInboxStore({ api, timers });
  await store.load();
  store.go('process');
  assert.equal(store.state.cur, 'a');
  store.open('b');
  assert.equal(store.state.cur, 'b');
  store.item('b').layout = 'photo';
  store.saveSoon(store.item('b'));
  store.go('upload');
  await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
  assert.equal(api.calls.filter(call => call.path === '/api/inbox/item/update').length, 1);
  assert.equal(store.state.stage, 'upload');
});

test('后台任务轮询到完成调用 onDone；失败项与轮询出错都提示', async () => {
  const timers = fakeTimers();
  const notes = [];
  let polls = 0;
  const api = fakeApi({
    'POST /api/inbox/jobs': body => ({ ok: true, data: { job: { id: `job-${body.type}` } } }),
    'GET /api/inbox/job': (_, path) => {
      polls += 1;
      if (path.includes('broken')) return { ok: false, error: { message: '服务重启' } };
      return polls < 2 ? { ok: true, data: { job: { status: 'running' } } } : { ok: true, data: { job: { status: 'done', errors: [{ msg: '模型超时' }], result: [] } } };
    },
  });
  const store = createInboxStore({ api, timers, notify: (text, kind) => notes.push([text, kind]) });
  const done = [];
  assert.equal(await store.job('detect', { items: [] }, job => done.push(job.status)), 'job-detect');
  assert.equal(store.polling(), 1);
  await timers.run();
  assert.deepEqual(done, []);
  await timers.run();
  assert.deepEqual(done, ['done']);
  assert.equal(store.polling(), 0);
  assert.deepEqual(notes.at(-1), ['detect 有 1 个失败：模型超时', 'warn']);
  await store.job('broken', {});
  await timers.run();
  assert.equal(store.polling(), 0);
  assert.match(notes.at(-1)[0], /读取任务进度或同步结果失败：服务重启/);
  const refused = createInboxStore({ api: fakeApi({}), timers });
  await assert.rejects(refused.job('extract', {}), /未登记/);
});

test('就绪题卡：按题卡分组、补默认表单、跳过已创建', () => {
  const ready = item('img#1', { status: 'ready', regions: [
    { id: 'q2', card: 2, role: 'question', convert: 'text', text: '题二' },
    { id: 'q1', card: 1, role: 'question', convert: 'image' },
    { id: 'a1', card: 1, role: 'answer', convert: 'text', text: '答' },
  ], cards: { 2: { subject: '数学', labels: '错题,易错', created_uid: '' } } });
  const created = item('old', { status: 'ready', regions: [{ id: 'x', card: 1, role: 'question' }], cards: { 1: { created_uid: 'MATH-1' } } });
  const cards = readyCards([item('p'), ready, created]);
  assert.deepEqual(cards.map(card => card.key), ['img#1#1', 'img#1#2']);
  assert.equal(ready.cards['1'].difficulty, 5);
  assert.deepEqual(ready.cards['2'].labels, ['错题', '易错']);
  assert.deepEqual(parseKey(cardKey('img#1', 2)), { id: 'img#1', card: 2 });
  assert.equal(regionKinds(cards[0].regions), '图片 + 文本');
  assert.equal(allText(cards[1].regions), true);
  assert.equal(allText(cards[0].regions), false);
});

test('题卡字段归一、写入路径、必填与汇总文案', () => {
  assert.equal(cardValue('difficulty', '8'), 8);
  assert.equal(cardValue('difficulty', '99'), 10);
  assert.deepEqual(cardValue('tags', '函数， 定义域,函数'), ['函数', '定义域']);
  assert.equal(cardValue('cause', 12), '12');
  assert.equal(targetPath({}), '→ 错题/科目/分类/分类N.md');
  assert.equal(targetPath({ subject: '数学', category: '函数' }), '→ 错题/数学/函数/函数N.md');
  assert.equal(missingRequired({ subject: '数学', category: ' ' }), true);
  assert.equal(commitSummary(3, 1), '已创建 3 道题目，1 张失败；原图与框位已存入数据集');
  assert.deepEqual(suggestions([{ subject: '物理', category: '力', knowledge_tags: ['牛顿'] }, { subject: '数学', category: '函数' }]),
    { subjects: ['数学', '物理'], categories: ['函数', '力'], tags: ['函数', '力', '牛顿'] });
});

test('训练统计模型：百分比、条形比例、盲标与存储文案', () => {
  const model = statsModel({
    images: 4, done: 2, boxes: { total: 6, question: 4, answer: 2, ignore: 0 },
    ai: { adoption_rate: 0.5, suggested: 4, adopted: 2, edited: 1, mean_iou_edited: 0.8, rejected: 1 },
    convert: { agreement_rate: null, judged: 0, agree: 0, text: 3, image: 1 },
    layouts: { photo: 1, zuoyebang: 3 }, blind: {}, storage: { raw_bytes: 3 * 1048576, crops_bytes: 2048, discarded: 1 },
    chat: { images: 2, boxes: 3 },
  });
  assert.deepEqual(model.cards.map(card => card.value), [4, 6, '50%', '—']);
  assert.deepEqual(model.layouts.map(row => [row.label, row.value]), [['作业帮截图', 75], ['拍照 / 扫描', 25]]);
  assert.deepEqual(model.convert.map(row => row.value), [75, 25]);
  assert.match(model.blind, /还没有盲标样本/);
  assert.equal(model.storage, '原图 3.0 MB · 裁图缓存 2 KB · 已丢弃待清理 1 张');
  assert.match(model.chat, /聊天来源图 2 张 · 标注框 3 个/);
  assert.deepEqual(statsModel(null).layouts, []);
  assert.equal(percent(0.333), '33%');
  assert.equal(bytes(0), '0 KB');
});

test('框选策略表单与提交体：默认值、数值夹取、导出与清理文案', () => {
  const form = policyForm({ inbox_detect_provider: 'local_http', inbox_local_detect_url: 'http://x', inbox_blind_every: 3 });
  assert.deepEqual(form, { provider: 'local_http', local: 'http://x', blind: '3', conf: '0', upload: false, days: '7' });
  assert.deepEqual(policyPayload({ provider: 'vlm', local: ' http://y ', blind: '-2', conf: '1.7', upload: true, days: 'abc' }), {
    inbox_detect_provider: 'vlm', inbox_local_detect_url: 'http://y', inbox_blind_every: 0,
    inbox_auto_ready_conf: 1, inbox_auto_on_upload: true, inbox_discard_keep_days: 0,
  });
  assert.equal(exportHref('yolo'), '/api/inbox/dataset/export?format=yolo');
  assert.equal(cleanupSummary({ discarded_days: 7, raw: 2, raw_bytes: 4096, crops: 5 }, true), '已清理：超过 7 天的已丢弃原图 2 张（4 KB），裁图缓存 5 个');
});

test('裁图参数：超大 PNG 改 JPEG 白底，预览只缩不放，框位键反映变化', () => {
  const small = cropPlan({ x: 0.1, y: 0.2, w: 0.5, h: 0.25 }, 1000, 2000);
  assert.deepEqual(small, { sx: 100, sy: 400, width: 500, height: 500, type: 'image/png', quality: 0.92, whiteBackground: false });
  const big = cropPlan({ x: 0, y: 0, w: 1, h: 1 }, 1000, JPEG_PIXELS / 1000 + 10);
  assert.equal(big.type, 'image/jpeg');
  assert.equal(big.whiteBackground, true);
  assert.equal(cropPlan({ x: 0, y: 0, w: 1, h: 1 }, 2000, 2000, 'image/jpeg', 0.85).quality, 0.85);
  assert.deepEqual(previewSize({ x: 0, y: 0, w: 0.5, h: 0.5 }, 400, 400, 340), { sw: 200, sh: 200, width: 200, height: 200 });
  assert.equal(previewSize({ x: 0, y: 0, w: 1, h: 0.5 }, 1040, 400, 520).width, 520);
  assert.notEqual(boxKey({ x: 0.1, y: 0.2, w: 0.3, h: 0.4 }), boxKey({ x: 0.1, y: 0.2, w: 0.3, h: 0.41 }));
});

test('AI 框选汇总：盲标、自动就绪与失败数', () => {
  assert.deepEqual(detectSummary(2, { result: [{ boxes: 2 }, { boxes: 1, blind: true }], errors: [] }),
    { text: '框选完成：2 张，共 3 框，请逐张确认；其中 1 张为盲标（不展示 AI 框，请直接手画）', warn: false });
  const summary = detectSummary(1, { result: [{ boxes: 2, auto: { ready: true } }], errors: [{ msg: '超时' }] });
  assert.equal(summary.warn, true);
  assert.match(summary.text, /1 张已按自动策略转文本并就绪；1 张失败：超时/);
});
