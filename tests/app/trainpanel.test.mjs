import test from 'node:test';
import assert from 'node:assert/strict';
import { ticks, point, duration, remaining, mergeMetrics, stateLabels } from '../../assets/app/features/trainpanel/state.js';
import { createTrainStore } from '../../assets/app/features/trainpanel/store.js';

test('坐标：零点与右上角，空轴不会除零', () => {
  assert.deepEqual(point(0, 0, 10, 1), [48, 196]);
  assert.deepEqual(point(10, 1, 10, 1), [564, 30]);
  assert.ok(point(0, 0, 0, 0).every(Number.isFinite));
});
test('刻度覆盖从零到最大值，空集也有刻度', () => {
  assert.deepEqual(ticks(2), [0, .5, 1, 1.5, 2]);
  assert.equal(ticks(0).at(-1), 1);
});
test('耗时与预计剩余有明确单位', () => {
  assert.equal(duration(61), '1 分 1 秒');
  assert.equal(duration(3660), '1 小时 1 分');
  assert.equal(remaining({ state: 'running', epoch: 2, epochs: 10, epoch_seconds: 8 }), '1 分 4 秒');
  assert.equal(remaining({ state: 'done' }), '—');
  assert.equal(stateLabels.interrupted, '已中断');
});
test('增量指标按轮次去重，新值替换而不丢旧值', () => {
  assert.deepEqual(mergeMetrics([{ epoch: 1, loss: 3 }], [{ epoch: 2, loss: 2 }, { epoch: 1, loss: 1 }]), [{ epoch: 1, loss: 1 }, { epoch: 2, loss: 2 }]);
});
test('轮次改变时重读实验详情，轮次不变不重复拉取', async () => {
  let epoch = 1, details = 0;
  const api = { async get(path) {
    if (path.endsWith('overview')) return { ok: true, data: { latest: { name: 'r' }, runs: [{ name: 'r', status: { epoch, state: 'running' } }] } };
    if (path.includes('/run?')) { details++; return { ok: true, data: { name: 'r', status: { epoch, state: 'running' }, metrics: [{ epoch }], errors: {} } }; }
    return { ok: true, data: { state: 'online' } };
  } };
  const store = createTrainStore({ api });
  await store.refresh(); await store.refresh();
  assert.equal(details, 1);
  epoch = 2; await store.refresh();
  assert.equal(details, 2); assert.equal(store.state.detail.metrics.length, 2);
});
test('损坏指标保留上次曲线并显示错误', async () => {
  let broken = false;
  const api = { async get(path) {
    if (path.endsWith('overview')) return { ok: true, data: { latest: { name: 'r' }, runs: [{ name: 'r' }] } };
    if (path.includes('/run?')) return { ok: true, data: { name: 'r', status: { epoch: 1 }, metrics: broken ? [] : [{ epoch: 1 }], errors: broken ? { metrics: '读取失败' } : {} } };
    return { ok: true, data: {} };
  } };
  const store = createTrainStore({ api });
  await store.refresh(true); broken = true; await store.refresh(true);
  assert.equal(store.state.detail.metrics.length, 1);
  assert.equal(store.state.detail.errors.metrics, '读取失败');
});

test('快速切换实验时迟到响应不能覆盖最后选择', async () => {
  const pending = new Map();
  const store = createTrainStore({ api: { get(path) { return new Promise(resolve => pending.set(path, resolve)); } } });
  const first = store.select('first'), second = store.select('second');
  pending.get('/api/trainpanel/run?name=second')({ ok: true, data: { name: 'second', metrics: [] } });
  await second;
  pending.get('/api/trainpanel/run?name=first')({ ok: true, data: { name: 'first', metrics: [] } });
  await first;
  assert.equal(store.state.detail.name, 'second');
});

test('状态暂时损坏后仍保留运行中进度并能恢复', async () => {
  let broken = false, epoch = 1;
  const api = { async get(path) {
    const status = { state: 'running', epoch, started_at: '2026-09-29T00:00:00Z' };
    if (path.endsWith('overview')) {
      const run = { name: 'r', status: broken ? null : status, error: broken ? '读取失败' : null };
      return { ok: true, data: { latest: run, runs: [run] } };
    }
    if (path.includes('/run?')) return { ok: true, data: { name: 'r', status: broken ? null : status, metrics: [{ epoch }], errors: broken ? { status: '读取失败' } : {} } };
    return { ok: true, data: {} };
  } };
  const store = createTrainStore({ api });
  await store.refresh(true); broken = true; await store.refresh(true);
  assert.equal(store.state.overview.latest.status.state, 'running');
  assert.equal(store.state.overview.latest.error, '读取失败');
  assert.equal(store.state.detail.status.epoch, 1);
  broken = false; epoch = 2; await store.refresh(true);
  assert.equal(store.state.overview.latest.status.epoch, 2);
  assert.equal(store.state.overview.latest.error, null);
});
