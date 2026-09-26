import test from 'node:test';
import assert from 'node:assert/strict';
import {
  historyRetractionState, normalizeHistoryRetractionState, historyRows, isNodeRetracted,
  historyReviewBatchStats, historyNodeTitle, historyNodeSubtitle, historyCommitFamily,
  formatLedgerTime, projectRecent,
} from '../../assets/app/domain/history.js';
import { readPreferences, reviewVisual, restoreTarget, historyPayloadPreview, reviewPayload } from '../../assets/app/features/history/state.js';

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
