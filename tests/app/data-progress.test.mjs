// 攻克复盘：互斥状态与交叉筛选、累计成绩、完整明细分页及安全渲染。
import test from 'node:test';
import assert from 'node:assert/strict';
import { progressSummary, questionRows, statusOf } from '../../assets/app/features/data/progress.js';
import { questionsView } from '../../assets/app/features/data/questions-view.js';

const items = [
  { uid: 'A', subject: '数学', category: '代数', labels: ['重点'], mastery: 1, is_killed: true, revive_stage: 2, kill_count: 3, attempts: 5, last_review: '2026-11-01' },
  { uid: 'B', subject: '物理', category: '力学', is_killed: true, is_revived: true, revive_stage: 1, kill_count: 1, attempts: 1, last_review: '2026-10-01' },
  { uid: 'C', subject: '数学', category: '几何', is_killed: false, kill_count: 2, attempts: 7, is_leech: true },
  { uid: 'D', subject: '数学', category: '代数', attempts: 0 },
  { uid: 'E', subject: '数学', suspended: true, is_killed: true, is_revived: true, kill_count: 99 },
];

test('击杀成绩保留降级题历史，停用题排除，档位之和等于当前已击杀题数', () => {
  const s = progressSummary(items);
  assert.deepEqual([s.dormant, s.revived, s.killCount, s.everKilled], [1, 1, 6, 3]);
  assert.deepEqual(s.stages.map(row => [row.value, row.pct]), [[1, 50], [1, 50], [0, 0], [0, 0], [0, 0]]);
  assert.equal(progressSummary().killCount, 0);
  assert.ok(progressSummary().stages.every(row => row.pct === 0));
});

test('已击杀兼容旧快照；复燃是击杀子集，不凭衰减熟练度推断', () => {
  const legacy = [{ uid: 'X', mastery: 1, decayed_mastery: 0.1 }, { uid: 'Y', tag: '#状态/已击杀', mastery: 0.9, is_revived: true }];
  assert.equal(questionRows(legacy).total, 2);
  assert.deepEqual(progressSummary(legacy).stages.map(row => row.value), [2, 0, 0, 0, 0]);
  assert.equal(statusOf(legacy[0]).label, '已击杀 · 休眠中');
  assert.equal(statusOf(legacy[1]).label, '复燃待复核');
  assert.equal(statusOf(items[2]).label, '待攻克');
  assert.equal(statusOf(items[3]).label, '待攻克 · 未复习');
});

test('状态筛选可交叉科目与搜索；计数说明重叠且不含停用题', () => {
  assert.deepEqual(questionRows(items).uids, ['B', 'A'], '待复核优先，即使上次复习更早');
  assert.deepEqual(questionRows(items).counts.map(row => row.count), [4, 2, 1, 1, 2, 1, 1]);
  assert.deepEqual(questionRows(items, { subject: '数学', query: '重点' }).uids, ['A']);
  assert.equal(questionRows(items, { subject: '数学', filter: 'revived' }).total, 0);
  assert.deepEqual(questionRows(items, { filter: 'attacking' }).uids.sort(), ['C', 'D']);
  assert.deepEqual(questionRows(items, { filter: 'never' }).uids, ['D']);
  assert.deepEqual(questionRows(items, { filter: 'leech', query: 'c' }).uids, ['C']);
  assert.deepEqual(questionRows(items, { filter: 'all', query: '代数' }).uids.sort(), ['A', 'D']);
  assert.deepEqual(questionRows(items).subjects, ['数学', '物理']);
});

test('匹配全集先过滤再分页，不丢失第 20 题以后的击杀记录，空页夹紧', () => {
  const many = Array.from({ length: 31 }, (_, i) => ({ ...items[0], uid: `Q${String(i).padStart(2, '0')}` }));
  const p = questionRows(many, { page: 3 });
  assert.deepEqual([p.rows.length, p.uids.length, p.total, p.page, p.pages], [10, 31, 31, 3, 4]);
  assert.equal(p.rows[0].uid, 'Q20');
  assert.equal(questionRows(many, { page: 99 }).rows[0].uid, 'Q30');
  assert.equal(questionRows(many, { query: '不存在', page: 4 }).page, 1);
  assert.equal(questionRows([], { page: -1 }).pages, 1);
});

test('明细转义用户文字，并展示逐题成绩、实际排期和复核档位', () => {
  const s = { filter: 'killed', subject: '', query: '\"><img src=x onerror=alert(1)>' };
  const list = questionRows([{ ...items[0], due_date: '2026-11-20', category: '<script>test</script>' }]);
  const text = questionsView(s, list).text;
  assert.ok(!text.includes('<img src=x') && !text.includes('<script>'));
  assert.match(text, /2026-11-20/);
  assert.match(text, /复核第 2 档/);
  assert.match(text, /3 次/);
  assert.match(text, /data-action="data.detail"/);
});
