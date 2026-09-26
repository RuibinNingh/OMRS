// 反馈录入的纯逻辑（assets/app/features/feedback/state.js）与导入计划（importer.js）：不依赖 DOM 与旧全局。
// 迁自 P4 之前的三个文件，断言逐条保留：
//   tests/test_feedback_ui.js（Session 进度 / 部分提交）、tests/test_omr_import.js（/result 协议契约）、
//   tests/smoke_feedback_omr_import.js（粘贴答题卡 → 自动填写的整条链路，现在由 planImportText 承担）。
import test from 'node:test';
import assert from 'node:assert/strict';
import * as S from '../../assets/app/features/feedback/state.js';
import { planImportText, parseLooseJson, escapeHtml } from '../../assets/app/features/feedback/importer.js';

const { fbSessionProgress, fbRowsForSession, fbRowsForSubmit, omrReadSheet, omrApplyToRows, fbPayloadKind } = S;

// ════════ 迁自 test_feedback_ui.js ════════
test('session progress keeps session order and filters already submitted UIDs', () => {
  const session = { count: 4, uids: ['U1', 'U2', 'U3', 'U4'], feedback_uids: ['U3', 'U3', 'U1'] };
  assert.deepEqual(fbSessionProgress(session), {
    total: 4, feedback_uids: ['U1', 'U3'], pending_uids: ['U2', 'U4'],
    feedback_count: 2, pending_count: 2, complete: false,
  });
  const rows = fbRowsForSession(session);
  assert.deepEqual(rows.map(row => row.uid), ['U2', 'U4']);
  assert.deepEqual(rows.map(row => row.number), [2, 4]);
});

test('completed session produces no editable feedback rows', () => {
  const session = { uids: ['U1', 'U2'], feedback_uids: ['U1', 'U2'] };
  assert.equal(fbSessionProgress(session).complete, true);
  assert.deepEqual(fbRowsForSession(session), []);
});

test('partial submit keeps unjudged rows for the next batch', () => {
  const rows = [
    { uid: 'U1', correct: true }, { uid: 'U2', correct: null },
    { uid: 'U3', correct: false }, { uid: '', correct: null },
  ];
  assert.deepEqual(fbRowsForSubmit(rows), { ready: [rows[0], rows[2]], pending: [rows[1], rows[3]] });
});

// ════════ 迁自 test_omr_import.js ════════
const session = { uids: ['U1', 'U2', 'U3', 'U4'], feedback_uids: [] };
const resultProtocol = (questions, overrides = {}) => Object.assign({
  recognition_id: 12, template_id: 'omrs-2col-normal-30q-tm-v2', mode: 'omrs', status: 'ready', questions, unresolved: [],
}, overrides);

function applyToSession(record, sessionObj = session) {
  const sheet = omrReadSheet(record);
  assert.equal(sheet.error, undefined, `omrReadSheet 不该报错：${sheet.error}`);
  const rows = fbRowsForSession(sessionObj);
  const report = omrApplyToRows(rows, sheet.questions, sessionObj.uids, new Set(sessionObj.feedback_uids || []));
  return { sheet, rows, report };
}

test('正式 /result 协议：OMRS questions.result / level 填入对错与主观分', () => {
  const { sheet, rows, report } = applyToSession(resultProtocol([
    { seq: 1, page: 1, result: 'C', level: '9' },
    { seq: 2, page: 1, result: 'W', level: '3' },
  ]));
  assert.equal(sheet.mode, 'omrs');
  assert.deepEqual(rows.slice(0, 2).map(row => [row.uid, row.correct, row.score]), [['U1', true, 9], ['U2', false, 3]]);
  assert.equal(report.filled, 2);
});

test('正式 /result 协议：Anki questions.answer 保持 SM-2 映射', () => {
  const { rows, report } = applyToSession(resultProtocol([
    { seq: 1, page: 1, answer: 'E' }, { seq: 2, page: 1, answer: 'G' },
    { seq: 3, page: 1, answer: 'H' }, { seq: 4, page: 1, answer: 'A' },
  ], { template_id: 'anki-4col-normal-30q-tm-v2', mode: 'anki' }));
  assert.deepEqual(rows.map(row => [row.correct, row.score]), [[true, 10], [true, 8], [true, 5], [false, 1]]);
  assert.equal(report.filled, 4);
});

test('unresolved 会阻止对应题自动填写并进入人工处理', () => {
  const { rows, report } = applyToSession(resultProtocol([
    { seq: 1, page: 1, result: 'C', level: '9' },
    { seq: 2, page: 1, result: 'W', level: '3' },
    { seq: 3, page: 1, result: 'C', level: null },
  ], {
    status: 'needs_review',
    unresolved: [
      { seq: 1, field: 'q1_result', status: 'ambiguous' },
      { seq: 2, field: 'q2_level', status: 'multi_marked' },
    ],
  }));
  assert.deepEqual(rows.slice(0, 3).map(row => [row.correct, row.score]), [[null, 5], [null, 5], [true, 10]]);
  assert.equal(report.filled, 1);
  assert.equal(report.manual.length, 2);
  assert.match(rows[0].note, /q1_result.*ambiguous/);
  assert.match(rows[1].note, /q2_level.*multi_marked/);
});

test('明确拒绝旧 raw/items、裸数组、包装层与不完整 result 形态', () => {
  const rawRecord = {
    id: 12, status: 'ready', template_id: 'omrs-2col-normal-30q-tm-v2',
    items: [{ seq: 1, field: 'q1_result', raw_value: 'C', result_status: 'accepted' }],
  };
  [rawRecord, rawRecord.items, { result: rawRecord },
    { recognition_id: 12, template_id: 'omrs-x', mode: 'omrs', status: 'ready', questions: [] },
  ].forEach(input => {
    const parsed = omrReadSheet(input);
    assert.match(parsed.error, /只接受.*\/api\/v1\/recognitions\/\{id\}\/result/);
    assert.match(parsed.error, /不接受.*raw\/items/);
  });
});

test('正式 /result 协议仍拒绝失败或未完成状态', () => {
  assert.match(omrReadSheet(resultProtocol([], { status: 'failed' })).error, /失败/);
  assert.match(omrReadSheet(resultProtocol([], { status: 'queued' })).error, /还没识别完/);
});

test('OMRS /result 中 level 为 null 且不在 unresolved 时按对错给默认分', () => {
  const { rows } = applyToSession(resultProtocol([
    { seq: 1, page: 1, result: 'C', level: null },
    { seq: 2, page: 1, result: 'W', level: null },
  ]));
  assert.deepEqual(rows.slice(0, 2).map(row => [row.correct, row.score]), [[true, 10], [false, 4]]);
});

test('正式 custom /result 只有 answer，推不出对错并留给人工', () => {
  const { sheet, rows, report } = applyToSession(resultProtocol([
    { seq: 1, page: 1, answer: 'B' }, { seq: 2, page: 1, answer: 'D' },
  ], { template_id: 'custom-4col-normal-30q-tm-v2', mode: 'custom' }));
  assert.equal(sheet.mode, 'custom');
  assert.equal(report.filled, 0);
  assert.equal(report.manual.length, 2);
  assert.deepEqual(rows.slice(0, 2).map(row => row.correct), [null, null]);
});

test('多页 /result：seq 全卷连续，page 不参与题号映射', () => {
  const { rows, report } = applyToSession(resultProtocol([
    { seq: 3, page: 2, result: 'W', level: '1' },
    { seq: 1, page: 1, result: 'C', level: '8' },
  ]));
  assert.deepEqual(rows.map(row => [row.uid, row.correct]), [['U1', true], ['U2', null], ['U3', false], ['U4', null]]);
  assert.equal(report.filled, 2);
});

test('超出 Session 题数的题号被忽略，已录入的题被跳过', () => {
  const shortSession = { uids: ['U1', 'U2'], feedback_uids: ['U2'] };
  const { rows, report } = applyToSession(resultProtocol([
    { seq: 1, page: 1, result: 'C', level: '9' },
    { seq: 2, page: 1, result: 'W', level: '4' },
    { seq: 5, page: 1, result: 'C', level: '7' },
  ]), shortSession);
  assert.deepEqual(rows.map(row => row.uid), ['U1']);
  assert.equal(report.filled, 1);
  assert.equal(report.skippedRecorded, 1);
  assert.deepEqual(report.outOfRange, [5]);
});

test('正式 /result 没覆盖到的 Session 题保持未判定', () => {
  const { rows } = applyToSession(resultProtocol([{ seq: 2, page: 1, result: 'C', level: '9' }]));
  assert.deepEqual(rows.map(row => row.correct), [null, true, null, null]);
});

test('同一个入口能分辨反馈 JSON、正式 /result 与题目 JSON', () => {
  assert.equal(fbPayloadKind({ type: 'omrs-feedback', items: [{ uid: 'U1', is_correct: true }] }), 'feedback');
  assert.equal(fbPayloadKind([{ uid: 'U1', is_correct: false, sub_score: 4 }]), 'feedback');
  assert.equal(fbPayloadKind(resultProtocol([{ seq: 1, result: 'C', level: '9' }])), 'omr');
  assert.equal(fbPayloadKind({ type: 'omrs-questions', questions: [{ uid: 'U1' }] }), 'questions');
});

// ════════ 迁自 smoke_feedback_omr_import.js：粘贴答题卡 → 自动填写 ════════
const SESSION = {
  session_id: 'EXP-20260902120000', status: 'active', count: 4,
  uids: ['化学-钠和氯1', '化学-钠和氯2', '化学-钠和氯3', '化学-钠和氯6'], feedback_uids: [], pending_uids: [],
};
const scanJson = JSON.stringify({
  recognition_id: 42, template_id: 'omrs-2col-normal-30q-tm-v2', mode: 'omrs', status: 'needs_review',
  questions: [
    { seq: 1, page: 1, result: 'C', level: '9' }, { seq: 2, page: 1, result: 'W', level: '3' },
    { seq: 3, page: 1, result: null, level: '5' }, { seq: 4, page: 1, result: 'C', level: null },
  ],
  unresolved: [{ seq: 3, field: 'q3_result', status: 'multi_marked' }],
});
const finder = (...list) => id => list.find(x => x.session_id === id) || null;

test('粘贴答题卡：没选 Session 时拒绝导入，不瞎对号', () => {
  const plan = planImportText(scanJson, { session: null, findSession: finder(SESSION), from: 'clipboard' });
  assert.equal(plan.ok, false);
  assert.equal(plan.rows, undefined);
  assert.match(plan.html, /请先在上面选中/);
});

test('粘贴答题卡：选中 Session 后按题号自动填写，报告写清自动 / 人工 / 待复核', () => {
  assert.equal(fbRowsForSession(SESSION).length, 4);
  const plan = planImportText(scanJson, { session: SESSION, findSession: finder(SESSION), from: 'clipboard' });
  assert.equal(plan.ok, true);
  const rows = plan.rows;
  assert.ok(rows[0].correct === true && rows[0].score === 9, '第 1 题 → C/9 判对');
  assert.ok(rows[1].correct === false && rows[1].score === 3, '第 2 题 → W/3 判错');
  assert.equal(rows[2].correct, null, '第 3 题 unresolved 不猜对错');
  assert.match(rows[2].note, /q3_result.*multi_marked/);
  assert.ok(rows[3].correct === true && rows[3].score === 10, '第 4 题掌握度没涂时给默认 10 分');
  assert.ok(rows[0].uid === SESSION.uids[0] && rows[3].uid === SESSION.uids[3], '题号按 Session 顺序对上 UID');
  assert.ok(plan.html.includes('自动填写 <strong>3</strong> 题'));
  assert.ok(plan.html.includes('1 题没有自动判定'));
  assert.ok(plan.html.includes('待复核'));
});

test('粘贴答题卡：已录入过的题不重复填', () => {
  const partly = { ...SESSION, feedback_uids: [SESSION.uids[0]] };
  const plan = planImportText(scanJson, { session: partly, findSession: finder(partly), from: 'clipboard' });
  assert.ok(plan.html.includes('已经录过反馈'));
  assert.equal(plan.rows.length, 3);
});

test('同一入口仍认得反馈 JSON，并切到其中的 Session', () => {
  const plan = planImportText(JSON.stringify({
    type: 'omrs-feedback', version: 1, session_id: SESSION.session_id,
    items: [{ uid: SESSION.uids[1], is_correct: true, sub_score: 8, note: '' }],
  }), { session: SESSION, findSession: finder(SESSION) });
  assert.equal(plan.ok, true);
  assert.ok(plan.html.includes('已导入 1 条作答'));
  assert.equal(plan.activeId, SESSION.session_id);
  assert.deepEqual(plan.rows.map(r => [r.uid, r.correct, r.score]), [[SESSION.uids[1], true, 8]]);
});

test('反馈 JSON：已全部录入时给出提示；没有 session_id 时 activeId 为空串', () => {
  const done = { ...SESSION, feedback_uids: [...SESSION.uids] };
  const dup = planImportText(JSON.stringify({ type: 'omrs-feedback', session_id: done.session_id, items: [{ uid: done.uids[0], is_correct: false }] }), { findSession: finder(done) });
  assert.equal(dup.ok, false);
  assert.match(dup.html, /已全部录入/);
  const loose = planImportText('[{"uid":"X1","correct":"错"}]', {});
  assert.equal(loose.ok, true);
  assert.equal(loose.activeId, '');
  assert.deepEqual(loose.rows.map(r => [r.uid, r.correct, r.score]), [['X1', false, 4]]);
});

test('坏输入不炸：非 JSON 给可读报错，旧 items 协议被明确拒绝，题目 JSON 被拦下', () => {
  assert.ok(planImportText('这不是 JSON', { from: 'clipboard' }).html.includes('剪贴板里不是 JSON'));
  assert.ok(planImportText('这不是 JSON', {}).html.includes('JSON 解析失败'));
  const old = planImportText(JSON.stringify({ items: [], count: 0 }), { session: SESSION });
  assert.ok(old.html.includes('只接受 /api/v1/recognitions/{id}/result') && old.html.includes('不接受旧 raw/items'));
  assert.match(planImportText('{"type":"omrs-questions","questions":[{"uid":"U1"}]}', {}).html, /题目 JSON/);
});

test('parseLooseJson / escapeHtml：去掉代码围栏、空内容报错、报错文本转义', () => {
  assert.deepEqual(parseLooseJson('```json\n{"a":1}\n```'), { a: 1 });
  assert.throws(() => parseLooseJson('   '), /内容为空/);
  assert.equal(escapeHtml('<b>"x"&\'y\''), '&lt;b&gt;&quot;x&quot;&amp;&#39;y&#39;');
});

// ════════ P4 新增：工作台的纯逻辑 ════════
test('fbRailEntries：选中 Session 时列全部题目（已录入只读），不属于本 Session 的行追加在末尾', () => {
  const sess = { uids: ['A', 'B', 'C'], feedback_uids: ['B'] };
  const rows = [...fbRowsForSession(sess), { uid: 'Z', correct: null }];
  const entries = S.fbRailEntries(sess, rows);
  assert.deepEqual(entries.map(e => [e.uid, e.number, e.recorded, e.index, !!e.extra]),
    [['A', 1, false, 0, false], ['B', 2, true, -1, false], ['C', 3, false, 1, false], ['Z', 4, false, 2, true]]);
  assert.deepEqual(S.fbRailEntries(null, [{ uid: 'Q' }, { uid: '' }]).map(e => [e.uid, e.number, e.index]), [['Q', 1, 0], ['', 2, 1]]);
});

test('光标：clampCursor 夹紧；firstOpenIndex / nextOpenIndex 跳过已录入与已判定并循环', () => {
  const sess = { uids: ['A', 'B', 'C', 'D'], feedback_uids: ['A'] };
  const rows = fbRowsForSession(sess); // B C D
  const entries = S.fbRailEntries(sess, rows);
  assert.equal(S.clampCursor(entries, 99), 3);
  assert.equal(S.clampCursor([], 5), 0);
  assert.equal(S.firstOpenIndex(entries, rows), 1);
  rows[0].correct = true; // B 判过
  assert.equal(S.firstOpenIndex(entries, rows), 2);
  assert.equal(S.nextOpenIndex(entries, rows, 3), 2); // 从 D 往后循环回到 C
  rows[1].correct = false; rows[2].correct = true;
  assert.equal(S.nextOpenIndex(entries, rows, 0), -1);
  assert.equal(S.currentContext(entries, rows, 0), null, '已录入的题没有可编辑上下文');
  assert.equal(S.currentContext(entries, rows, 1).row.uid, 'B');
});

test('判定 / 打分：未手动打分时对 9 错 4，手动打过分后判定不改分；提交体只含已判定行', () => {
  const row = { uid: 'A', score: 5, correct: null, note: 'n', scoreTouched: false };
  S.setVerdict(row, true); assert.deepEqual([row.correct, row.score], [true, 9]);
  S.setVerdict(row, false); assert.deepEqual([row.correct, row.score], [false, 4]);
  S.setScore(row, '12'); assert.equal(row.score, 10);
  S.setVerdict(row, true); assert.equal(row.score, 10, '手动打过分，判定不再覆盖');
  assert.equal(S.setVerdict(null, true), false);
  assert.deepEqual(S.submitPayload([row, { uid: 'B', correct: null }]), [{ uid: 'A', sub_score: 10, is_correct: true, note: 'n' }]);
});
