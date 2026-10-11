import test from 'node:test';
import assert from 'node:assert/strict';
import { createAssistantHistory } from '../../assets/app/features/assistant/history.js';
import { runFrom } from '../../assets/app/features/assistant/state.js';
import { turnView } from '../../assets/app/features/assistant/view.js';

const events = [
  { type: 'round.start', data: { n: 1 } },
  { type: 'delta', data: { n: 1, kind: 'think', text: '历史思考摘要' } },
  ...Array.from({ length: 1207 }, () => ({ type: 'delta', data: { n: 1, kind: 'text', text: '段' } })),
  { type: 'delta', data: { n: 1, kind: 'text', text: '末尾标记' } },
  { type: 'round.end', data: { n: 1, usage: {} } },
  { type: 'run.end', data: { reason: 'completed' } },
].map((event, i) => ({ ...event, i, t: i }));

function setup(t) {
  const original = globalThis.fetch, requests = [], notes = [];
  const run = runFrom({ id: 'history', status: 'done' }, events.slice(0, 200), { hasMore: true, next: 200 });
  const S = { alive: true, convId: 'conversation', convRequest: 1, items: [{ run }],
    traceClosed: new Set([run.id]), open: new Set(), closed: new Set(), uiVer: 0 };
  let paints = 0;
  globalThis.fetch = url => new Promise(resolve => { requests.push({ url, resolve }); });
  const controller = createAssistantHistory(S, { schedule: () => { paints++; }, notify: text => notes.push(text) });
  t.after(() => {
    S.alive = false;
    for (const request of requests) request.resolve(Response.json({ events: [], has_more: false }));
    globalThis.fetch = original;
  });
  const take = () => {
    assert.ok(requests.length, '存在待响应的运行事件请求');
    return requests.shift();
  };
  const reply = (request, data, status = 200) => request.resolve(Response.json(data, { status }));
  const page = request => {
    const query = new URL(request.url, 'http://test.local').searchParams;
    const after = Number(query.get('after')), limit = Number(query.get('limit'));
    assert.equal(query.get('run'), run.id);
    assert.equal(query.get('wait'), '0');
    assert.ok(limit > 0 && limit <= 500);
    const next = Math.min(events.length, after + limit);
    return { events: events.slice(after, next), next, has_more: next < events.length };
  };
  return { S, run, controller, requests, notes, take, reply, page, paints: () => paints };
}

const advance = () => new Promise(resolve => setImmediate(resolve));

test('一次展开跨越三个后续页，处理过程展开，重复点击不并发，最终回答不漏不重', async t => {
  const h = setup(t), pending = h.controller.loadRunEvents(h.run.id);
  assert.equal(h.run.eventsBusy, true);
  assert.equal(h.S.traceClosed.has(h.run.id), false);
  assert.match(String(turnView(h.S, h.run, 0)), /disabled>正在展开…/);
  await h.controller.loadRunEvents(h.run.id);
  assert.equal(h.requests.length, 1);
  const cursors = [];
  for (let i = 0; i < 3; i++) {
    const request = h.take();
    cursors.push(Number(new URL(request.url, 'http://test.local').searchParams.get('after')));
    h.reply(request, h.page(request));
    await advance();
    if (i < 2) assert.equal(h.run.eventsBusy, true);
  }
  await pending;
  assert.deepEqual(cursors, [200, 700, 1200]);
  assert.equal(h.run.next, events.length);
  assert.equal(h.run.seenEvents.size, events.length);
  assert.equal(h.run.steps.find(step => step.kind === 'text').src, '段'.repeat(1207) + '末尾标记');
  assert.equal(h.run.steps.find(step => step.kind === 'text').live, false);
  assert.equal(h.run.eventsBusy, false);
  assert.equal(h.run.eventsMore, false);
  assert.deepEqual(h.notes, []);
  assert.doesNotMatch(String(turnView(h.S, h.run, 0)), /assistant.loadRunEvents|尚未全部读取/);
});

test('中途失败保留前一页，按钮恢复，从已有游标重试到末页', async t => {
  const h = setup(t), first = h.controller.loadRunEvents(h.run.id), request = h.take();
  h.reply(request, h.page(request));
  await advance();
  h.reply(h.take(), { msg: '网络暂不可用' }, 503);
  await first;
  assert.equal(h.run.next, 700);
  assert.equal(h.run.seenEvents.size, 700);
  assert.equal(h.run.eventsBusy, false);
  assert.equal(h.run.eventsMore, true);
  assert.deepEqual(h.notes, ['网络暂不可用']);
  const markup = String(turnView(h.S, h.run, 0));
  assert.match(markup, />展开完整运行记录</);
  assert.doesNotMatch(markup, /disabled>展开完整运行记录/);
  const retry = h.controller.loadRunEvents(h.run.id);
  for (let i = 0; i < 2; i++) {
    const next = h.take();
    if (!i) assert.match(next.url, /after=700&/);
    h.reply(next, h.page(next));
    await advance();
  }
  await retry;
  assert.equal(h.run.seenEvents.size, events.length);
  assert.equal(h.run.eventsMore, false);
  assert.equal(h.run.steps.find(step => step.kind === 'text').src, '段'.repeat(1207) + '末尾标记');
});

test('切换请求、换对话、替换运行或离页使迟到响应失效并停止续页', async t => {
  const cases = [
    ['发起对话切换', h => { h.S.convRequest++; }],
    ['换到另一个对话', h => { h.S.convId = 'other'; h.S.items = []; }],
    ['重新读取同一运行', h => { h.S.items = [{ run: runFrom({ id: h.run.id }, []) }]; }],
    ['离开助手页', h => { h.S.alive = false; }],
  ];
  for (const [name, invalidate] of cases) await t.test(name, async inner => {
    const h = setup(inner), pending = h.controller.loadRunEvents(h.run.id), request = h.take();
    invalidate(h);
    const paints = h.paints();
    h.reply(request, h.page(request));
    await pending;
    assert.equal(h.run.next, 200);
    assert.equal(h.run.seenEvents.size, 200);
    assert.equal(h.run.eventsBusy, false);
    assert.equal(h.requests.length, 0);
    assert.deepEqual(h.notes, []);
    if (name !== '发起对话切换') assert.equal(h.paints(), paints);
  });
});

test('切换后的迟到失败不向新对话显示错误', async t => {
  const h = setup(t), pending = h.controller.loadRunEvents(h.run.id), request = h.take();
  h.S.convRequest++;
  h.reply(request, { msg: '旧对话错误' }, 500);
  await pending;
  assert.deepEqual(h.notes, []);
  assert.equal(h.requests.length, 0);
});

test('空续页或游标没有前进时停止并可重试，避免无限请求', async t => {
  const cases = [
    { events: [], next: 700, has_more: true },
    { events: events.slice(200, 700), next: 200, has_more: true },
    { events: events.slice(200, 700), has_more: true },
  ];
  for (const data of cases) await t.test(JSON.stringify({ next: data.next, count: data.events.length }), async inner => {
    const h = setup(inner), pending = h.controller.loadRunEvents(h.run.id);
    h.reply(h.take(), data);
    await pending;
    assert.equal(h.requests.length, 0);
    assert.equal(h.run.next, 200);
    assert.equal(h.run.eventsMore, true);
    assert.equal(h.run.eventsBusy, false);
    assert.deepEqual(h.notes, ['运行记录读取未能继续，请重试']);
  });
});

test('空末页正常完成；活动运行交给已有跟随读取', async t => {
  const h = setup(t);
  h.run.following = true;
  await h.controller.loadRunEvents(h.run.id);
  assert.equal(h.requests.length, 0);
  h.run.following = false;
  const pending = h.controller.loadRunEvents(h.run.id);
  h.reply(h.take(), { events: [], next: 200, has_more: false });
  await pending;
  assert.equal(h.run.eventsMore, false);
  assert.equal(h.run.eventsBusy, false);
  assert.deepEqual(h.notes, []);
});
