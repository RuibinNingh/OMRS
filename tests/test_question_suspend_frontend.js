'use strict';
const assert = require('node:assert/strict');

(async () => {
  const { filterItems } = await import('../assets/app/domain/items.js');
  const { defaultFilters, toItemFilters } = await import('../assets/app/features/questions/state.js');
  const items = [
    { uid: 'active', mastery: 0.2, difficulty: 5, suspended: false },
    { uid: 'paused', mastery: 0.2, difficulty: 5, suspended: true },
  ];
  const filtered = suspended => filterItems(items, toItemFilters({ ...defaultFilters(), suspended })).map(item => item.uid);
  assert.deepEqual(filtered(''), ['active']);
  assert.deepEqual(filtered('suspended'), ['paused']);
  assert.deepEqual(filtered('all'), ['active', 'paused']);
  console.log('停用题前端筛选验证通过');
})().catch(error => { console.error(error); process.exitCode = 1; });
