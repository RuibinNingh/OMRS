/* 前端冒烟测试：用最小 DOM 桩跑「粘贴 OMR /result JSON → 自动填写反馈行」的整条链路。
   test_omr_import.js 测的是纯解析函数；这里补的是纯函数测不到的接线部分——
   元素 id 对不对、Session 查得到查不到、结果有没有真的落进 fbRows。
   运行：node tests/smoke_feedback_omr_import.js  （在仓库根目录） */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const root = path.resolve(__dirname, '..');
const load = (f) => fs.readFileSync(path.join(root, 'assets', f), 'utf8');

// ── 最小 DOM 桩 ──
function makeEl(id) {
  return {
    id, value: '', textContent: '', innerHTML: '', className: '', open: false,
    classList: {
      add() {}, remove() {}, toggle() {},
      contains: (name) => id === 'panel-feedback' && name === 'active',
    },
    dataset: {}, querySelector: () => null, querySelectorAll: () => [],
    addEventListener() {}, scrollIntoView() {},
  };
}
const els = {};
const document = {
  getElementById: (id) => (els[id] = els[id] || makeEl(id)),
  querySelector: () => null,
  querySelectorAll: () => [],
  addEventListener() {},
  documentElement: { getAttribute: () => 'dark', setAttribute() {} },
};
const sandbox = {
  document, console, Intl, Date, Math, JSON, Number, Object, Set, Map, String, Array,
  Boolean, RegExp, Error, Promise, isNaN, parseInt, parseFloat,
  localStorage: { getItem: () => null, setItem() {} },
  navigator: {}, window: {}, setTimeout, URLSearchParams,
  fetch: async () => { throw new Error('offline') },
};
sandbox.window = sandbox;
vm.createContext(sandbox);

vm.runInContext(load('core.js'), sandbox, { filename: 'core.js' });
vm.runInContext(load('feedback.js'), sandbox, { filename: 'feedback.js' });
// 这几个由别的文件提供，冒烟只要求存在
vm.runInContext(`
  function getItems(){ return [] }
  async function qvRender(){ }
  function refreshFbSessionPicker(){ }
`, sandbox);

function setInContext(name, value) {
  sandbox.__tmp = value;
  vm.runInContext(`${name} = __tmp`, sandbox);
}
const getFromContext = (expr) => vm.runInContext(expr, sandbox);

let failures = 0;
function check(label, condition, extra) {
  if (condition) { console.log(`  ok   ${label}`); return; }
  failures++;
  console.log(`  FAIL ${label}${extra ? ' — ' + extra : ''}`);
}

// onFbSessionChange 是从 #fb-session-picker 读当前 Session 的，桩里要照做
function selectSession(sessionObj) {
  setInContext('SESSIONS', [sessionObj]);
  document.getElementById('fb-session-picker').value = sessionObj.session_id;
  sandbox.onFbSessionChange(true);
}

// ── 夹具：一个 4 题的 Session + OMR /result 顶层协议 ──
const SESSION = {
  session_id: 'EXP-20260902120000', status: 'active', count: 4,
  uids: ['化学-钠和氯1', '化学-钠和氯2', '化学-钠和氯3', '化学-钠和氯6'],
  feedback_uids: [], pending_uids: [],
};

const scanJson = JSON.stringify({
  recognition_id: 42,
  template_id: 'omrs-2col-normal-30q-tm-v2',
  mode: 'omrs',
  status: 'needs_review',
  questions: [
    { seq: 1, page: 1, result: 'C', level: '9' },
    { seq: 2, page: 1, result: 'W', level: '3' },
    { seq: 3, page: 1, result: null, level: '5' },
    { seq: 4, page: 1, result: 'C', level: null },
  ],
  unresolved: [{ seq: 3, field: 'q3_result', status: 'multi_marked' }],
});

// ── 1. 没选 Session 时必须拒绝，而不是瞎对号 ──
setInContext('SESSIONS', [SESSION]);
setInContext('ACTIVE_FB_SESSION', '');
sandbox.fbImportText(scanJson, { from: 'clipboard' });
check('未选 Session 时拒绝导入', els['fb-json-status'].innerHTML.includes('请先在上面选中'));
check('未选 Session 时不写入 fbRows', getFromContext('fbRows.length') === 0);

// ── 2. 选中 Session 后按题号自动填写 ──
selectSession(SESSION);
check('选中 Session 后建出 4 行待录入', getFromContext('fbRows.length') === 4);

sandbox.fbImportText(scanJson, { from: 'clipboard' });
const rows = getFromContext('fbRows');
check('第 1 题 → C/9 判对', rows[0].correct === true && rows[0].score === 9);
check('第 2 题 → W/3 判错', rows[1].correct === false && rows[1].score === 3);
check('第 3 题 unresolved 不猜对错', rows[2].correct === null);
check('第 3 题把 unresolved 字段与状态写进备注', /q3_result.*multi_marked/.test(rows[2].note));
check('第 4 题掌握度没涂时给默认 10 分', rows[3].correct === true && rows[3].score === 10);
check('题号按 Session 顺序对上 UID', rows[0].uid === SESSION.uids[0] && rows[3].uid === SESSION.uids[3]);

const status = els['fb-json-status'].innerHTML;
check('状态行报出自动填写数', status.includes('自动填写 <strong>3</strong> 题'));
check('状态行点出待人工判定的题', status.includes('1 题没有自动判定'));
check('状态行提示 OMR 侧仍待复核', status.includes('待复核'));

// ── 3. 已录入过的题不重复填 ──
selectSession(Object.assign({}, SESSION, { feedback_uids: [SESSION.uids[0]] }));
sandbox.fbImportText(scanJson, { from: 'clipboard' });
check('已录入的题被跳过', els['fb-json-status'].innerHTML.includes('已经录过反馈'));
check('剩下 3 行待录入', getFromContext('fbRows.length') === 3);

// ── 4. 同一入口仍然认得旧的反馈 JSON ──
selectSession(SESSION);
sandbox.fbImportText(JSON.stringify({
  type: 'omrs-feedback', version: 1, session_id: SESSION.session_id,
  items: [{ uid: SESSION.uids[1], is_correct: true, sub_score: 8, note: '' }],
}), {});
check('反馈 JSON 仍走原路径', els['fb-json-status'].innerHTML.includes('已导入 1 条作答'));

// ── 5. 坏输入不炸 ──
sandbox.fbImportText('这不是 JSON', { from: 'clipboard' });
check('非 JSON 给出可读报错', els['fb-json-status'].innerHTML.includes('剪贴板里不是 JSON'));
sandbox.fbImportText(JSON.stringify({ items: [], count: 0 }), {});
check('旧 items 协议被明确拒绝', els['fb-json-status'].innerHTML.includes('只接受 /api/v1/recognitions/{id}/result')
  && els['fb-json-status'].innerHTML.includes('不接受旧 raw/items'));

console.log(failures ? `\n${failures} 项失败` : '\n全部通过');
process.exit(failures ? 1 : 0);
