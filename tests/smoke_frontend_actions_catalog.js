/* 前端冒烟测试：用最小 DOM 桩跑 catalog.js 的纯逻辑部分（行动推荐已迁到 features/dashboard，见 tests/app/dashboard.test.mjs）。
   不是浏览器环境替代品，只验证「给定 DATA 能渲染出树」。
   运行：node tests/smoke_frontend_actions_catalog.js  （在仓库根目录） */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const load = (f) => fs.readFileSync(path.join(root, 'assets', f), 'utf8');

// ── 最小 DOM 桩 ──
function makeEl(id) {
  return {
    id, value: '', textContent: '', innerHTML: '', className: '', checked: false,
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false } },
    dataset: {},
  };
}
const els = {};
const document = {
  getElementById: (id) => (els[id] = els[id] || makeEl(id)),
  querySelectorAll: () => [],
  addEventListener() {},
  documentElement: { getAttribute: () => 'dark', setAttribute() {} },
};
const localStorage = { getItem: () => null, setItem() {} };
const sandbox = {
  document, localStorage, console, Intl, Date, Math, JSON, Number, Object, Set, Map,
  navigator: {}, window: {}, fetch: async () => { throw new Error('offline') },
  setTimeout, URLSearchParams,
};
sandbox.window = sandbox;
vm.createContext(sandbox);

vm.runInContext(load('core.js'), sandbox, { filename: 'core.js' });
vm.runInContext(load('catalog.js'), sandbox, { filename: 'catalog.js' });
// switchTab / renderQ / viewQ 由其他文件提供，这里只需要存在
vm.runInContext('function switchTab(){};function renderQ(){};function viewQ(){}', sandbox);

// core.js / catalog.js 里的 DATA、SESSIONS、CATALOG_* 是顶层 let，
// 不会挂到 global 上，所以要在 context 内部赋值而不是写 sandbox.X
function setInContext(name, value) {
  sandbox.__tmp = value;
  vm.runInContext(`${name} = __tmp`, sandbox);
}
function getFromContext(expr) { return vm.runInContext(expr, sandbox) }

let failures = 0;
function check(label, condition, extra) {
  if (condition) { console.log(`  ok   ${label}`); return; }
  failures++;
  console.log(`  FAIL ${label}${extra ? ' — ' + extra : ''}`);
}

function daysAgo(n) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return d.toISOString().slice(0, 10);
}
function daysAhead(n) { return daysAgo(-n); }

function makeItem(over) {
  return Object.assign({
    uid: 'X1', path: '错题/数学/甲/X1.md', subject: '数学', category: '甲',
    difficulty: 5, mastery: 0.5, decayed_mastery: 0.45, ef: 2.5, attempts: 2,
    last_review: daysAgo(3), due_date: daysAhead(10), tag: '#状态/待攻克',
    knowledge_tags: [], fail_count: 0, is_leech: false,
  }, over);
}

// 场景 1–3（行动推荐规则）随仪表盘迁到 assets/app/features/dashboard/plan.js（P6），用例在 tests/app/dashboard.test.mjs。

// ── 场景 4：目录树渲染 ──
console.log('场景 4 目录树');
setInContext('DATA', {
  total: 3, review_alert: {}, daily_trend: {},
  items: [
    makeItem({ uid: '隐圆模型1', path: '错题/数学/隐圆模型/隐圆模型1.md', category: '隐圆模型', mastery: 0.2, decayed_mastery: 0.18, due_date: daysAgo(1) }),
    makeItem({ uid: '隐圆模型2', path: '错题/数学/隐圆模型/隐圆模型2.md', category: '隐圆模型', mastery: 0.9, decayed_mastery: 0.88 }),
    makeItem({ uid: '动能定理1', path: '错题/物理/动能定理/动能定理1.md', subject: '物理', category: '动能定理', is_leech: true }),
  ],
});
setInContext('CATALOG_TREE', sandbox.catalogFallbackTree());
setInContext('CATALOG_OPEN', new Set(['错题', '错题/数学', '错题/物理', '错题/数学/隐圆模型', '错题/物理/动能定理']));
sandbox.renderCatalog();
const html = els['catalog-tree'].innerHTML;
check('渲染出根目录', html.includes('错题'));
check('渲染出二级分类目录', html.includes('隐圆模型'));
check('题目文件可点击打开', html.includes('catalogOpenQuestion'));
check('文件夹标出题量', html.includes('2 题'));
check('文件夹标出待复习', html.includes('待复习'));
check('文件夹标出顽固题', html.includes('顽固'));
check('统计卡渲染了题目文件数', els['catalog-stat'].innerHTML.includes('题目文件'));

// 折叠后子节点不再渲染
setInContext('CATALOG_OPEN', new Set(['错题']));
setInContext('CATALOG_QUERY', '');
sandbox.renderCatalog();
check('折叠后不渲染孙节点', !els['catalog-tree'].innerHTML.includes('隐圆模型1.md'));

// 搜索时自动展开命中分支
sandbox.catalogSearch('动能');
check('搜索命中后展开该分支', els['catalog-tree'].innerHTML.includes('动能定理'));
check('搜索过滤掉不相关分支', !els['catalog-tree'].innerHTML.includes('隐圆模型1.md'));

console.log(failures ? `\n${failures} 项失败` : '\n全部通过');
process.exit(failures ? 1 : 0);
