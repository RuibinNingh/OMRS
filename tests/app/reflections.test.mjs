import test from 'node:test';
import assert from 'node:assert/strict';
import { ReflectionDraft } from '../../assets/app/domain/question/reflection-state.js';
import { notesWithoutCause } from '../../assets/app/domain/question/notes.js';

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
