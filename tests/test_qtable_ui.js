const assert = require('node:assert/strict');
const test = require('node:test');

global.document = { addEventListener() {}, getElementById() { return null; }, querySelectorAll() { return []; } };
global.localStorage = { getItem() { return null; }, setItem() {} };
global.escapeHtml = value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
global.escapeAttr = global.escapeHtml;

const { qbActiveFilters, qbFilterCount, qbVisibleColumns, QB_DEFAULT_COLUMNS } = require('../assets/qtable.js');

const base = { text: '', subject: '', category: '', tag: '', knowledgeTag: '', labels: [], labelMode: 'any',
  difficultyMin: 1, difficultyMax: 10, masteryMin: 0, masteryMax: 1, dueFilter: '', suspended: '', sort: 'mastery-asc' };

test('sliders at both ends and empty selects count as no filter', () => {
  assert.deepEqual(qbActiveFilters(base), []);
  assert.equal(qbFilterCount(base), 0);
});

test('active filters produce one chip per condition with readable labels', () => {
  const active = qbActiveFilters({ ...base, subject: '数学', labels: ['考前必看', '压轴'], labelMode: 'all',
    difficultyMin: 3, masteryMax: 0.4, dueFilter: 'overdue', tag: '易错', suspended: 'suspended', text: 'sin' });
  const labels = active.map(entry => entry.label || entry.chip);
  assert.deepEqual(labels, ['搜索：sin', '科目：数学', '考前必看', '压轴', '标记：全部命中', '难度 3–10', '熟练度 0–40%', '到期：逾期', '状态：易错坑', '题目：仅停用题目']);
  assert.equal(qbFilterCount({ ...base, labels: ['A'] }), 1);
});

test('default columns keep select/main/actions even if hidden by prefs', () => {
  const columns = qbVisibleColumns();
  assert.ok(['select', 'main', 'actions', 'labels', 'mastery', 'due', 'status'].every(key => columns.has(key)));
  assert.deepEqual([...columns], QB_DEFAULT_COLUMNS);
});
