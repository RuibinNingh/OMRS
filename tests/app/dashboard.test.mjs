// 仪表盘纯函数：行动推荐规则（原 tests/smoke_frontend_actions_catalog.js 场景 1–3 与 tests/test_question_suspend_frontend.js 的行动计划断言迁来）、
// 「今天」卡、概览、30 天热力、最薄弱科目、展开 / 收起。
import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPlan, activeItems, todayTarget, daysSince, weakestGroup, recentReviewCount, daysSinceLastReview, dayKey, LEVELS } from '../../assets/app/features/dashboard/plan.js';
import { todaySummary, kpis, heatmap, weakSubjects, visiblePlan, dateStamp } from '../../assets/app/features/dashboard/state.js';

const TODAY = new Date(2026, 8, 25);
const ago = n => dayKey(new Date(2026, 8, 25 - n));
// 到期天数：due_date 相对 TODAY（与旧 getDueDays 同口径：未来为正、逾期为负）
const dueDays = item => (item.due_date ? Math.round((new Date(`${item.due_date}T00:00`) - TODAY) / 864e5) : null);
const item = over => ({ uid: 'X1', subject: '数学', category: '甲', difficulty: 5, mastery: 0.5, decayed_mastery: 0.45, attempts: 2,
  last_review: ago(3), due_date: dayKey(new Date(2026, 8, 35)), tag: '#状态/待攻克', is_leech: false, ...over });
const env = over => ({ items: [], data: {}, sessions: [], dueDays, today: TODAY, ...over });

test('dueDays helper matches legacy sign convention', () => {
  assert.equal(dueDays(item({ due_date: ago(9) })), -9);
  assert.equal(dueDays(item({ due_date: ago(0) })), 0);
  assert.equal(dueDays(item({ due_date: dayKey(new Date(2026, 8, 28)) })), 3);
  assert.equal(dueDays({}), null);
});

test('scenario 1: empty library gives a single "go create" suggestion', () => {
  const plan = buildPlan(env({}));
  assert.equal(plan.length, 1);
  assert.equal(plan[0].key, 'empty');
  assert.deepEqual(plan[0].actions[0], { label: '去录入题目', primary: true, go: 'page', page: 'create' });
});

test('scenario 2: backlog — overdue, due today, leech, pending session; urgent first', () => {
  const plan = buildPlan(env({
    data: { daily_trend: { [ago(1)]: 4 } },
    items: [
      item({ uid: 'A1', due_date: ago(9), mastery: 0.2, decayed_mastery: 0.15 }),
      item({ uid: 'A2', due_date: ago(2), mastery: 0.3, decayed_mastery: 0.25 }),
      item({ uid: 'B1', due_date: ago(0), mastery: 0.4, decayed_mastery: 0.35 }),
      item({ uid: 'C1', is_leech: true, mastery: 0.1, decayed_mastery: 0.08 }),
      item({ uid: 'D1', mastery: 1, tag: '#状态/已击杀', due_date: ago(5) }),
    ],
    sessions: [{ session_id: 'EXP-1', status: 'active', count: 6 }, { session_id: 'EXP-0', status: 'done', count: 3 }],
  }));
  const keys = plan.map(r => r.key);
  for (const key of ['overdue', 'due_today', 'leech', 'pending_feedback']) assert.ok(keys.includes(key), key);
  assert.ok(!keys.includes('all_good'));
  assert.equal(plan[0].level, 'urgent');
  const overdue = plan.find(r => r.key === 'overdue');
  assert.equal(overdue.metric, '2', '逾期计数不含已击杀题');
  assert.match(overdue.detail, /9 天/);
  assert.deepEqual(overdue.actions[1], { label: '在题库查看', go: 'questions', preset: { 'q-filter-due': 'overdue', 'q-sort': 'due-asc' } });
  const fb = plan.find(r => r.key === 'pending_feedback');
  assert.equal(fb.metric, '1');
  assert.deepEqual(fb.actions[0], { label: '去录反馈', primary: true, go: 'feedback', session: 'EXP-1' });
  assert.equal(plan.find(r => r.key === 'due_today').actions[0].go, 'review');
  const ranks = plan.map(r => LEVELS[r.level].rank);
  assert.deepEqual(ranks, [...ranks].sort((a, b) => a - b));
});

test('scenario 3: nothing pending → all_good first, no urgent', () => {
  const plan = buildPlan(env({
    data: { daily_trend: { [dayKey(TODAY)]: 6 } },
    items: [
      item({ uid: 'E1', due_date: dayKey(new Date(2026, 8, 31)), mastery: 0.9, decayed_mastery: 0.88, attempts: 5, last_review: ago(1) }),
      item({ uid: 'E2', due_date: dayKey(new Date(2026, 9, 4)), mastery: 0.85, decayed_mastery: 0.8, attempts: 4, last_review: ago(1) }),
    ],
  }));
  assert.equal(plan[0].key, 'all_good');
  assert.equal(plan[0].metric, '6');
  assert.ok(!plan.some(r => r.level === 'urgent'));
});

test('suspended questions never enter the plan (active items, leech)', () => {
  assert.deepEqual(activeItems([{ uid: 'active', mastery: 0.2 }, { uid: 'paused', mastery: 0.2, suspended: true }]).map(i => i.uid), ['active']);
  const plan = buildPlan(env({ items: [item({ uid: 'paused', suspended: true, is_leech: true })] }));
  assert.ok(!plan.some(r => r.key === 'leech'));
});

test('untouched / cold / idle / never / low_not_due / weak subject & category rules', () => {
  const many = n => Array.from({ length: n }, (_, i) => i);
  let plan = buildPlan(env({ items: many(3).map(i => item({ uid: `U${i}`, attempts: 0, last_review: ago(40) })), data: { daily_trend: { [ago(8)]: 2 } } }));
  let keys = plan.map(r => r.key);
  assert.ok(keys.includes('untouched') && keys.includes('cold'));
  const idle = plan.find(r => r.key === 'idle');
  assert.equal(idle.level, 'warn');
  assert.equal(idle.metric, '8天');
  assert.deepEqual(idle.actions[0].preset, { 'inst-count': '5' });
  plan = buildPlan(env({ items: [item({})] }));
  assert.ok(plan.some(r => r.key === 'never'));
  plan = buildPlan(env({ data: { daily_trend: { [ago(4)]: 1 } }, items: many(3).map(i => item({ uid: `L${i}`, decayed_mastery: 0.3 })) }));
  keys = plan.map(r => r.key);
  assert.ok(keys.includes('low_not_due'));
  assert.equal(plan.find(r => r.key === 'idle').level, 'info');
  const mixed = [...many(3).map(i => item({ uid: `M${i}`, subject: '数学', category: '甲', decayed_mastery: 0.2 })),
    ...many(3).map(i => item({ uid: `P${i}`, subject: '物理', category: '乙', decayed_mastery: 0.9 }))];
  plan = buildPlan(env({ items: mixed, data: { daily_trend: { [dayKey(TODAY)]: 1 } } }));
  const weak = plan.find(r => r.key === 'weak_subject');
  assert.equal(weak.metric, '20%');
  assert.deepEqual(weak.actions.map(a => a.go), ['instant', 'questions']);
  assert.deepEqual(plan.find(r => r.key === 'weak_category').actions[0].preset, { 'inst-category': '甲' });
  assert.equal(weakestGroup(mixed.slice(0, 3), 'subject', 3), null, '只有一组时不算最薄弱');
});

test('date helpers: daysSince, recentReviewCount, daysSinceLastReview, todayTarget', () => {
  assert.equal(daysSince('2026/09/20', TODAY), 5);
  assert.equal(daysSince('bad', TODAY, 7), 7);
  assert.equal(daysSince('2026-02-30', TODAY, 7), 7);
  assert.equal(daysSince(dayKey(new Date(2026, 9, 1)), TODAY), 0);
  assert.equal(recentReviewCount({ [ago(0)]: 2, [ago(6)]: 3, [ago(7)]: 9 }, TODAY, 7), 5);
  assert.equal(daysSinceLastReview({}, TODAY), null);
  assert.equal(daysSinceLastReview({ [ago(2)]: 1, [ago(9)]: 3, [ago(1)]: 0 }, TODAY), 2);
  const items = [...Array.from({ length: 25 }, (_, i) => item({ uid: `D${i}`, due_date: ago(1) })), item({ uid: 'L1', is_leech: true }), item({ uid: 'L2', is_leech: true })];
  assert.equal(todayTarget({ items: items.slice(0, 3), dueDays }), 3);
  assert.equal(todayTarget({ items: [items[0], items[25], items[26]], dueDays }), 3);
  assert.equal(todayTarget({ items, dueDays }), 20);
});

test('todaySummary: levels, splits, actions, progress', () => {
  let t = todaySummary(env({}));
  assert.equal(t.empty, true);
  assert.equal(t.actions[0].page, 'create');
  assert.equal(t.stamp, '9 月 25 日 · 星期五');
  t = todaySummary(env({ items: [item({ due_date: ago(3) }), item({ uid: 'B', due_date: ago(0) })], data: { daily_trend: { [dayKey(TODAY)]: 1 } } }));
  assert.equal(t.level, 'overdue');
  assert.equal(t.waiting, 2);
  assert.deepEqual(t.splits.map(s => s.tone), ['danger', 'warning']);
  assert.deepEqual(t.actions.map(a => a.go), ['review', 'questions']);
  assert.match(t.note, /3 天/);
  assert.equal(t.pct, 50);
  t = todaySummary(env({ items: [item({})], sessions: [{ status: 'active', pending_count: 4 }] }));
  assert.equal(t.level, 'clear');
  assert.deepEqual(t.splits, [{ tone: 'info', label: '未录反馈 4' }]);
  assert.deepEqual(t.actions.map(a => a.label), ['随便练几题', '去录反馈']);
  t = todaySummary(env({ items: [item({})] }));
  assert.deepEqual(t.splits, [{ tone: 'success', label: '没有到期的题' }]);
  assert.equal(t.pct, 0);
  assert.equal(dateStamp(new Date(2026, 0, 4)), '1 月 4 日 · 星期日');
});

test('kpis, heatmap, weakSubjects, visiblePlan', () => {
  const k = kpis({ total: 40, killed: 10, attacking: 30, avg_mastery: 0.164, suspended: 2 });
  assert.deepEqual(k.map(r => r.value), ['40', '10', '30', '16%', '2']);
  assert.equal(k[1].hint, '25% 击杀率');
  assert.equal(kpis(null)[1].hint, '');
  const h = heatmap({ [ago(0)]: 8, [ago(1)]: 2, [ago(29)]: 1, [ago(30)]: 50 }, TODAY);
  assert.equal(h.days.length, 30);
  assert.equal(h.days[29].key, dayKey(TODAY));
  assert.deepEqual([h.total, h.active, h.peak], [11, 3, 8]);
  assert.deepEqual([h.days[29].level, h.days[28].level, h.days[0].level, h.days[1].level], [4, 1, 1, 0]);
  assert.deepEqual(h.ticks, ['8/27', '今天']);
  const rows = weakSubjects([...Array.from({ length: 5 }, (_, i) => item({ uid: `a${i}`, subject: '英语', decayed_mastery: 0.1 })),
    ...Array.from({ length: 5 }, (_, i) => item({ uid: `b${i}`, subject: '化学', decayed_mastery: 0.7 })),
    ...Array.from({ length: 4 }, (_, i) => item({ uid: `c${i}`, subject: '物理', decayed_mastery: 0 })),
    item({ uid: 'x', subject: '化学', suspended: true, decayed_mastery: 0 })]);
  assert.deepEqual(rows.map(r => [r.key, r.pct, r.tone, r.count]), [['英语', 10, 'danger', 5], ['化学', 70, 'success', 5]]);
  const plan = Array.from({ length: 6 }, (_, i) => ({ key: `k${i}` }));
  assert.deepEqual([visiblePlan(plan, false).rows.length, visiblePlan(plan, false).hidden, visiblePlan(plan, true).collapsible], [4, 2, true]);
  assert.equal(visiblePlan(plan.slice(0, 3), true).collapsible, false);
});
