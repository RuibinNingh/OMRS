import test from 'node:test';
import assert from 'node:assert/strict';
import {
  historyRetractionState, normalizeHistoryRetractionState, historyRows, isNodeRetracted,
  historyReviewBatchStats, historyNodeTitle, historyNodeSubtitle, historyCommitFamily,
  formatLedgerTime, projectRecent,
} from '../../assets/app/domain/history.js';
import { readPreferences, reviewVisual, restoreTarget, historyPayloadPreview, reviewPayload,
  timeGroups, dateRange, durationText, state } from '../../assets/app/features/history/state.js';
import { view } from '../../assets/app/features/history/view.js';

const session = { seq: 2, commit_id: 's2', commit_type: 'session.create', payload: { session_id: 'EXP-1' }, created_at: '2026-09-25T12:00:00+08:00' };
const review = { seq: 3, commit_id: 'r3', commit_type: 'review.batch_submit', payload: {
  session_id: 'EXP-1', feedbacks: [{ uid: 'A', is_correct: true }, { uid: 'B', is_correct: false }],
}, created_at: '2026-09-25T12:10:00+08:00' };
const retract = { seq: 4, commit_id: 'x4', commit_type: 'review.retract', payload: { target_commit_id: 'r3', target_review_index: 0 } };
const restore = { seq: 5, commit_id: 'x5', commit_type: 'review.restore', payload: { target_commit_id: 'r3', target_review_index: 0 } };

test('撤销状态按 seq 回放；服务端状态优先，整次 Session 撤销时主节点隐藏', () => {
  const rs = historyRetractionState([retract, review, session]);
  assert.deepEqual([...rs.retractedReviews], ['r3:0']);
  assert.equal(isNodeRetracted(review, rs), false);
  assert.equal(historyReviewBatchStats(review, rs).hidden, 1);
  assert.equal(historyRows([review, session, retract], null).corrections.length, 1);
  assert.deepEqual([...historyRetractionState([restore, retract, review]).retractedReviews], []);

  const state = normalizeHistoryRetractionState({ retracted_sessions: ['EXP-1'], retracted_reviews: [] });
  assert.equal(isNodeRetracted(session, state), true);
  assert.equal(isNodeRetracted(review, state), true);
  const rows = historyRows([session, review, retract], { retracted_sessions: ['EXP-1'] });
  assert.equal(rows.main.length, 0);
  assert.equal(rows.hidden, 2);
  assert.equal(rows.corrections.length, 1);
});

test('节点标题、批次统计、分类和排序与历史记录页共用', () => {
  const rs = historyRetractionState([retract, review]);
  assert.equal(historyNodeTitle(review, rs), '复习 Session · B');
  assert.match(historyNodeSubtitle(review, rs), /1\/2 题有效 · 0 对 1 错 · 1 条已撤销/);
  assert.equal(historyCommitFamily('question.create_external'), 'question');
  assert.equal(historyRows([session, review], null, 'desc').main[0].commit_id, 'r3');
  assert.equal(historyNodeTitle({ commit_type: 'system.genesis', payload: {} }), '初始化 Ledger');
});

test('最近动态不用旧全局，过滤修正和撤销节点，时间按指定时区显示', () => {
  const recent = projectRecent([session, review, retract], { retracted_reviews: ['r3:0'] }, 4, 'Asia/Shanghai');
  assert.deepEqual(recent.map(row => row.id), ['r3', 's2']);
  assert.equal(recent[0].chip, '0 对 · 1 错');
  assert.equal(recent[0].time, '2026-09-25 12:10');
  assert.equal(formatLedgerTime('2026-09-25T12:10:00+08:00', 'UTC'), '2026-09-25 04:10:00');
  assert.equal(formatLedgerTime('2026-09-25T12:10:00', 'UTC'), '2026-09-25 12:10:00');
});

test('历史页偏好、配比条和修正记录恢复按钮按当前撤销状态计算', () => {
  const storage = { getItem: key => ({ 'omrs-history-sort': 'desc', 'omrs-history-edit-mode': '1' })[key] };
  assert.deepEqual(readPreferences(storage), { sort: 'desc', edit: true });
  const rs = historyRetractionState([retract, review]);
  assert.deepEqual(reviewVisual(review, rs), { marks: ['off', 'no'], correct: 0, wrong: 1, correctPct: 0 });
  assert.deepEqual(restoreTarget(retract, rs), { type: 'review', id: 'r3', index: 0 });
  assert.equal(restoreTarget(retract, historyRetractionState([restore, retract, review])), null);
});

test('修正请求钳制分数，旧迁移载荷预览摘要截断', () => {
  const payload = reviewPayload(review, 'replace', { index: 1, score: 12.6, correct: 'false', note: '<备注>', reason: '  更正  ' });
  assert.deepEqual(payload, { target_commit_id: 'r3', target_review_index: 1, reason: '更正',
    replacement: { sub_score: 10, is_correct: false, note: '<备注>' } });
  const legacy = historyPayloadPreview({ commit_type: 'legacy.bootstrap', payload: { questions: Array(30).fill({}) } });
  assert.match(legacy, /"questions": 30/);
  assert.doesNotMatch(legacy, /\{\}/);
});

test('日期筛选按所选时区的日界线，覆盖跨年与夏令时长短日', () => {
  assert.deepEqual(dateRange('all', 'UTC'), {});
  assert.deepEqual(dateRange('7d', 'Asia/Shanghai', Date.parse('2026-01-01T22:00:00Z')), {
    since: '2025-12-26T16:00:00.000Z', until: '2026-01-02T16:00:00.000Z',
  });
  assert.deepEqual(dateRange('today', 'America/New_York', Date.parse('2026-03-08T16:00:00Z')), {
    since: '2026-03-08T05:00:00.000Z', until: '2026-03-09T04:00:00.000Z',
  });
  assert.deepEqual(dateRange('today', 'America/New_York', Date.parse('2026-11-01T16:00:00Z')), {
    since: '2026-11-01T04:00:00.000Z', until: '2026-11-02T05:00:00.000Z',
  });
});

test('时间线按显示时区分日，空时间有明确分组，耗时区分未完成与未知', () => {
  const rows = [{ started_at: '2026-10-02T01:00:00Z' }, { created_at: '2026-10-01T18:00:00Z' }, {}];
  assert.deepEqual(timeGroups(rows, 'Asia/Shanghai').map(g => [g.date, g.rows.length]), [['2026-10-02', 2], ['初始化', 1]]);
  assert.deepEqual(timeGroups(rows, 'UTC').map(g => g.date), ['2026-10-02', '2026-10-01', '初始化']);
  assert.equal(durationText({ status: 'running' }), '执行中');
  assert.equal(durationText({ status: 'interrupted' }), '—');
  assert.equal(durationText({ duration_ms: 1234 }), '1.23 s');
  assert.deepEqual(readPreferences({ getItem: () => null }), { sort: 'desc', edit: false });
});

test('选中态和手机详情开关能写入布尔属性，调用摘要不会注入 HTML', () => {
  const s = { ...state, commits: [session], selectedSeq: session.seq, tab: 'learning', mobileDetail: true };
  const learning = view(s, 'UTC').text;
  assert.match(learning, /aria-pressed="true"/);
  assert.match(learning, /data-mobile-detail="true"/);
  const system = view({ ...s, tab: 'system', system: { ...state.system,
    records: [{ seq: 1, title: '<script>隐私</script>', status: 'failure', tool: 'get_overview', key_name: '仅查询' }],
    selectedSeq: 1 } }, 'UTC').text;
  assert.doesNotMatch(system, /<script>/);
  assert.match(system, /&lt;script&gt;/);
});
