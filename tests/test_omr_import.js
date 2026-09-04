// OMR 顶层 /result 协议 JSON → 反馈行 的解析测试。
// 正式形态固定为 recognition_id/template_id/mode/status/questions/unresolved；
// raw/items、裸数组与包装层都必须明确拒绝。
const assert = require('node:assert/strict');
const test = require('node:test');
const {
  fbRowsForSession, omrReadSheet, omrApplyToRows, fbPayloadKind,
} = require('../assets/feedback.js');

const session = { uids: ['U1', 'U2', 'U3', 'U4'], feedback_uids: [] };

const resultProtocol = (questions, overrides = {}) => Object.assign({
  recognition_id: 12,
  template_id: 'omrs-2col-normal-30q-tm-v2',
  mode: 'omrs',
  status: 'ready',
  questions,
  unresolved: [],
}, overrides);

function applyToSession(record, sessionObj = session) {
  const sheet = omrReadSheet(record);
  assert.equal(sheet.error, undefined, `omrReadSheet 不该报错：${sheet.error}`);
  const rows = fbRowsForSession(sessionObj);
  const report = omrApplyToRows(rows, sheet.questions, sessionObj.uids,
    new Set(sessionObj.feedback_uids || []));
  return { sheet, rows, report };
}

test('正式 /result 协议：OMRS questions.result / level 填入对错与主观分', () => {
  const { sheet, rows, report } = applyToSession(resultProtocol([
    { seq: 1, page: 1, result: 'C', level: '9' },
    { seq: 2, page: 1, result: 'W', level: '3' },
  ]));
  assert.equal(sheet.mode, 'omrs');
  assert.deepEqual(rows.slice(0, 2).map(row => [row.uid, row.correct, row.score]),
    [['U1', true, 9], ['U2', false, 3]]);
  assert.equal(report.filled, 2);
});

test('正式 /result 协议：Anki questions.answer 保持 SM-2 映射', () => {
  const { rows, report } = applyToSession(resultProtocol([
    { seq: 1, page: 1, answer: 'E' },
    { seq: 2, page: 1, answer: 'G' },
    { seq: 3, page: 1, answer: 'H' },
    { seq: 4, page: 1, answer: 'A' },
  ], { template_id: 'anki-4col-normal-30q-tm-v2', mode: 'anki' }));
  assert.deepEqual(rows.map(row => [row.correct, row.score]),
    [[true, 10], [true, 8], [true, 5], [false, 1]]);
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
  assert.deepEqual(rows.slice(0, 3).map(row => [row.correct, row.score]),
    [[null, 5], [null, 5], [true, 10]]);
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
  const oldInputs = [
    rawRecord,
    rawRecord.items,
    { result: rawRecord },
    { recognition_id: 12, template_id: 'omrs-x', mode: 'omrs', status: 'ready', questions: [] },
  ];
  oldInputs.forEach(input => {
    const parsed = omrReadSheet(input);
    assert.match(parsed.error, /只接受.*\/api\/v1\/recognitions\/\{id\}\/result/);
    assert.match(parsed.error, /不接受.*raw\/items/);
  });
});

test('正式 /result 协议仍拒绝失败或未完成状态', () => {
  const failed = omrReadSheet(resultProtocol([], { status: 'failed' }));
  const queued = omrReadSheet(resultProtocol([], { status: 'queued' }));
  assert.match(failed.error, /失败/);
  assert.match(queued.error, /还没识别完/);
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
    { seq: 1, page: 1, answer: 'B' },
    { seq: 2, page: 1, answer: 'D' },
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
  assert.deepEqual(rows.map(row => [row.uid, row.correct]),
    [['U1', true], ['U2', null], ['U3', false], ['U4', null]]);
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
  const { rows } = applyToSession(resultProtocol([
    { seq: 2, page: 1, result: 'C', level: '9' },
  ]));
  assert.deepEqual(rows.map(row => row.correct), [null, true, null, null]);
});

test('同一个入口能分辨反馈 JSON、正式 /result 与题目 JSON', () => {
  assert.equal(fbPayloadKind({ type: 'omrs-feedback', items: [{ uid: 'U1', is_correct: true }] }), 'feedback');
  assert.equal(fbPayloadKind([{ uid: 'U1', is_correct: false, sub_score: 4 }]), 'feedback');
  assert.equal(fbPayloadKind(resultProtocol([{ seq: 1, result: 'C', level: '9' }])), 'omr');
  assert.equal(fbPayloadKind({ type: 'omrs-questions', questions: [{ uid: 'U1' }] }), 'questions');
});
