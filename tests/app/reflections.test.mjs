import test from 'node:test';
import assert from 'node:assert/strict';
import { ReflectionDraft } from '../../assets/app/domain/question/reflection-state.js';

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
