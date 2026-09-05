'use strict';
const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const values = new Map();
function element(id) {
  if (!values.has(id)) values.set(id, { id, value: '', checked: false });
  return values.get(id);
}
const sandbox = {
  console,
  Date,
  Math,
  Number,
  String,
  Object,
  Array,
  Set,
  Map,
  URLSearchParams,
  document: { getElementById: id => element(id), querySelectorAll: () => [], addEventListener() {} },
  localStorage: { getItem: () => null, setItem() {} },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(root, 'assets/core.js'), 'utf8'), sandbox);
const publicGetFilterState = sandbox.getFilterState;
const publicFilterItems = sandbox.filterItems;
vm.runInContext(fs.readFileSync(path.join(root, 'assets/recommend_v2.js'), 'utf8'), sandbox);

test('recommend v2 keeps the shared filter API intact', () => {
  assert.strictEqual(sandbox.getFilterState, publicGetFilterState);
  assert.strictEqual(sandbox.filterItems, publicFilterItems);
  assert.equal(typeof sandbox.recV2GetFilterState, 'function');
  assert.equal(typeof sandbox.recV2FilterItems, 'function');
});

test('recommend v2 filters use the shared suspended/text/knowledge contract', () => {
  element('rec-search-v2').value = 'circle';
  element('rec-filter-ktag-v2').value = '圆';
  element('rec-filter-sort-v2').value = 'mastery-asc';
  const items = [
    { uid: 'circle-1', subject: '数学', category: '几何', knowledge_tags: ['圆'], mastery: 0.2, difficulty: 5, suspended: false },
    { uid: 'circle-paused', subject: '数学', category: '几何', knowledge_tags: ['圆'], mastery: 0.1, difficulty: 5, suspended: true },
    { uid: 'line-1', subject: '数学', category: '几何', knowledge_tags: ['直线'], mastery: 0.1, difficulty: 5, suspended: false },
  ];
  const filters = sandbox.recV2GetFilterState();
  assert.deepEqual(Array.from(sandbox.recV2FilterItems(items, filters), item => item.uid), ['circle-1']);
});
