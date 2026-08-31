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
for (const file of ['core.js', 'actions.js']) {
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
vm.runInContext('DATA = {items: [{uid:"active", mastery:0.2}, {uid:"paused", mastery:0.2, suspended:true}]};', sandbox);
if (sandbox.actionActiveItems().map(item => item.uid).join(',') !== 'active') throw new Error('行动计划仍包含停用题');
vm.runInContext('DATA = {items: [{uid:"paused", mastery:0.2, suspended:true, is_leech:true}]};', sandbox);
if (sandbox.buildActionPlan().some(item => item.key === 'leech')) throw new Error('顽固题行动建议仍包含停用题');
 element('q-filter-suspended').value = 'suspended';
 sandbox.actionResetQuestionFilters();
if (element('q-filter-suspended').value !== '') throw new Error('行动推荐跳转未清除停用筛选');
if (sandbox.jsArg("a'b").includes("'")) throw new Error('题目 UID 未做 JavaScript 参数安全编码');
console.log('停用题前端筛选、行动计划与跳转验证通过');
