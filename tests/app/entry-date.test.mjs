import assert from 'node:assert/strict';
import test from 'node:test';
import { businessToday } from '../../assets/app/core/date.js';
import { editEntryDate, entryDateError, entryDateOf, entryDateRange } from '../../assets/app/domain/entry-date.js';
import { filterItems } from '../../assets/app/domain/items.js';
import * as Q from '../../assets/app/features/questions/state.js';
import * as A from '../../assets/app/features/schedule/arrange.js';

const item = (uid, entry_date, other = {}) => ({ uid, entry_date, subject: '数学', difficulty: 5, labels: ['复盘'], ...other });
const ids = items => items.map(row => row.uid);
const before = new Date('2026-11-26T15:59:59Z');
const after = new Date('2026-11-26T16:00:00Z');

test('录入日优先用有效旧字段，创建时刻按上海午夜回退', () => {
  assert.equal(entryDateOf(item('旧题', '2026/9/2', { created_at: after.toISOString() })), '2026-09-02');
  assert.equal(entryDateOf(item('旧题', '2026-02-29', { created_at: before.toISOString() })), '2026-11-26');
  assert.equal(entryDateOf(item('缺录入日', '', { created_at: after.toISOString() })), '2026-11-27');
  assert.equal(entryDateOf(item('未知', '', { created_at: '2026-02-30T12:00:00Z' })), '');
  assert.equal(entryDateOf(item('未知', '随手写的日期')), '');
});

test('上海午夜切换今天和最近 7 / 30 天，两页条件和排序一致', () => {
  assert.deepEqual(entryDateRange({ entryDateMode: 'today' }, businessToday(before)), { from: '2026-11-26', to: '2026-11-26' });
  const today = businessToday(after);
  assert.deepEqual(entryDateRange({ entryDateMode: 'today' }, today), { from: '2026-11-27', to: '2026-11-27' });
  assert.deepEqual(entryDateRange({ entryDateMode: '30days' }, today), { from: '2026-10-29', to: '2026-11-27' });
  const list = [
    item('首日', '2026-11-21'), item('前一天', '2026-11-20'), item('末日', '2026-11-27'),
    item('后一天', '2026-11-28'), item('未知', ''), item('其他科', '2026-11-27', { subject: '物理' }),
    item('未标记', '2026-11-27', { labels: [] }),
  ];
  const patch = { entryDateMode: '7days', subject: '数学', labels: ['复盘'], sort: 'entry-desc' };
  assert.deepEqual(ids(filterItems(list, Q.toItemFilters({ ...Q.defaultFilters(), ...patch }, today))), ['末日', '首日']);
  assert.deepEqual(ids(A.filterCandidates(list, { ...A.emptyFilters(), ...patch }, filterItems, today)), ['末日', '首日']);
});

test('自定义草稿保留已应用的条件，只应用有效且至少有一端的范围', () => {
  const filters = { ...Q.defaultFilters(), entryDateMode: 'today', subject: '数学' };
  const opened = editEntryDate(filters, null, 'mode', 'custom');
  assert.equal(opened.filters, filters);
  assert.equal(editEntryDate(filters, opened.draft, 'apply').filters, filters);
  const { draft } = editEntryDate(filters, opened.draft, 'from', '2026-11-20');
  const invalid = editEntryDate(filters, draft, 'to', '2026-11-19');
  assert.match(entryDateError(invalid.draft), /开始日期不能晚于结束日期/);
  assert.equal(editEntryDate(filters, invalid.draft, 'apply').filters, filters);
  assert.match(entryDateError({ from: '2026-11-31', to: '' }), /有效的日期/);
  const applied = editEntryDate(filters, draft, 'apply');
  assert.deepEqual(entryDateRange(applied.filters), { from: '2026-11-20', to: '' });
  assert.equal(applied.draft, null);
  assert.deepEqual(entryDateRange(editEntryDate(filters, { from: '', to: '2026-11-20' }, 'apply').filters), { from: '', to: '2026-11-20' });
  assert.equal(Q.activeFilters(Q.toItemFilters(applied.filters)).find(chip => chip.kind === 'entryDate').label, '录入日期 · 2026-11-20 起');
  assert.equal(Q.clearFilter(applied.filters, 'entryDate').subject, '数学');
  assert.equal(A.clearField(applied.filters, 'entryDate').entryDateFrom, '');
  assert.equal(entryDateRange(Q.resetFilters(applied.filters)), null);
});

test('录入排序两向均以 UID 收同日并将日期未知排最后，精确创建排序独立', () => {
  const list = [item('b', '2026-11-21', { created_at: '2026-11-26T16:00:00Z' }), item('a', '2026-11-21'),
    item('c', '2026-11-23'), item('z', '')];
  const sorted = sort => ids(filterItems(list, Q.toItemFilters({ ...Q.defaultFilters(), sort })));
  assert.deepEqual(sorted('entry-desc'), ['c', 'a', 'b', 'z']);
  assert.deepEqual(sorted('entry-asc'), ['a', 'b', 'c', 'z']);
  assert.deepEqual(sorted('created-desc'), ['b', 'c', 'a', 'z']);
});

test('题库视图保存相对模式或固定端点，旧视图和错误日期退回全部', () => {
  const prefs = Q.defaultPrefs();
  const relative = Q.snapshot({ ...Q.defaultFilters(), entryDateMode: '7days', sort: 'entry-desc' }, prefs);
  const restored = Q.applySnapshot(relative, prefs).filters;
  assert.deepEqual(Q.toItemFilters(restored, businessToday(before)).entryDateRange, { from: '2026-11-20', to: '2026-11-26' });
  assert.deepEqual(Q.toItemFilters(restored, businessToday(after)).entryDateRange, { from: '2026-11-21', to: '2026-11-27' });
  assert.equal(restored.sort, 'entry-desc');
  assert.equal(Q.currentViewName({ 最近: relative }, restored), '最近');
  const custom = { ...Q.defaultFilters(), entryDateMode: 'custom', entryDateFrom: '', entryDateTo: '2026-11-27' };
  const saved = Q.snapshot(custom, prefs);
  assert.deepEqual(Q.applySnapshot(saved, prefs).filters, custom);
  assert.equal(Q.applySnapshot({ fields: { 'q-sort': 'created-asc' } }, prefs).filters.entryDateMode, '');
  saved.fields['q-filter-entry-date-to'] = '2026-02-31';
  assert.equal(Q.applySnapshot(saved, prefs).filters.entryDateMode, '');
});
