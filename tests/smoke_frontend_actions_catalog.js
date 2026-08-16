/* 前端冒烟测试：用最小 DOM 桩跑 actions.js / catalog.js 的纯逻辑部分。
   不是浏览器环境替代品，只验证「给定 DATA 能算出预期的建议条目 / 能渲染出树」。
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
vm.runInContext(load('actions.js'), sandbox, { filename: 'actions.js' });
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

// ── 场景 1：空题库 ──
console.log('场景 1 空题库');
setInContext('DATA', { total: 0, items: [], review_alert: {}, daily_trend: {} });
setInContext('SESSIONS', []);
let plan = sandbox.buildActionPlan();
check('只给一条「去录入」建议', plan.length === 1 && plan[0].key === 'empty');

// ── 场景 2：逾期 + 今日到期 + 顽固题 + 未反馈 Session ──
console.log('场景 2 有积压');
setInContext('DATA', {
  total: 5,
  daily_trend: { [daysAgo(1)]: 4 },
  review_alert: {},
  items: [
    makeItem({ uid: 'A1', due_date: daysAgo(9), mastery: 0.2, decayed_mastery: 0.15 }),
    makeItem({ uid: 'A2', due_date: daysAgo(2), mastery: 0.3, decayed_mastery: 0.25 }),
    makeItem({ uid: 'B1', due_date: daysAgo(0), mastery: 0.4, decayed_mastery: 0.35 }),
    makeItem({ uid: 'C1', is_leech: true, mastery: 0.1, decayed_mastery: 0.08 }),
    makeItem({ uid: 'D1', mastery: 1, tag: '#状态/已击杀' }),
  ],
});
setInContext('SESSIONS', [{ session_id: 'EXP-1', status: 'active', count: 6 }]);
plan = sandbox.buildActionPlan();
const keys = plan.map(r => r.key);
check('识别出逾期', keys.includes('overdue'));
check('识别出今日到期', keys.includes('due_today'));
check('识别出顽固题', keys.includes('leech'));
check('识别出未反馈 Session', keys.includes('pending_feedback'));
check('没有误报「状态良好」', !keys.includes('all_good'));
check('紧急项排在最前', plan[0].level === 'urgent', `实际 ${plan[0].level}/${plan[0].key}`);
const overdueRow = plan.find(r => r.key === 'overdue');
check('逾期计数不含已击杀题', overdueRow.metric === '2', `实际 ${overdueRow.metric}`);
check('逾期天数取最久的一道', overdueRow.detail.includes('9 天'), overdueRow.detail);

// ── 场景 3：一切清空 ──
console.log('场景 3 无积压');
setInContext('DATA', {
  total: 2,
  daily_trend: { [new Date().toISOString().slice(0, 10)]: 6 },
  review_alert: {},
  items: [
    makeItem({ uid: 'E1', due_date: daysAhead(6), mastery: 0.9, decayed_mastery: 0.88, attempts: 5, last_review: daysAgo(1) }),
    makeItem({ uid: 'E2', due_date: daysAhead(9), mastery: 0.85, decayed_mastery: 0.8, attempts: 4, last_review: daysAgo(1) }),
  ],
});
setInContext('SESSIONS', []);
plan = sandbox.buildActionPlan();
check('给出「状态良好」', plan[0].key === 'all_good', plan.map(r => r.key).join(','));
check('没有紧急项', !plan.some(r => r.level === 'urgent'));

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
