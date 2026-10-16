import test from 'node:test';
import assert from 'node:assert/strict';
import { requestId } from '../../assets/app/core/request-id.js';
import { controlPayload } from '../../assets/app/features/trainpanel/control.js';

test('局域网 HTTP 没有 randomUUID 时仍用 128 位安全随机生成请求标识', () => {
  let calls = 0;
  const crypto = { getRandomValues(bytes) { calls++; bytes.forEach((_, i) => { bytes[i] = i * 17; }); return bytes; } };
  const id = requestId(crypto);
  assert.equal(id, '00112233445566778899aabbccddeeff');
  assert.equal(calls, 1);
  assert.equal(controlPayload({ revision: 1 }, 'start', null, id).request_id, id);
});

test('没有安全随机源时明确失败，不用时间戳或 Math.random 冒充重试身份', () => {
  assert.throws(() => requestId({}), /无法生成请求标识/);
  assert.throws(() => requestId(null), /无法生成请求标识/);
});
