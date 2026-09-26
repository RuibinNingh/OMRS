// 复习调度 ·「全题库导出」的纯函数（features/schedule/exporter.js）与 domain/exporting.js 的失败路径。
// 共享筛选就是旧 core.js 的 filterItems（与 arrange.test.mjs 同法载入）。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import * as X from '../../assets/app/features/schedule/exporter.js';
import { requestExport } from '../../assets/app/domain/exporting.js';

if (typeof globalThis.filterItems !== 'function') vm.runInThisContext(fs.readFileSync(new URL('../../assets/core.js', import.meta.url), 'utf8'));
const filterAll = (items, f) => globalThis.filterItems(items, f);
const items = [
  { uid: 'a', subject: '数学', category: '函数', tag: '#状态/待攻克', knowledge_tags: ['单调'], labels: ['易错'], mastery: 0.5, difficulty: 3 },
  { uid: 'b', subject: '物理', category: '力学', tag: '#状态/已击杀', knowledge_tags: [], labels: ['易错', '考前'], mastery: 0.1, difficulty: 8 },
  { uid: 'c', subject: '数学', category: '几何', tag: '#状态/待攻克', mastery: 0.9, difficulty: 5, suspended: true },
];
const uids = f => X.filterExport(items, { ...X.emptyExportFilters(), ...f }, filterAll).map(i => i.uid);

test('export filters follow the shared contract (suspended hidden, mastery ascending by default)', () => {
  assert.deepEqual(uids({}), ['b', 'a']);
  assert.deepEqual(uids({ sort: 'diff-asc' }), ['a', 'b']);
  assert.deepEqual(uids({ subject: '数学' }), ['a']);
  assert.deepEqual(uids({ text: ' 单调 ' }), ['a']);
  assert.deepEqual(uids({ labels: ['易错', '考前'], labelMode: 'all' }), ['b']);
  assert.deepEqual(uids({ masteryMin: '30' }), ['a']);
  assert.deepEqual(uids({ diffMin: '6', diffMax: '9' }), ['b']);
  assert.deepEqual(uids({ tag: '已击杀' }), ['b']);
  const sf = X.sharedExportFilters({ ...X.emptyExportFilters(), masteryMax: '150', diffMax: '' });
  assert.deepEqual([sf.masteryMax, sf.difficultyMin, sf.difficultyMax, sf.suspended], [1, 0, 10, '']);
});

test('selection: toggle keeps order, add / remove filtered, prune vanished uids, summary', () => {
  let sel = X.toggleSelection([], 'a');
  sel = X.toggleSelection(sel, 'b');
  assert.deepEqual(sel, ['a', 'b']);
  assert.deepEqual(X.toggleSelection(sel, 'a'), ['b']);
  assert.deepEqual(X.addFiltered(['b'], [{ uid: 'a' }, { uid: 'b' }, { uid: 'a' }]), ['b', 'a']);
  assert.deepEqual(X.removeFiltered(['a', 'b', 'z'], [{ uid: 'b' }]), ['a', 'z']);
  assert.deepEqual(X.pruneSelection(['z', 'a', 'c'], items), ['a', 'c']);
  assert.equal(X.summary([{}, {}], ['a']), '已筛出 2 题，已选择 1 题。');
});

test('payload: screen always includes answers, gap clamped, A4 columns, session vs uids, file names, status tag', () => {
  assert.deepEqual(X.exportPayload({ uids: ['a'], variant: 'screen', answers: false, gap: 5, twoColumns: false }),
    { format: 'screen', include_answers: true, question_gap_lines: 5, a4_two_columns: true, uids: ['a'] });
  assert.deepEqual(X.exportPayload({ sessionId: 'EXP-1', variant: 'a4', answers: true, gap: 99, twoColumns: false }),
    { format: 'a4', include_answers: true, question_gap_lines: 20, a4_two_columns: false, session_id: 'EXP-1' });
  assert.equal(X.exportPayload({ uids: [], variant: 'a4', gap: '-3', twoColumns: true }).question_gap_lines, 0);
  assert.equal(X.exportFileName({ variant: 'a4' }), 'OMRS-Export-a4.html');
  assert.equal(X.exportFileName({ sessionId: 'EXP-1', variant: 'screen' }), 'OMRS-EXP-1-screen.html');
  assert.deepEqual([X.clampGap('2.9'), X.clampGap('x')], [2, 0]);
  assert.deepEqual(X.statusTag(items[1]), { label: '状态/已击杀', tone: 'success' });
  assert.deepEqual(X.statusTag({}), { label: '', tone: 'danger' });
});

test('domain requestExport: server message on failure, network error, request body', async () => {
  const calls = [];
  const bad = async (path, init) => { calls.push([path, JSON.parse(init.body)]); return { ok: false, json: async () => ({ msg: '题目不存在' }) }; };
  assert.deepEqual(await requestExport({ uids: ['a'], format: 'a4' }, 'x.html', bad), { ok: false, name: '', error: '题目不存在' });
  assert.deepEqual(calls[0], ['/api/export', { uids: ['a'], format: 'a4' }]);
  const plain = async () => ({ ok: false, json: async () => { throw new Error('not json'); } });
  assert.equal((await requestExport({}, 'x', plain)).error, '导出失败');
  const down = async () => { throw new Error('offline'); };
  assert.deepEqual(await requestExport({}, 'x', down), { ok: false, name: '', error: 'offline' });
});
