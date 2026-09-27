import test from 'node:test';
import assert from 'node:assert/strict';
import { filterAll, filterPractice, dueDays, parseReviewDate } from '../../assets/app/domain/items.js';

test('shared filters preserve suspended, labels, mastery bounds and server order in practice', () => {
  const rows = [
    { uid: 'a', subject: '数学', difficulty: 5, mastery: 0, labels: ['重点'] },
    { uid: 'b', subject: '数学', difficulty: 5, mastery: .5, labels: ['重点', '难题'], suspended: true },
    { uid: 'c', subject: '英语', difficulty: 7, mastery: .8, labels: ['难题'] },
  ];
  assert.deepEqual(filterAll(rows, { labels: ['重点', '难题'], labelMode: 'all', suspended: 'all', difficultyMin: 0, difficultyMax: 10 }).map(x => x.uid), ['b']);
  assert.deepEqual(filterAll(rows, { masteryMin: 0, masteryMax: 0, difficultyMin: 0, difficultyMax: 10 }).map(x => x.uid), ['a']);
  assert.deepEqual(filterPractice(rows, { subject: '数学' }).map(x => x.uid), ['a']);
});

test('due date parser rejects overflow and keeps local calendar dates', () => {
  assert.equal(parseReviewDate('2026-02-30'), null);
  assert.equal(dueDays({ due_date: '2026-09-28' }, new Date(2026, 8, 27)), 1);
});

test('dueDays survives being passed straight to map / filter (index is not a date)', () => {
  const rows = [{ due_date: '2000-01-01' }, { due_date: '' }, { due_date: '2999-01-01' }];
  const days = rows.map(dueDays);
  assert.equal(days.length, 3);
  assert.ok(days[0] < 0);
  assert.equal(days[1], null);
  assert.ok(days[2] > 0);
  assert.equal(dueDays({ due_date: '2026-09-28' }, new Date('invalid')), dueDays({ due_date: '2026-09-28' }));
});
