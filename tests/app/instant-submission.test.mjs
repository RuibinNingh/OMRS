import test from 'node:test';
import assert from 'node:assert/strict';
import { createInstantController } from '../../assets/app/features/instant/index.js';
import * as S from '../../assets/app/features/instant/state.js';
import { view } from '../../assets/app/features/instant/view.js';

const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { resolve, promise }; };
function setup(t) {
  const state = S.createState(), requests = [];
  S.startRound(state, [{ uid: '练习1', question_id: 'Q1' }, { uid: '练习2', question_id: 'Q2' }]);
  const ctl = createInstantController({}, { store: { get: () => ({ data: { items: [] } }) } }, {
    state, paint() {}, toast() {}, reloadData: async () => {}, invalidateQuestions: async () => {},
    post(path, body) { const reply = deferred(); requests.push({ path, body: structuredClone(body), ...reply }); return reply.promise; },
  });
  t.after(() => ctl.dispose());
  return { state, requests, ctl };
}

test('慢反馈请求期间鼠标及快捷键入口不能改变提交快照，成功后锁定同一判定', async t => {
  const { state, requests, ctl } = setup(t);
  ctl.verdict(false); ctl.score(4);
  const submit = ctl.submit();
  assert.equal(state.submitting, true);
  const html = String(view(state, { facets: { subjects: [], categories: [], ktags: [] }, labels: [], dueDays: () => 0 }));
  assert.match(html, /data-action="instant.verdict"[^>]* disabled/g);
  assert.match(html, /data-input="instant.score"[^>]* disabled/);
  ctl.verdict(true); ctl.score(10); ctl.scoreKey(9);
  assert.equal(state.results['练习1'].correct, false);
  assert.equal(state.results['练习1'].score, 4);
  assert.equal(S.setVerdict(state, '练习2', true), false);
  requests[0].resolve({ ok: true, data: { results: [{ uid: '练习1', question_id: 'Q1', status: 'ok' }] } });
  await submit;
  assert.deepEqual([requests[0].body.feedbacks[0].is_correct, requests[0].body.feedbacks[0].sub_score], [false, 4]);
  assert.deepEqual(state.results['练习1'], { revealed: true, correct: false, score: 4, submitted: true });
  assert.equal(state.submitting, false);
});

test('请求失败解除判定锁；重新修改后重试发送新值', async t => {
  const { state, requests, ctl } = setup(t);
  ctl.verdict(false);
  const first = ctl.submit();
  requests[0].resolve({ ok: false, error: { message: '合成断网' } });
  await first;
  assert.equal(state.submitting, false);
  assert.equal(state.results['练习1'].submitted, false);
  ctl.verdict(true); ctl.score(10);
  const retry = ctl.submit();
  assert.deepEqual([requests[1].body.feedbacks[0].is_correct, requests[1].body.feedbacks[0].sub_score], [true, 10]);
  requests[1].resolve({ ok: true, data: { results: [{ uid: '练习1', question_id: 'Q1', status: 'ok' }] } });
  await retry;
  assert.equal(state.results['练习1'].submitted, true);
});

test('部分成功仅锁成功题，失败题可改判重试；旧轮响应不能锁新轮', async t => {
  const { state, requests, ctl } = setup(t);
  ctl.verdict(false); ctl.go(1); ctl.verdict(true);
  const first = ctl.submit();
  requests[0].resolve({ ok: true, data: { results: [
    { uid: '练习1', question_id: 'Q1', status: 'ok' }, { uid: '练习2', question_id: 'Q2', status: 'error' },
  ] } });
  await first;
  ctl.verdict(false); ctl.score(3);
  assert.equal(state.results['练习1'].submitted, true);
  assert.equal(state.results['练习2'].submitted, false);
  const retry = ctl.submit();
  assert.equal(requests[1].body.feedbacks.length, 1);
  S.startRound(state, [{ uid: '练习2', question_id: 'Q2' }]); ctl.verdict(true);
  requests[1].resolve({ ok: true, data: { results: [{ uid: '练习2', question_id: 'Q2', status: 'ok' }] } });
  await retry;
  assert.equal(state.results['练习2'].submitted, false);
  assert.equal(state.results['练习2'].correct, true);
});
