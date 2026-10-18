import test from 'node:test';
import assert from 'node:assert/strict';
import { chooseEntryQuality, createEntryFrameMonitor, ENTRY_FALLBACK_KEY, ENTRY_FALLBACK_TTL,
  ENTRY_QUALITY_KEY, readEntryFallback, readEntryQuality, rememberEntryFallback,
  writeEntryQuality } from '../../assets/app/core/entry-quality.js';

test('系统减少动态效果优先，未知设备保守选择轻量，不以高核数直接开启完整档', () => {
  assert.equal(chooseEntryQuality().quality, 'light');
  assert.equal(chooseEntryQuality({ cores: 64, memory: 16 }).quality, 'light');
  assert.equal(chooseEntryQuality({ preference: 'full', reduced: true }).quality, 'static');
  assert.equal(chooseEntryQuality({ preference: 'full', cores: 1, saveData: true }).quality, 'full');
  assert.equal(chooseEntryQuality({ preference: 'bad' }).quality, 'light');
});

test('自动模式使用资源有限和省流量线索，缺失或非法设备信息不误判', () => {
  for (const hints of [{ cores: 2 }, { memory: 2 }, { saveData: true }]) {
    assert.equal(chooseEntryQuality(hints).quality, 'static');
  }
  for (const hints of [{ cores: 0, memory: 0 }, { cores: NaN }, { memory: undefined }]) {
    assert.equal(chooseEntryQuality(hints).quality, 'light');
  }
});

test('自动降级记录限时有效，拒绝未来时间、损坏记录和手动模式污染', () => {
  const at = 1_000_000;
  assert.equal(chooseEntryQuality({ fallback: { at }, now: at + 1 }).quality, 'static');
  assert.equal(chooseEntryQuality({ fallback: { at }, now: at + ENTRY_FALLBACK_TTL }).quality, 'light');
  assert.equal(chooseEntryQuality({ fallback: { at }, now: at - 1 }).quality, 'light');
  assert.equal(chooseEntryQuality({ fallback: { at: 'bad' } }).quality, 'light');
  assert.equal(chooseEntryQuality({ preference: 'light', fallback: { at }, now: at }).quality, 'light');
});

test('手动重新选择清除短期降级记录，浏览器存储损坏或拒绝访问时正常回退', () => {
  const data = new Map();
  const storage = { getItem: key => data.get(key), setItem: (key, value) => data.set(key, value),
    removeItem: key => data.delete(key) };
  rememberEntryFallback(storage, 123);
  assert.deepEqual(readEntryFallback(storage), { at: 123 });
  assert.equal(writeEntryQuality('static', storage), 'static');
  assert.equal(readEntryQuality(storage), 'static');
  assert.equal(data.has(ENTRY_FALLBACK_KEY), false);
  data.set(ENTRY_QUALITY_KEY, 'bad'); data.set(ENTRY_FALLBACK_KEY, '{bad');
  assert.equal(readEntryQuality(storage), 'auto');
  assert.equal(readEntryFallback(storage), null);
  const denied = { getItem() { throw Error('禁止存储'); }, setItem() { throw Error('禁止存储'); } };
  assert.equal(readEntryQuality(denied), 'auto');
  assert.equal(writeEntryQuality('full', denied), 'full');
  assert.doesNotThrow(() => rememberEntryFallback(denied));
});

function sample(monitor, start, end, interval) {
  for (let time = start; time < end; time += interval) monitor.sample(time);
}

test('目标 30 FPS 主动限帧不会降级，持续低帧率经过预热及两窗口只触发一次', () => {
  let count = 0;
  const stable = createEntryFrameMonitor({ onSlow: () => count++ });
  stable.reset(0); sample(stable, 0, 20000, 1000 / 30);
  assert.equal(count, 0);
  const slow = createEntryFrameMonitor({ onSlow: () => count++ });
  slow.reset(0); sample(slow, 0, 7900, 100);
  assert.equal(count, 0);
  sample(slow, 7900, 20000, 100);
  assert.equal(count, 1);
});

test('短时慢帧恢复后不累积，后台和闲置恢复重置采样', () => {
  let count = 0;
  const monitor = createEntryFrameMonitor({ onSlow: () => count++ });
  monitor.reset(0);
  sample(monitor, 0, 5400, 100);
  sample(monitor, 5400, 10000, 1000 / 30);
  monitor.reset(15000);
  sample(monitor, 15000, 18000, 1000 / 30);
  monitor.reset(20000);
  sample(monitor, 20000, 27000, 100);
  assert.equal(count, 0);
});

test('前台极慢渲染仍会降级，不把长帧误当后台恢复', () => {
  let count = 0;
  const monitor = createEntryFrameMonitor({ onSlow: () => count++ });
  monitor.reset(0); sample(monitor, 0, 20000, 2000);
  assert.equal(count, 1);
});

test('浏览器拒绝读取localStorage属性时仍能使用默认档位和本次手动选择', () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, get() { throw Error('禁止存储'); } });
  try {
    assert.equal(readEntryQuality(), 'auto');
    assert.equal(readEntryFallback(), null);
    assert.equal(writeEntryQuality('static'), 'static');
    assert.doesNotThrow(() => rememberEntryFallback());
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor);
    else delete globalThis.localStorage;
  }
});
