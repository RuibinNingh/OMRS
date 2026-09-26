// 复习调度：Session 所有权（domain/sessions.js，原 tests/test_schedule_sessions.js 的加载与删除用例迁来）与页面纯函数（features/schedule/state.js）。
// 「后开的计划详情不被先发的旧响应覆盖」「删除确认期间重复点击不重复请求、取消后计划保留」在 tests/e2e/schedule.py 里走真实页面。
import test from 'node:test';
import assert from 'node:assert/strict';
import * as D from '../../assets/app/domain/sessions.js';
import * as S from '../../assets/app/features/schedule/state.js';

const json = (body, status = 200) => ({ ok: status < 400, status, headers: { get: () => 'application/json' }, json: async () => body });
function deferredFetch() {
  const calls = [];
  const fetch = (path, init) => new Promise((resolve, reject) => calls.push({ path, init, resolve, reject }));
  return { fetch, calls };
}

test('slow older session response cannot erase the refreshed list; failure keeps the list and reports', async () => {
  D.resetSessions();
  const { fetch, calls } = deferredFetch();
  const events = [];
  D.connectSessions({ emit: (type, list) => events.push([type, list.length]), fetch });
  const older = D.refreshSessions();
  const newer = D.refreshSessions();
  calls[1].resolve(json({ sessions: [{ session_id: 'latest' }] }));
  assert.equal((await newer).ok, true);
  calls[0].reject(new Error('old offline response'));
  assert.equal((await older).stale, true);
  assert.deepEqual(D.listSessions().map(s => s.session_id), ['latest']);
  assert.deepEqual(D.sessionsState(), { loading: false, error: '' });
  const failed = D.refreshSessions();
  assert.equal(D.sessionsState().loading, true);
  calls[2].resolve(json({ msg: '测试离线' }, 503));
  assert.deepEqual(await failed, { ok: false, error: '测试离线' });
  assert.deepEqual(D.listSessions().map(s => s.session_id), ['latest']);
  assert.equal(D.sessionsState().error, '测试离线');
  assert.ok(events.every(e => e[0] === 'sessions'));
});

test('delete: business error keeps the plan; success removes it and invalidates an in-flight load', async () => {
  D.resetSessions();
  const { fetch, calls } = deferredFetch();
  D.connectSessions({ fetch });
  const load = D.refreshSessions();
  calls[0].resolve(json({ sessions: [{ session_id: 'KEEP' }, { session_id: 'GONE' }] }));
  await load;
  const bad = D.deleteSession('KEEP');
  calls[1].resolve(json({ status: 'error', deleted: false }));
  const res = await bad;
  assert.equal(res.ok, false);
  assert.match(res.error, /计划不存在或已删除/);
  assert.equal(JSON.parse(calls[1].init.body).session_id, 'KEEP');
  assert.equal(D.listSessions().length, 2);
  const inflight = D.refreshSessions();
  const good = D.deleteSession('GONE');
  calls[3].resolve(json({ status: 'ok', deleted: true }));
  assert.deepEqual(await good, { ok: true, error: '' });
  calls[2].resolve(json({ sessions: [{ session_id: 'KEEP' }, { session_id: 'GONE' }] }));
  await inflight;
  assert.deepEqual(D.listSessions().map(s => s.session_id), ['KEEP'], '删除前发出的加载作废，不会把删掉的计划带回来');
  const net = D.deleteSession('KEEP');
  calls[4].reject(new Error('down'));
  assert.equal((await net).ok, false);
});

test('fetchSession and progress helpers', async () => {
  D.resetSessions();
  const { fetch, calls } = deferredFetch();
  D.connectSessions({ fetch });
  const got = D.fetchSession('EXP 1');
  assert.equal(calls[0].path, '/api/session?id=EXP%201');
  calls[0].resolve(json({ session_id: 'EXP 1' }));
  assert.equal((await got).data.session_id, 'EXP 1');
  assert.deepEqual(D.sessionUniqueUids({ uids: [' a', 'b', 'a', '', null] }), ['a', 'b']);
  const p = D.sessionProgress({ uids: ['a', 'b', 'c'], feedback_uids: ['b', 'x'] });
  assert.deepEqual([p.total, p.feedback_count, p.pending_count, p.complete], [3, 1, 2, false]);
  assert.equal(D.sessionProgress({ uids: ['a'], feedback_uids: ['a'] }).complete, true);
  assert.equal(D.sessionProgress({}).complete, false);
});

test('views: switching, export remembers where it came from, tab keys', () => {
  let s = { view: 'plans', exportReturn: 'arrange' };
  s = { ...s, ...S.nextView(s, 'export') };
  assert.deepEqual([s.view, s.exportReturn], ['export', 'plans']);
  s = { ...s, ...S.nextView(s, 'export') };
  assert.equal(s.exportReturn, 'plans', '在导出里再点导出不改来处');
  s = { ...s, ...S.nextView(s, 'back') };
  assert.equal(s.view, 'plans');
  assert.equal(S.nextView(s, 'nope').view, 'arrange');
  assert.deepEqual(['home', 'end', 'arrowleft', 'arrowright', 'x'].map(k => S.tabKey('arrange', k)), ['arrange', 'plans', 'plans', 'plans', null]);
  assert.equal(S.tabKey('plans', 'arrowright'), 'arrange');
});

test('plan list, cards, detail model, gap clamp', () => {
  const list = [
    { session_id: 'EXP-1', status: 'active', created_at: '2026-09-25T12:46:38', subject_filter: '数学', uids: ['a', 'b'], feedback_uids: ['a'] },
    { session_id: 'EXP-2', status: 'completed', created_at: '2026-09-24T08:00:00', uids: ['c'], feedback_uids: ['c'] },
    { session_id: 'IMM-3', created_at: '2026-09-23T08:00:00', uids: [] },
  ];
  assert.deepEqual(S.filterPlans(list).map(s => s.session_id), ['EXP-1', 'IMM-3']);
  assert.deepEqual(S.filterPlans(list, 'completed').map(s => s.session_id), ['EXP-2']);
  assert.deepEqual(S.filterPlans(list, 'all', ' exp ').map(s => s.session_id), ['EXP-1', 'EXP-2']);
  assert.equal(S.activeCount(list), 2);
  assert.deepEqual(S.planCard(list[0]), { id: 'EXP-1', when: '2026-09-25 12:46', done: false, status: '待完成', title: '数学 · 2 题', total: 2, recorded: 1 });
  assert.equal(S.planCard(list[2]).title, '多科复习 · 0 题');
  const d = S.detailModel({ session_id: 'EXP-1', created_at: '2026-09-25T12:46:38', status: 'active', count: 3, feedback_count: 1, pending_count: 2, feedback_uids: ['a'],
    items: [{ UID: 'a', Subject: '数学', Category: '函数' }, { uid: 'b', subject: '物理', category: '力学' }, { uid: 'gone', _missing: true }] });
  assert.deepEqual([d.title, d.when, d.hint, d.canFeedback, d.previewable], ['多科复习计划', '2026-09-25 12:46:38', '还有 2 题待录入', true, ['a', 'b']]);
  assert.deepEqual(d.questions.map(q => [q.n, q.uid, q.recorded, q.meta]), [[1, 'a', true, '数学 · 函数'], [2, 'b', false, '物理 · 力学'], [3, 'gone', false, '题目已缺失，无法预览']]);
  const done = S.detailModel({ status: 'completed', pending_count: 0, items: [] });
  assert.deepEqual([done.hint, done.canFeedback, done.status], ['本次复习已全部录入', false, '已完成']);
  assert.deepEqual(['3', '-1', '25', 'x', 2.6].map(S.clampGap), [3, 0, 20, 0, 3]);
});
