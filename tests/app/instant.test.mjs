// 即时练习的纯逻辑（assets/app/features/instant/state.js）与 domain/items.js 的 facets()：不依赖 DOM 与旧全局。
import test from 'node:test';
import assert from 'node:assert/strict';
import * as S from '../../assets/app/features/instant/state.js';
import { practiceRequestId } from '../../assets/app/features/instant/index.js';
import { facets, practiceFilters } from '../../assets/app/domain/items.js';

const item = (uid, extra = {}) => ({ uid, mastery: 0.2, ...extra });

test('mergeRecommendations：到期在前、熟练度在后，按 uid 去重，截到题数', () => {
  const rows = S.mergeRecommendations({ due: [item('a'), item('b')], proficiency: [item('b'), item('c'), item('d')] }, 3);
  assert.deepEqual(rows.map(r => `${r.uid}:${r._source}`), ['a:due', 'b:due', 'c:proficiency']);
  assert.equal(S.mergeRecommendations({ due: [item('x'), {}, null] }, 10).length, 1);
});

test('buildParams：题数夹在 1–50；科目 / 分类 / 知识点 / 多个标记都进查询串', () => {
  const p = S.buildParams({ count: 99, subject: '数学', category: '', ktag: '三角', labels: ['易错', '必考'] });
  assert.equal(p.get('due_count'), '50');
  assert.equal(p.get('prof_count'), '50');
  assert.equal(p.get('subject'), '数学');
  assert.equal(p.has('category'), false);
  assert.equal(p.get('knowledge_tag'), '三角');
  assert.deepEqual(p.getAll('label'), ['易错', '必考']);
  assert.equal(S.clampCount('abc'), 10);
  assert.equal(S.clampCount(0), 1);
});

test('applyPreset：旧元素 id 作键；先清空科目 / 分类 / 知识点，标记与未给出的题数保留', () => {
  const base = { subject: '物理', category: '力学', ktag: '牛顿', labels: ['易错'], labelMode: 'all', count: 20 };
  assert.deepEqual(S.applyPreset(base, { 'inst-subject': '数学' }), { ...base, subject: '数学', category: '', ktag: '' });
  assert.equal(S.applyPreset(base, { 'inst-count': '5' }).count, 5);
  assert.equal(S.applyPreset(base, { unknown: 'x' }).subject, '');
});

test('判定与打分：判定顺带翻开答案，默认分对 8 错 4；手动打过分不被覆盖；分数夹在 0–10', () => {
  const s = S.createState();
  S.startRound(s, [item('a'), item('b')], new Date(2026, 8, 25, 9, 5, 7));
  assert.equal(s.sessionId, 'IMM-20260925090507');
  assert.equal(s.phase, 'ready');
  S.setVerdict(s, 'a', false);
  assert.deepEqual(s.results.a, { revealed: true, correct: false, score: 4, submitted: false });
  S.setScore(s, 'a', 12.4);
  assert.equal(s.results.a.score, 10);
  S.setVerdict(s, 'a', true);
  assert.equal(s.results.a.score, 10, '已有分数不随判定改');
  S.setScore(s, 'b', 'x');
  assert.equal(s.results.b.score, 5);
});

test('提交：只发已判定未提交的题；提交后锁定，不能改判、不会重复发送；计数分开统计', () => {
  const s = S.createState();
  S.startRound(s, [item('a', { _source: 'due' }), item('b', { _source: 'proficiency' }), item('c')]);
  S.setVerdict(s, 'b', true);
  S.setVerdict(s, 'a', false);
  S.reveal(s, 'c');
  const rows = S.submitRows(s);
  assert.deepEqual(rows.map(r => [r.uid, r.is_correct, r.sub_score, r.source, r.note]),
    [['a', false, 4, 'due', '即时练习'], ['b', true, 8, 'proficiency', '即时练习']]);
  S.markSubmitted(s, rows);
  assert.deepEqual(S.counts(s), { total: 3, judged: 2, submitted: 2, pending: 0 });
  assert.equal(S.setVerdict(s, 'a', true), false);
  assert.equal(s.results.a.correct, false);
  assert.equal(S.setScore(s, 'b', 1), false);
  assert.deepEqual(S.submitRows(s), []);
});

test('练习卡恢复题序和已提交项；部分失败仅锁成功条目', () => {
  const s = S.createState();
  S.startPractice(s, { card: { card_id: 'PC-a', title: '函数巩固' }, attempt_id: 'PA-a', session_id: 'IMM-PA-a',
    items: [item('a', { question_id: 'Q1' }), item('b', { question_id: 'Q2' }), item('c', { question_id: 'Q3' })],
    submitted: ['Q1'], progress: { results: { Q2: { revealed: true, correct: false, score: 4, submitted: false } } }, unavailable: [] });
  assert.deepEqual(s.queue.map(i => i.uid), ['a', 'b', 'c']);
  assert.equal(s.results.a.submitted, true);
  assert.equal(s.results.b.correct, false);
  assert.deepEqual(S.submitRows(s).map(r => r.entry_id), ['Q2']);
  S.markSubmitted(s, [{ uid: 'b', question_id: 'Q2', status: 'error' }]);
  assert.equal(s.results.b.submitted, false);
  S.markSubmitted(s, [{ uid: 'b', question_id: 'Q2', status: 'ok' }]);
  assert.equal(s.results.b.submitted, true);
});

test('非安全上下文只需 getRandomValues，不依赖 randomUUID', () => {
  const id = practiceRequestId({ getRandomValues(bytes) { bytes.fill(7); return bytes; } });
  assert.equal(id, 'PR-' + '07'.repeat(16));
});

test('nextOpenIndex：从下一题起循环找没判定也没提交的题；全做完返回 -1', () => {
  const q = [item('a'), item('b'), item('c')];
  assert.equal(S.nextOpenIndex(q, {}, 0), 1);
  assert.equal(S.nextOpenIndex(q, { b: { correct: true }, c: { submitted: true } }, 0), 0);
  assert.equal(S.nextOpenIndex(q, { a: { correct: true }, b: { correct: false }, c: { correct: true } }, 1), -1);
  const s = S.createState();
  S.startRound(s, []);
  assert.equal(s.phase, 'empty');
});

test('domain/items：facets 去空去重、按中文排序；practiceFilters 固定排除停用、不排序', () => {
  const f = facets([item('a', { subject: '数学', category: '函数', knowledge_tags: ['单调性', '定义域'] }),
    item('b', { subject: '物理', category: '', knowledge_tags: ['定义域'] }), item('c', { subject: '数学' })]);
  assert.deepEqual(f, { subjects: ['数学', '物理'], categories: ['函数'], ktags: ['单调性', '定义域'].sort((x, y) => x.localeCompare(y, 'zh-CN')) });
  const p = practiceFilters({ subject: '数学', labels: ['易错'], labelMode: 'all', ktag: 'k' });
  assert.equal(p.sort, 'none');
  assert.equal(p.suspended, '');
  assert.equal(p.knowledgeTag, 'k');
  assert.deepEqual([p.difficultyMin, p.difficultyMax, p.masteryMin], [0, 10, null]);
});
