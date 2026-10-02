import { businessToday } from '../../assets/app/core/date.js';
// 复习调度 ·「安排复习」的纯函数（features/schedule/arrange.js）。原 tests/test_recommend_v2_filters.js 的用例迁来：
// 共享筛选契约（停用、文本、知识点）、本地日期的「今日 / 未到期」、标记任一 / 全部与 0% 熟练度、均衡轮选与排序、重拉时保留仍可安排的已选题。
// 共享筛选就是旧 core.js 的 filterItems（题库、导出、即时练习共用）：这里把 core.js 载入本进程当作 filterAll。
import test from 'node:test';
import assert from 'node:assert/strict';
import * as A from '../../assets/app/features/schedule/arrange.js';
import { filterAll } from '../../assets/app/domain/items.js';

const pick = (items, patch) => A.filterCandidates(items, { ...A.emptyFilters(), sort: 'mastery-asc', ...patch }, filterAll).map(i => i.uid);

test('shared filter contract: suspended hidden, text and knowledge tag', () => {
  const items = [
    { uid: 'circle-1', subject: '数学', category: '几何', knowledge_tags: ['圆'], mastery: 0.2, difficulty: 5, suspended: false },
    { uid: 'circle-paused', subject: '数学', category: '几何', knowledge_tags: ['圆'], mastery: 0.1, difficulty: 5, suspended: true },
    { uid: 'line-1', subject: '数学', category: '几何', knowledge_tags: ['直线'], mastery: 0.1, difficulty: 5, suspended: false },
  ];
  assert.deepEqual(pick(items, { text: ' Circle ', ktag: '圆' }), ['circle-1']);
});

test('local dates: today and future across Shanghai and negative UTC offsets', () => {
  const before = process.env.TZ;
  for (const zone of ['Asia/Shanghai', 'America/Los_Angeles']) {
    process.env.TZ = zone;
    const now = businessToday();
    const date = `${now.getFullYear()}-${now.getMonth() + 1}-${now.getDate()}`;
    const t = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const items = [{ uid: 'today', due_date: date, difficulty: 5 }, { uid: 'slash', due_date: date.replaceAll('-', '/'), difficulty: 5 },
      { uid: 'future', due_date: `${t.getFullYear()}-${t.getMonth() + 1}-${t.getDate()}`, difficulty: 5 }, { uid: 'invalid', due_date: '2026-02-31', difficulty: 5 }];
    assert.deepEqual(pick(items, { due: 'today', sort: 'priority', mode: 'due' }), ['today', 'slash']);
    assert.deepEqual(pick(items, { due: 'future', sort: 'priority', mode: 'due' }), ['future']);
  }
  if (before === undefined) delete process.env.TZ; else process.env.TZ = before;
});

test('label any / all, 0% mastery is a real bound, invalid ranges give nothing and a message', () => {
  const items = [{ uid: 'both', difficulty: 5, mastery: 0, labels: ['考前', '易错'] }, { uid: 'one', difficulty: 5, mastery: 0.5, labels: ['易错'] },
    { uid: 'none', difficulty: 5, mastery: 0, labels: [] }];
  const base = { labels: ['考前', '易错'], sort: 'priority', mode: 'due' };
  assert.deepEqual(pick(items, base), ['both', 'one']);
  assert.deepEqual(pick(items, { ...base, labelMode: 'all' }), ['both']);
  assert.deepEqual(pick(items, { sort: 'priority', mode: 'due', masteryMax: '0' }), ['both', 'none']);
  assert.deepEqual(pick(items, { diffMin: '9', diffMax: '2' }), []);
  assert.match(A.filterError(A.sharedFilters({ ...A.emptyFilters(), diffMin: '9', diffMax: '2' })), /下限不能大于上限/);
  assert.match(A.filterError(A.sharedFilters({ ...A.emptyFilters(), masteryMin: '120' })), /0–100%/);
  assert.equal(A.filterError(A.sharedFilters(A.emptyFilters())), '');
});

test('priority sort keeps server rank, then orders by mode (balanced rotates subjects, due first)', () => {
  const items = [{ uid: 'm1', subject: '数学', _source: 'due', mastery: 0.9 }, { uid: 'm2', subject: '数学', _source: 'due', mastery: 0 },
    { uid: 'p1', subject: '物理', _source: 'due', mastery: 0 }, { uid: 'early1', subject: '数学', _source: 'proficiency' }, { uid: 'early2', subject: '物理', _source: 'proficiency' }];
  assert.deepEqual(A.orderItems(items, 'balanced').map(i => i.uid), ['m1', 'p1', 'm2', 'early1', 'early2']);
  assert.deepEqual(A.orderItems(items, 'due').map(i => i.uid), ['m1', 'm2', 'p1', 'early1', 'early2']);
  assert.deepEqual(A.orderItems(items, 'weak').map(i => i.uid), ['early1', 'early2', 'm1', 'm2', 'p1']);
  const withDiff = items.map(i => ({ ...i, difficulty: 5 }));
  assert.deepEqual(A.filterCandidates(withDiff, { ...A.emptyFilters() }, filterAll).map(i => i.uid), ['m1', 'p1', 'm2', 'early1', 'early2'], '筛选后恢复服务端顺序再轮选，不按熟练度重排');
});

test('reload keeps still-eligible selected items (as the new objects) and reports the rest', () => {
  const merged = A.mergeLoaded({ due: [{ uid: 'keep', v: 2 }], proficiency: [{ uid: 'new' }] }, new Map([['keep', { uid: 'keep', v: 1 }], ['gone', { uid: 'gone' }]]));
  assert.deepEqual(merged.data.map(i => [i.uid, i._source]), [['keep', 'due'], ['new', 'proficiency']]);
  assert.deepEqual([...merged.selected.keys()], ['keep']);
  assert.equal(merged.selected.get('keep').v, 2);
  assert.equal(merged.removed, 1);
  assert.deepEqual(A.mergeLoaded(null, new Map()).data, []);
});

test('reason, revive chip, chips and clearing, smart pick, estimates, empty states, view preference', () => {
  assert.equal(A.reason({ is_revived: true, dormant_days: 40 }, -30), '复燃 · 已休眠 40 天');
  assert.deepEqual([A.reason({ _source: 'proficiency' }, 5), A.reason({ _source: 'proficiency' }, null), A.reason({}, null), A.reason({}, -2), A.reason({}, 0), A.reason({}, 3)],
    ['提前巩固 · 5 天后到期', '提前巩固', '待安排复习', '已逾期 2 天', '今日到期', '3 天后到期']);
  assert.deepEqual(A.revive({ is_revived: true, kill_count: 2, dormant_days: 31, next_revive_date: '2026-09-01' }), { label: '复燃 ×2', title: '第 2 次击杀后休眠 31 天复燃 · 原定 2026-09-01' });
  assert.equal(A.revive({ is_revived: true, suspended: true }), null);
  assert.equal(A.revive({ is_revived: true }).label, '复燃');
  const f = { ...A.emptyFilters(), mode: 'weak', subject: '物理', due: 'today', diffMin: '3', labels: ['易错'] };
  assert.deepEqual(A.chips(f).map(c => c.label), ['科目 物理', '到期 今日到期', '难度 ≥ 3', '标记 易错']);
  assert.deepEqual(A.clearField(f, 'label:易错').labels, []);
  assert.equal(A.clearField(f, 'subject').subject, '');
  assert.deepEqual(A.resetFilters(f), { ...A.emptyFilters(), mode: 'weak' }, '清除筛选保留推荐方式');
  const list = [{ uid: 'a', difficulty: 4 }, { uid: 'b', difficulty: 8 }, { uid: 'c' }];
  assert.deepEqual([...A.smartPick(list, '2').keys()], ['a', 'b']);
  assert.equal(A.smartPick(list, '0'), null);
  assert.equal(A.smartPick(list, '1.5'), null);
  assert.equal(A.estimateMinutes(list), 6 + 12 + 8);
  assert.equal(A.hiddenSelected(new Map([['a', {}], ['z', {}]]), list), 1);
  assert.deepEqual(A.emptyState({ data: [] }, '', 2), { title: '目前没有可安排的新题。 还有 2 个计划待完成，可以接着复习。', action: 'plans' });
  assert.deepEqual(A.emptyState({ data: [{}] }, '', 2), { title: '没有符合这些条件的题目，试试放宽筛选。', action: 'reset' });
  assert.equal(A.emptyState({ loading: true }, '', 0).action, null);
  assert.equal(A.emptyState({ data: [{}], onlySelected: true }, '', 0).title, '当前筛选内没有已选题。可关闭「只看已选」或清除筛选。');
  const store = new Map();
  const storage = { getItem: k => store.get(k) ?? null, setItem: (k, v) => store.set(k, v) };
  assert.equal(A.readView(storage), 'list');
  A.writeView(storage, 'gallery');
  assert.equal(A.readView(storage), 'gallery');
  assert.equal(A.readView({ getItem() { throw new Error('denied'); } }), 'list');
});
