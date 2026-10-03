import test from 'node:test';
import assert from 'node:assert/strict';
import { createDraftNavigation } from '../../assets/app/domain/drafts.js';
import { createBus } from '../../assets/app/core/bus.js';

function harness(request = async () => ({ ok: false })) {
  const bus = createBus();
  const storage = new Map();
  const badge = { hidden: true, textContent: '', setAttribute() {} };
  let page = 'assistant';
  const win = { sessionStorage: { getItem: key => storage.get(key), setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) } };
  const doc = { getElementById: () => badge };
  win.addEventListener = doc.addEventListener = () => {};
  win.removeEventListener = doc.removeEventListener = () => {};
  const router = { current: () => page, go: id => { page = id; return id; } };
  const nav = createDraftNavigation({ bus, router, window: win, document: doc, request });
  return { nav, bus, router, win, badge };
}

test('草稿跳页：目标在挂载前可消费，切页后通知；失败守卫不打开页面', async () => {
  const h = harness();
  let consumed;
  const events = [];
  h.bus.on('drafts:open', p => events.push(p.id));
  h.router.go = () => { consumed = h.nav.consume(); h.router.current = () => 'ai-review'; return 'ai-review'; };
  assert.equal(await h.nav.open('DR-1'), true);
  assert.equal(consumed, 'DR-1');
  assert.deepEqual(events, ['DR-1']);
  assert.equal(h.nav.selected(), 'DR-1');
  const blocked = harness();
  blocked.router.go = async () => 'assistant';
  assert.equal(await blocked.nav.open('DR-2'), false);
  assert.equal(blocked.nav.consume(), null);
  h.nav.dispose(); blocked.nav.dispose();
});

test('草稿计数：首次加载、修改后补拉、失败保留上次成功数值', async () => {
  const responses = [];
  let calls = 0;
  const h = harness(() => { calls += 1; return new Promise(resolve => responses.push(resolve)); });
  const seen = [];
  h.bus.on('drafts:counts', counts => seen.push(counts.review));
  const first = h.nav.refresh();
  const next = h.nav.refresh();
  assert.equal(h.nav.refresh(), next);
  responses.shift()({ ok: true, data: { counts: { cropping: 1, review: 2, done: 3, discarded: 4 } } });
  await first;
  await Promise.resolve();
  assert.equal(calls, 2);
  responses.shift()({ ok: false });
  await next;
  assert.equal(h.badge.textContent, '3');
  assert.equal(h.badge.hidden, false);
  assert.deepEqual(seen, [2]);
  h.nav.dispose();
});

test('草稿选择：刷新会话保留编号，销毁后晚到计数不再更新页面', async () => {
  let resolve;
  const h = harness(() => new Promise(done => { resolve = done; }));
  h.nav.select('DR-3');
  const fresh = createDraftNavigation({ window: h.win });
  assert.equal(fresh.selected(), 'DR-3');
  const loading = h.nav.refresh();
  h.nav.dispose();
  resolve({ ok: true, data: { counts: { cropping: 0, review: 7, done: 0, discarded: 0 } } });
  await loading;
  assert.equal(h.badge.hidden, true);
  fresh.dispose();
});
