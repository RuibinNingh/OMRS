import test from 'node:test';
import assert from 'node:assert/strict';
import { ReflectionDraft } from '../../assets/app/domain/question/reflection-state.js';
import { notesWithoutCause } from '../../assets/app/domain/question/notes.js';

function memoryStorage() {
  const data = new Map();
  return { getItem: k => data.get(k), setItem: (k, v) => data.set(k, v) };
}

test('新建和清空后的下一条使用上海业务日期，跨午夜重新取当天', t => {
  t.mock.timers.enable({ apis: ['Date'], now: Date.parse('2026-11-15T16:30:00Z') });
  const draft = new ReflectionDraft('OP-000001', memoryStorage());
  assert.equal(draft.value.occurred_at, '2026-11-16');
  draft.update({ content_md: '补记', occurred_at: '2026-11-01' });
  t.mock.timers.tick(86400000);
  draft.clear();
  assert.equal(draft.value.occurred_at, '2026-11-17');
});

test('明确留空和补记日期重开后保持，旧空表单采用当天而旧草稿保留未知', t => {
  t.mock.timers.enable({ apis: ['Date'], now: Date.parse('2026-11-15T04:00:00Z') });
  const storage = memoryStorage();
  const draft = new ReflectionDraft('OP-000001', storage);
  draft.update({ occurred_at: '' });
  assert.equal(new ReflectionDraft('OP-000001', storage).value.occurred_at, '');
  draft.update({ occurred_at: '2026-10-01', content_md: '补记旧错因' });
  assert.equal(new ReflectionDraft('OP-000001', storage).value.occurred_at, '2026-10-01');
  const legacy = { ...draft.value, content_md: '', occurred_at: '' };
  storage.setItem(draft.key, JSON.stringify({ value: legacy, id: '' }));
  assert.equal(new ReflectionDraft('OP-000001', storage).value.occurred_at, '2026-11-15');
  storage.setItem(draft.key, JSON.stringify({ value: { ...legacy, content_md: '旧未保存草稿' }, id: 'retry' }));
  const restored = new ReflectionDraft('OP-000001', storage);
  assert.equal(restored.value.occurred_at, '');
  assert.equal(restored.payload().request_id, 'retry');
});

test('草稿按稳定身份隔离，失败重试沿用请求编号，修改后换编号', () => {
  const data = new Map();
  const storage = { getItem: k => data.get(k), setItem: (k,v) => data.set(k,v), removeItem: k => data.delete(k) };
  const a = new ReflectionDraft('OP-000001', storage);
  a.update({ content_md: '除负数漏变号' });
  const first = a.payload();
  assert.equal(a.payload().request_id, first.request_id);
  assert.equal(new ReflectionDraft('OP-000001',storage).value.content_md, '除负数漏变号');
  assert.equal(new ReflectionDraft('OP-000002',storage).value.content_md, '');
  a.update({content_md:'乘负数漏变号'});
  assert.notEqual(a.payload().request_id,first.request_id);
  a.clear();
  assert.equal(new ReflectionDraft('OP-000001',storage).value.content_md,'');
});

test('备注去除错因及记录元数据，保留裸备注、关联、代码和其它子节', () => {
  const notes = '普通备注\n\n## 错因\n### 日期未知 · REF-test\n<!-- omrs-reflection {} -->\n> 原因\n\n## 关联\n关联内容\n\n## 补充备注\n```md\n## 错因\n代码原文\n```';
  assert.equal(notesWithoutCause(notes), '普通备注\n\n## 关联\n关联内容\n\n## 补充备注\n```md\n## 错因\n代码原文\n```');
  assert.equal(notesWithoutCause('## 错因\n只有错因'), '');
  assert.equal(notesWithoutCause('## 错因记录\n错因\n## 陌生子节\n保留'), '## 陌生子节\n保留');
});
