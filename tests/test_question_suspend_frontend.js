'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const root = path.resolve(__dirname, '..');
const elements = {};
function element(id) {
  return elements[id] ||= { id, value: '', innerHTML: '', classList: { add() {}, remove() {}, toggle() {} } };
}
const sandbox = {
  document: { getElementById: id => element(id), querySelectorAll: () => [], addEventListener() {}, documentElement: { getAttribute: () => 'dark' } },
  localStorage: { getItem: () => null, setItem() {} },
  window: {}, navigator: {}, console, Intl, Date, Math, JSON, Number, Object, Set, Map,
};
sandbox.window = sandbox;
vm.createContext(sandbox);
for (const file of ['core.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'assets', file), 'utf8'), sandbox, { filename: file });
}
const items = [{ uid: 'active', mastery: 0.2, difficulty: 5, suspended: false }, { uid: 'paused', mastery: 0.2, difficulty: 5, suspended: true }];
function filtered(value) {
  element('q-filter-suspended').value = value;
  return sandbox.filterItems(items, sandbox.getFilterState('q')).map(item => item.uid);
}
if (JSON.stringify(filtered('')) !== JSON.stringify(['active'])) throw new Error('默认筛选应隐藏停用题');
if (JSON.stringify(filtered('suspended')) !== JSON.stringify(['paused'])) throw new Error('仅停用筛选失败');
if (JSON.stringify(filtered('all')) !== JSON.stringify(['active', 'paused'])) throw new Error('含停用筛选失败');
// 行动计划排除停用题、行动推荐把预设交给题库页：仪表盘迁到 features/dashboard（P6）后断言在 tests/app/dashboard.test.mjs
// 「suspended questions never enter the plan」与 tests/e2e/dashboard.py「跳转」段。
if (sandbox.jsArg("a'b").includes("'")) throw new Error('题目 UID 未做 JavaScript 参数安全编码');
console.log('停用题前端筛选与参数编码验证通过');
