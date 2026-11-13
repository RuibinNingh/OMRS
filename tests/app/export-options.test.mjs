// 验证参数在刷新、取消、损坏存储和屏幕版切换时保持一致。
import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_EXPORT_OPTIONS, EXPORT_OPTIONS_KEY, normalizeExportOptions, loadExportOptions, saveExportOptions } from '../../assets/app/features/schedule/export-options.js';
import { exportPayload } from '../../assets/app/features/schedule/exporter.js';

test('参数归一化保留明确关闭，限制留白与历史条数', () => {
  assert.deepEqual(normalizeExportOptions(null), DEFAULT_EXPORT_OPTIONS);
  const o = normalizeExportOptions({ historyPosition: 'none', historyLimit: 999, gap: -2, historyDates: false, twoColumns: 'false' });
  assert.equal(o.historyPosition, 'none'); assert.equal(o.historyLimit, 16); assert.equal(o.gap, 0);
  assert.equal(o.historyDates, false); assert.equal(o.twoColumns, true);
  assert.equal(normalizeExportOptions({ historyLimit: '' }).historyLimit, 8);
});

test('成功导出后才保存，读取返回副本；损坏与受限存储不阻止导出', () => {
  const map = new Map();
  globalThis.localStorage = { getItem: key => map.get(key), setItem: (key, value) => map.set(key, value) };
  try {
    const saved = { ...DEFAULT_EXPORT_OPTIONS, gap: 3, historyPosition: 'question' };
    assert.equal(saveExportOptions(saved), true);
    loadExportOptions().gap = 10;
    assert.equal(loadExportOptions().gap, 3);
    assert.equal(JSON.parse(map.get(EXPORT_OPTIONS_KEY)).historyPosition, 'question');
    map.set(EXPORT_OPTIONS_KEY, '{broken');
    assert.equal(loadExportOptions().gap, 3);
    globalThis.localStorage = { getItem() { throw Error('禁止'); }, setItem() { throw Error('禁止'); } };
    assert.equal(saveExportOptions({ ...saved, gap: 4 }), false);
    assert.equal(loadExportOptions().gap, 4);
  } finally { delete globalThis.localStorage; }
});

test('两处导出使用相同历史契约，屏幕版强制答案但保留历史位置', () => {
  const options = { ...DEFAULT_EXPORT_OPTIONS, variant: 'screen', historyPosition: 'question', historyLimit: 12 };
  const plan = exportPayload({ ...options, sessionId: 'EXP-1' });
  const selected = exportPayload({ ...options, question_refs: [{ question_id: 'Q1' }] });
  assert.equal(plan.include_answers, true);
  assert.deepEqual(plan.history, { position: 'question', limit: 12, scores: true, dates: true });
  assert.deepEqual(plan.history, selected.history);
});
