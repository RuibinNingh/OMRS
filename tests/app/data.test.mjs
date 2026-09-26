// domain/data.js：统计快照的所有者（P6）——加载、并发合并、失败保留旧快照、旧代码刷新钩子与发布顺序。
import test from 'node:test';
import assert from 'node:assert/strict';
import { connectData, setLegacyRefresh, reloadData, currentData, itemsNow, lastError, loading, resetData } from '../../assets/app/domain/data.js';

const json = (body, status = 200) => ({ ok: status < 400, status, headers: { get: () => 'application/json' }, json: async () => body });
function fakeFetch(responses) {
  const calls = [];
  const fetch = async path => { calls.push(path); const next = responses.shift(); if (next instanceof Error) throw next; return next; };
  return { fetch, calls };
}

test('load publishes after the legacy refresh, with the same snapshot object', async () => {
  resetData();
  const order = [];
  const { fetch, calls } = fakeFetch([json({ total: 2, items: [{ uid: 'a' }, { uid: 'b' }] })]);
  connectData({ emit: (type, payload) => order.push([type, payload]), fetch });
  setLegacyRefresh(async snap => { order.push(['legacy', snap]); });
  const res = await reloadData();
  assert.equal(res.ok, true);
  assert.deepEqual(calls, ['/api/stats']);
  assert.deepEqual(order.map(o => o[0]), ['legacy', 'data']);
  assert.equal(order[0][1], order[1][1]);
  assert.equal(currentData(), res.data);
  assert.deepEqual(itemsNow().map(i => i.uid), ['a', 'b']);
  assert.equal(lastError(), null);
});

test('concurrent calls coalesce: one in flight + one follow-up shared by later callers', async () => {
  resetData();
  const { fetch, calls } = fakeFetch([json({ total: 1, items: [] }), json({ total: 2, items: [] })]);
  const seen = [];
  connectData({ emit: (type, payload) => seen.push(payload.total), fetch });
  const a = reloadData();
  assert.equal(loading(), true);
  const b = reloadData();
  const c = reloadData();
  assert.equal(b, c, '进行中再来的调用共享同一次补拉');
  const [ra, rb] = await Promise.all([a, b, c]);
  assert.deepEqual([ra.data.total, rb.data.total], [1, 2]);
  assert.deepEqual(seen, [1, 2]);
  assert.equal(calls.length, 2);
  assert.equal(loading(), false);
});

test('failure keeps the previous snapshot; first failure gives an empty one; missing items become []', async () => {
  resetData();
  const { fetch } = fakeFetch([json({ msg: '服务重启中' }, 503), json({ total: 3 }), new Error('offline')]);
  connectData({ fetch });
  let res = await reloadData();
  assert.equal(res.ok, false);
  assert.equal(res.error.message, '服务重启中');
  assert.deepEqual([res.data.total, res.data.items], [0, []]);
  res = await reloadData();
  assert.equal(res.ok, true);
  assert.deepEqual(res.data.items, []);
  const kept = res.data;
  res = await reloadData();
  assert.equal(res.ok, false);
  assert.equal(res.error.code, 'network');
  assert.equal(currentData(), kept, '失败时不拿演示数据顶替，保留上一份');
});

test('a throwing legacy refresh is logged, and data is still published', async () => {
  resetData();
  const { fetch } = fakeFetch([json({ total: 5, items: [] })]);
  const seen = [];
  connectData({ emit: type => seen.push(type), fetch });
  setLegacyRefresh(() => { throw new Error('旧代码出错'); });
  const original = console.error;
  const logged = [];
  console.error = (...args) => logged.push(args.join(' '));
  try { await reloadData(); } finally { console.error = original; }
  assert.deepEqual(seen, ['data']);
  assert.equal(logged.length, 1);
});
