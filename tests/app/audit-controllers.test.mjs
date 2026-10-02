// 审计修复：直接调用真实控制器，故意排列异步完成顺序。
import test from 'node:test';
import assert from 'node:assert/strict';
import { createInstantController } from '../../assets/app/features/instant/index.js';
import * as I from '../../assets/app/features/instant/state.js';
import { createFeedbackController } from '../../assets/app/features/feedback/index.js';
import * as F from '../../assets/app/features/feedback/state.js';
import { createCards } from '../../assets/app/features/create/cards.js';
import { filterPractice } from '../../assets/app/domain/items.js';

const noop = () => {};
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const ctx = { store: { get: () => ({ data: { items: [] } }), subscribe: () => noop }, bus: { on: () => noop, emit: noop }, router: { go: noop } };
globalThis.sessionStorage = { getItem: () => null };
const instantIo = { paint: noop, toast: noop, ensureDetail: async () => null, reloadData: async () => ({ ok: true }), invalidateQuestions: async () => {} };
const practice = id => ({ ok: true, data: { card: { card_id: id }, attempt_id: `PA-${id}`, session_id: `IMM-PA-${id}`, items: [] } });

test('练习卡加载推荐只请求一次，先清除卡片上下文', async () => {
  const state = I.createState(); I.startPractice(state, practice('OLD').data);
  let requests = 0;
  const ctl = createInstantController({}, ctx, { ...instantIo, state, get: async () => { requests++; return { ok: true, data: { due: [], proficiency: [] } }; } });
  await ctl.load();
  assert.equal(requests, 1); assert.equal(state.cardId, ''); assert.equal(state.attemptId, ''); ctl.dispose();
});

test('旧挂载练习请求返回时不会覆盖新卡', async () => {
  const state = I.createState(); const pending = deferred();
  const old = createInstantController({}, ctx, { ...instantIo, state, get: () => pending.promise });
  const loading = old.loadPractice('OLD'); old.dispose();
  const current = createInstantController({}, ctx, { ...instantIo, state, get: async () => practice('NEW') });
  await current.loadPractice('NEW'); pending.resolve(practice('OLD')); await loading;
  assert.equal(state.cardId, 'NEW'); assert.equal(state.attemptId, 'PA-NEW'); current.dispose();
});

test('卡片读取中的统计补拉也是失效边界', async () => {
  const state = I.createState(); const pending = deferred();
  const noData = { ...ctx, store: { get: () => ({}) } };
  const old = createInstantController({}, noData, { ...instantIo, state, get: async () => practice('OLD'), reloadData: () => pending.promise });
  const loading = old.loadPractice('OLD'); await Promise.resolve(); old.dispose();
  I.startPractice(state, practice('NEW').data); pending.resolve({ ok: true }); await loading;
  assert.equal(state.cardId, 'NEW');
});

test('旧轮次提交返回不锁定新轮次同题', async () => {
  const state = I.createState(); I.startRound(state, [{ uid: 'same' }]); I.setVerdict(state, 'same', true);
  const pending = deferred();
  const ctl = createInstantController({}, ctx, { ...instantIo, state, post: () => pending.promise });
  const submitting = ctl.submit(); I.startRound(state, [{ uid: 'same' }]);
  pending.resolve({ ok: true, data: { results: [{ uid: 'same', status: 'ok' }] } }); await submitting;
  assert.equal(state.results.same, undefined); assert.equal(state.submitting, false); ctl.dispose();
});

const feedbackRows = () => [
  { id: 1, uid: 'OK', correct: true, score: 9, note: '成功项' },
  { id: 2, uid: 'FAIL', correct: false, score: 2, note: '人工备注不能丢' },
  { id: 3, uid: 'TODO', correct: null, score: 5, note: '未判定' },
];
const feedbackIo = { paint: noop, toast: noop, openResultsDialog: noop, reloadData: async () => ({ ok: true }), invalidateQuestions: async () => {},
  listSessions: () => [], activeSessionId: () => '', findSession: () => null, domItems: () => [], refreshSessions: async () => ({ ok: true }),
  post: async () => ({ ok: true, data: { results: [{ uid: 'OK', status: 'ok' }, { uid: 'FAIL', status: 'error', msg: '模拟失败' }] } }) };

test('手工反馈保留失败判定、备注和未判定项', async () => {
  const state = F.createState(); state.rows = feedbackRows(); const failed = state.rows[1];
  const ctl = createFeedbackController({}, ctx, { ...feedbackIo, state }); await ctl.submit();
  assert.deepEqual(state.rows.map(r => r.uid), ['FAIL', 'TODO']); assert.equal(state.rows[0], failed); assert.equal(state.status.tone, 'warn'); ctl.dispose();
});

test('Session刷新复用失败行；刷新失败不报告全部完成', async () => {
  for (const refreshed of [true, false]) {
    const state = F.createState(); state.rows = feedbackRows(); const failed = state.rows[1];
    const session = { session_id: 'EXP', uids: ['OK', 'FAIL', 'TODO'], feedback_uids: ['OK'] };
    let afterSubmit = false;
    const ctl = createFeedbackController({}, ctx, { ...feedbackIo, state, activeSessionId: () => 'EXP',
      findSession: () => afterSubmit ? session : { ...session, feedback_uids: [] },
      refreshSessions: async () => { afterSubmit = true; return { ok: refreshed }; } });
    await ctl.submit(); assert.equal(state.rows.find(r => r.uid === 'FAIL'), failed);
    assert.equal(state.rows[0].note, '人工备注不能丢');
    if (!refreshed) assert.match(state.status.text, /刷新失败/); ctl.dispose();
  }
});

test('批量创建期间单卡操作被互斥，重复已创建卡不再请求', async () => {
  const crop = deferred(); const started = deferred(); let requests = 0;
  const item = { id: 'IMG', status: 'ready', revision: 1, reset_epoch: 0, cards: { 1: { subject: '数学', category: '代数' }, 2: { subject: '数学', category: '代数' } },
    regions: [{ id: 'r1', card: 1, role: 'question', convert: 'image' }, { id: 'r2', card: 2, role: 'question', convert: 'text' }] };
  const inbox = { state: { items: [item], stage: 'create', csel: new Set(['IMG#1', 'IMG#2']), loaded: true }, item: () => item, flush: async () => true, load: async () => true };
  const ctl = createCards({ querySelector: () => ({}) }, ctx, { inbox, paint: noop, notify: noop, createCombobox: () => ({ dispose: noop }), reloadData: async () => ({ ok: true }),
    cropDataUrl: async () => { started.resolve(); await crop.promise; return 'image'; },
    post: async (_, payload) => { requests++; item.cards[payload.card].created_uid = `Q-${requests}`; item.revision++; return { ok: true, data: { uid: `Q-${requests}` } }; } });
  const batch = ctl.commitSelected(); await started.promise; assert.equal(await ctl.commit('IMG#2'), null);
  crop.resolve(); await batch; assert.equal(requests, 2);
  const reused = await ctl.commit('IMG#2'); assert.equal(reused.reused, true); assert.equal(requests, 2); ctl.dispose();
});

test('推荐筛选保持真实服务端题序', () => {
  const rows = [{ uid: 'first', mastery: .8, difficulty: 10 }, { uid: 'second', mastery: .2, difficulty: 1 }];
  assert.deepEqual(filterPractice(rows, {}).map(row => row.uid), ['first', 'second']);
});
