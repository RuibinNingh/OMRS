// core/ 纯逻辑单测：store、bus、router、api、format、html 的 each。node --test tests/*.js tests/app/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { createStore } from '../../assets/app/core/store.js';
import { createBus } from '../../assets/app/core/bus.js';
import { createRouter, parseHash } from '../../assets/app/core/router.js';
import { request, post } from '../../assets/app/core/api.js';
import { formatDate, relativeDays, formatPercent, formatNumber, formatDuration } from '../../assets/app/core/format.js';
import { html, each } from '../../assets/app/core/html.js';
import { normalizeCombo } from '../../assets/app/core/keys.js';

test('store：浅合并、选择器订阅只在选中值变化时回调、batch 只通知一次、退订', () => {
  const store = createStore({ a: 1, b: 1 });
  const seen = [];
  const stop = store.subscribe((v, prev) => seen.push([v, prev]), s => s.a);
  store.set({ b: 2 });
  assert.deepEqual(seen, []);
  store.set({ a: 2 });
  assert.deepEqual(seen, [[2, 1]]);
  let calls = 0;
  store.subscribe(() => { calls += 1; });
  store.batch(() => { store.set({ a: 3 }); store.set({ b: 3 }); });
  assert.equal(calls, 1);
  stop();
  store.set({ a: 9 });
  assert.equal(seen.length, 2);
  const same = store.get();
  store.set(s => s);
  assert.equal(store.get(), same);
});

test('bus：on / once / off / emit，监听出错不影响其余监听', () => {
  const bus = createBus();
  const got = [];
  const off = bus.on('x', v => got.push(`a${v}`));
  bus.once('x', v => got.push(`b${v}`));
  const originalError = console.error;
  console.error = () => {};
  bus.on('x', () => { throw new Error('boom'); });
  bus.emit('x', 1);
  bus.emit('x', 2);
  off();
  bus.emit('x', 3);
  console.error = originalError;
  assert.deepEqual(got, ['a1', 'b1', 'a2']);
});

function fakeWindow(hash = '') {
  const listeners = {};
  const win = {
    location: { hash },
    history: {
      entries: [hash], index: 0,
      pushState(_s, _t, h) { this.entries = this.entries.slice(0, this.index + 1); this.entries.push(h); this.index += 1; win.location.hash = h; },
      replaceState(_s, _t, h) { this.entries[this.index] = h; win.location.hash = h; },
    },
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
    back() { this.history.index -= 1; this.location.hash = this.history.entries[this.history.index]; (listeners.popstate || []).forEach(fn => fn()); },
    navigateHash(h) { this.location.hash = h; (listeners.hashchange || []).forEach(fn => fn()); },
  };
  return win;
}

test('router：parseHash 只认 #/页面', () => {
  assert.deepEqual(parseHash('#/questions'), { id: 'questions', query: '' });
  assert.deepEqual(parseHash('#/board?id=3'), { id: 'board', query: 'id=3' });
  assert.equal(parseHash('#'), null);
  assert.equal(parseHash('#section'), null);
  assert.equal(parseHash(''), null);
});

test('router：start 按地址进入、无效地址改写为 fallback、go 同步切页并写历史、后退回到上一页', () => {
  const win = fakeWindow('#/questions');
  const entered = [];
  const router = createRouter({ win, fallback: 'dashboard', onEnter: (page, prev) => entered.push(`${prev}>${page.id}`) });
  ['dashboard', 'questions', 'board'].forEach(id => router.register({ id }));
  assert.equal(router.start(), 'questions');
  assert.equal(router.current(), 'questions');
  router.go('board');
  assert.equal(win.location.hash, '#/board');
  assert.equal(router.current(), 'board');
  router.go('board');
  assert.deepEqual(entered, ['null>questions', 'questions>board']);
  win.back();
  assert.equal(router.current(), 'questions');
  assert.equal(router.go('nope'), 'dashboard');
  const bad = createRouter({ win: fakeWindow('#/nope'), fallback: 'dashboard' });
  bad.register({ id: 'dashboard' });
  assert.equal(bad.start(), 'dashboard');
});

test('router：地址变成非路由 hash（href="#"）时不切页，并把地址改回当前页', () => {
  const win = fakeWindow('#/board');
  const router = createRouter({ win, fallback: 'dashboard' });
  ['dashboard', 'board'].forEach(id => router.register({ id }));
  router.start();
  win.navigateHash('#');
  assert.equal(router.current(), 'board');
  assert.equal(win.location.hash, '#/board');
  win.navigateHash('#/nope');
  assert.equal(router.current(), 'dashboard');
});

const fakeFetch = (status, payload, type = 'application/json') => async () => ({
  ok: status >= 200 && status < 300, status,
  headers: { get: () => type },
  json: async () => payload, text: async () => String(payload),
});

test('api：成功返回 data；HTTP 错误取服务端 msg；网络失败与超时给统一结构，不抛出', async () => {
  const ok = await request('/api/x', { fetchImpl: fakeFetch(200, { n: 1 }) });
  assert.deepEqual(ok, { ok: true, status: 200, data: { n: 1 }, error: null });
  const bad = await request('/api/x', { fetchImpl: fakeFetch(400, { error: 'bad_input', msg: '题号不对' }) });
  assert.equal(bad.ok, false);
  assert.deepEqual(bad.error, { status: 400, code: 'bad_input', message: '题号不对' });
  const net = await request('/api/x', { fetchImpl: async () => { throw new TypeError('fail'); } });
  assert.deepEqual(net.error, { status: 0, code: 'network', message: '网络连接失败' });
  const slow = await request('/api/x', { timeout: 20, fetchImpl: (_p, init) => new Promise((_r, reject) => init.signal.addEventListener('abort', () => reject(Object.assign(new Error('x'), { name: 'AbortError' })))) });
  assert.equal(slow.error.code, 'timeout');
  let sent = null;
  await post('/api/y', { a: 1 }, { fetchImpl: async (_p, init) => { sent = init; return fakeFetch(200, {})(); } });
  assert.equal(sent.method, 'POST');
  assert.equal(sent.headers['Content-Type'], 'application/json');
  assert.equal(sent.body, '{"a":1}');
});

test('format：日期、相对天数、百分比、数字、时长；空值显示「—」', () => {
  assert.equal(formatDate('2026-09-05'), '2026-09-05');
  assert.equal(formatDate(new Date(2026, 8, 25, 9, 5), 'datetime'), '2026-09-25 09:05');
  assert.equal(formatDate('2026-09-25', 'short'), '9/25');
  assert.equal(formatDate(null), '—');
  assert.equal(formatDate('not a date'), '—');
  const now = new Date(2026, 8, 25, 23, 0);
  assert.equal(relativeDays('2026-09-25', now), '今天');
  assert.equal(relativeDays('2026-09-26', now), '明天');
  assert.equal(relativeDays('2026-09-24', now), '昨天');
  assert.equal(relativeDays('2026-09-28', now), '3 天后');
  assert.equal(relativeDays('2026-09-20', now), '5 天前');
  assert.equal(formatPercent(0.625), '63%');
  assert.equal(formatPercent(62.5, { ratio: false, digits: 1 }), '62.5%');
  assert.equal(formatPercent(null), '—');
  assert.equal(formatNumber(1284), '1,284');
  assert.equal(formatNumber('x'), '—');
  assert.equal(formatDuration(80), '1 分 20 秒');
  assert.equal(formatDuration(3660), '1 小时 1 分');
  assert.equal(formatDuration(5), '5 秒');
});

test('html each：按 key 拼接列表，重复 key 报错', () => {
  const out = each([{ id: 1 }, { id: 2 }], it => it.id, it => html`<li data-key="${it.id}">${it.id}</li>`);
  assert.equal(out.text, '<li data-key="1">1</li><li data-key="2">2</li>');
  assert.throws(() => each([{ id: 1 }, { id: 1 }], it => it.id, () => html``), /重复的 key/);
});

test('keys：组合键规范化', () => {
  assert.equal(normalizeCombo('Ctrl+K'), 'mod+k');
  assert.equal(normalizeCombo('Meta+K'), 'mod+k');
  assert.equal(normalizeCombo('Shift+Tab'), 'shift+tab');
  assert.equal(normalizeCombo('Escape'), 'escape');
  assert.equal(normalizeCombo('?'), '?');
});
