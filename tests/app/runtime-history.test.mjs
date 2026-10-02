import test from 'node:test';
import assert from 'node:assert/strict';
import { runtimeController } from '../../assets/app/features/history/runtime-controller.js';

const row = (seq, status = 'success') => ({ seq, status, title: `调用 ${seq}` });
const page = (rows, more = false, total = rows.length) => ({ status: 'ok', records: rows, has_more: more,
  next_before_seq: more ? rows.at(-1).seq : null, keys: [], summary: { total, running: 0 } });

function setup(t) {
  const original = globalThis.fetch, requests = [], options = { q: '' };
  const s = { records: [], details: new Map(), detailErrors: new Map(), selectedSeq: null, summary: {} };
  let paints = 0;
  globalThis.fetch = url => new Promise(resolve => { requests.push({ url, resolve }); });
  const ctl = runtimeController(s, () => { paints++; }, () => ({ ...options }), () => false);
  t.after(() => {
    ctl.dispose();
    for (const request of requests) request.resolve(Response.json({ status: 'ok', detail: row(1) }));
    globalThis.fetch = original;
  });
  const take = (kind = 'records?') => {
    const index = requests.findIndex(request => request.url.includes(kind));
    assert.ok(index >= 0, `待响应请求：${kind}`);
    return requests.splice(index, 1)[0];
  };
  const reply = (request, data, status = 200) => request.resolve(Response.json(data, { status }));
  const load = async data => { const pending = ctl.load(); reply(take(), data); await pending; };
  return { ctl, s, options, take, reply, load, paints: () => paints };
}

test('切换筛选立即使旧响应失效，卸载后迟到响应不改状态或重绘', async t => {
  const h = setup(t), first = h.ctl.load(), old = h.take();
  h.ctl.pause(); h.options.q = '失败';
  const second = h.ctl.load(); h.reply(h.take(), page([row(2, 'failure')])); await second;
  h.reply(old, page([row(1)])); await first;
  assert.equal(h.s.records[0].seq, 2);
  const third = h.ctl.load(), late = h.take();
  h.ctl.dispose(); const paints = h.paints();
  h.reply(late, page([row(3)])); await third;
  assert.equal(h.s.records[0].seq, 2); assert.equal(h.paints(), paints);
});

test('刷新保留已翻页范围和正确游标，后续页失败保留完整旧列表', async t => {
  const h = setup(t);
  await h.load(page([row(4), row(3)], true, 4));
  const more = h.ctl.load(true); h.reply(h.take(), page([row(2), row(1)], false, 4)); await more;
  const refresh = h.ctl.load(); h.reply(h.take(), page([row(5), row(4)], true, 5));
  await new Promise(setImmediate);
  h.reply(h.take(), page([row(3), row(2)], true, 5));
  await new Promise(setImmediate);
  h.reply(h.take(), page([row(1)], false, 5)); await refresh;
  assert.deepEqual(h.s.records.map(r => r.seq), [5, 4, 3, 2, 1]);
  assert.equal(h.s.hasMore, false); assert.equal(h.s.summary.total, 5);
  const failed = h.ctl.load(); h.reply(h.take(), page([row(6), row(5)], true, 6));
  await new Promise(setImmediate);
  h.reply(h.take(), { msg: '分页存储故障' }, 503); await failed;
  assert.deepEqual(h.s.records.map(r => r.seq), [5, 4, 3, 2, 1]);
  assert.equal(h.s.error, '分页存储故障');
  h.ctl.pause(); h.options.q = '新范围';
  await h.load(page([row(7)]));
  assert.deepEqual(h.s.records.map(r => r.seq), [7]); assert.equal(h.s.selectedSeq, 7);
});

test('详情刷新失败保留旧数据，可重试；同条详情的迟到响应不能覆盖新响应', async t => {
  const h = setup(t);
  h.s.records = [row(1)]; h.s.selectedSeq = 1; h.s.details.set('1', row(1));
  const failure = h.ctl.detail(1, true); h.reply(h.take('detail?'), { msg: '暂时离线' }, 503); await failure;
  assert.equal(h.s.details.get('1').title, '调用 1'); assert.equal(h.s.detailErrors.get('1'), '暂时离线');
  h.ctl.select(1); const older = h.take('detail?');
  const retry = h.ctl.detail(1, true), newer = h.take('detail?');
  h.reply(newer, { detail: { ...row(1), title: '最新详情' } }); await retry;
  h.reply(older, { detail: { ...row(1), title: '迟到详情' } }); await new Promise(setImmediate);
  assert.equal(h.s.details.get('1').title, '最新详情'); assert.equal(h.s.detailErrors.size, 0);
});

test('首屏范围之外的关联调用处于进行中时，刷新仍会更新其详情', async t => {
  const h = setup(t);
  h.s.details.set('1', row(1, 'running'));
  h.ctl.select(1, true);
  await h.load(page([row(80)], true, 80));
  const request = h.take('detail?');
  assert.match(request.url, /seq=1$/);
  h.reply(request, { detail: row(1) }); await new Promise(setImmediate);
  assert.equal(h.s.selectedSeq, 1);
  assert.equal(h.s.details.get('1').status, 'success');
});
