import test from 'node:test';
import assert from 'node:assert/strict';
import { ensureDetail, cachedDetail, qvInvalidate, qvInvalidateMany, dropDetail, pendingDetailsObject } from '../../assets/app/domain/question/mount.js';

function requests(t) {
  const reads = [];
  t.mock.method(globalThis, 'fetch', async () => new Promise(resolve => {
    reads.push({ reply(question, question_id = 'Q-CACHE') {
      resolve({ ok: true, status: 200, headers: { get: () => 'application/json' }, json: async () => ({ question_id, question }) });
    } });
  }));
  return reads;
}

for (const [name, invalidate] of [['单题失效', uid => qvInvalidate(uid)], ['全量失效', () => qvInvalidateMany()], ['删除详情', uid => dropDetail(uid)]]) {
  test(`${name}隔离旧在途响应；旧清理不会删除新的去重请求`, async t => {
    const uid = `缓存-${name}`, reads = requests(t);
    t.after(() => dropDetail(uid));
    const old = ensureDetail(uid, 'Q-CACHE');
    assert.equal(ensureDetail(uid, 'Q-CACHE'), old);
    await invalidate(uid);
    const fresh = ensureDetail(uid, 'Q-CACHE');
    assert.equal(reads.length, 2);
    reads[0].reply('修改前');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(cachedDetail(uid), null);
    assert.equal(ensureDetail(uid, 'Q-CACHE'), fresh, '旧 finally 不能删除新请求');
    assert.ok(pendingDetailsObject()[`${uid}|Q-CACHE`]);
    reads[1].reply('修改后');
    assert.equal((await old).question, '修改后');
    assert.equal((await fresh).question, '修改后');
    assert.equal(cachedDetail(uid).question, '修改后');
    assert.equal(reads.length, 2);
    assert.equal(pendingDetailsObject()[`${uid}|Q-CACHE`], undefined);
  });
}

test('先返回的新响应不会被迟到的旧响应覆盖', async t => {
  const uid = '缓存-逆序', reads = requests(t);
  t.after(() => dropDetail(uid));
  const old = ensureDetail(uid, 'Q-CACHE');
  await qvInvalidate(uid);
  const fresh = ensureDetail(uid, 'Q-CACHE');
  reads[1].reply('当前正文'); await fresh;
  reads[0].reply('过期正文'); await old;
  assert.equal((await ensureDetail(uid, 'Q-CACHE')).question, '当前正文');
  assert.equal(reads.length, 2);
});
