/** Ledger 历史的纯投影：撤销状态、节点分类、标题、时间和排序。 */
const corrections = new Set(['review.replace', 'review.retract', 'review.restore',
  'session.retract', 'session.restore', 'state.restore']);
const number = (value, fallback = 0) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};

export const isHistoryCorrection = row => corrections.has(row?.commit_type);
export const historyCommitFamily = type => {
  if (type === 'review.batch_submit') return 'review';
  if (type === 'session.create' || type === 'session.complete') return 'session';
  if (type?.startsWith('question.')) return 'question';
  return 'system';
};

export function orderedHistoryRows(commits, sort = 'asc') {
  return [...(commits || [])].sort((a, b) => sort === 'desc'
    ? number(b.seq) - number(a.seq) : number(a.seq) - number(b.seq));
}

export function historyRetractionState(commits) {
  const retractedSessions = new Set();
  const retractedReviews = new Set();
  for (const row of orderedHistoryRows(commits)) {
    const p = row.payload || {};
    if (row.commit_type === 'session.retract' && p.session_id) retractedSessions.add(p.session_id);
    else if (row.commit_type === 'session.restore' && p.session_id) retractedSessions.delete(p.session_id);
    else if (row.commit_type === 'review.retract') retractedReviews.add(`${p.target_commit_id}:${number(p.target_review_index)}`);
    else if (row.commit_type === 'review.restore') retractedReviews.delete(`${p.target_commit_id}:${number(p.target_review_index)}`);
  }
  return { retractedSessions, retractedReviews };
}

export function normalizeHistoryRetractionState(state) {
  if (!state) return null;
  return { retractedSessions: new Set(state.retracted_sessions || []),
    retractedReviews: new Set(state.retracted_reviews || []) };
}

export const historyNodeSessionId = row => {
  const p = row.payload || {};
  return p.session_id || p.session?.session_id || '';
};

export function isNodeRetracted(row, rs) {
  const p = row.payload || {};
  if (row.commit_type === 'session.create') {
    const sid = historyNodeSessionId(row);
    return !!sid && rs.retractedSessions.has(sid);
  }
  if (row.commit_type !== 'review.batch_submit') return false;
  const feedbacks = p.feedbacks || p.reviews || [];
  if (!feedbacks.length) return false;
  const batchSid = p.session_id || '';
  return feedbacks.every((fb, index) => {
    const sid = batchSid || fb.session_id || '';
    return rs.retractedReviews.has(`${row.commit_id}:${index}`)
      || (!!sid && rs.retractedSessions.has(sid));
  });
}

export function historyRows(commits, retraction, sort = 'asc') {
  const rs = normalizeHistoryRetractionState(retraction) || historyRetractionState(commits);
  const ordered = orderedHistoryRows(commits, sort);
  const ordinary = ordered.filter(row => !isHistoryCorrection(row));
  const main = ordinary.filter(row => !isNodeRetracted(row, rs));
  return { main, corrections: ordered.filter(isHistoryCorrection), hidden: ordinary.length - main.length, rs };
}

export function historySessionLabel(sid) {
  if (!sid) return '手动反馈';
  if (String(sid).startsWith('IMM-')) return '即时练习';
  if (String(sid).startsWith('EXP-')) return '复习 Session';
  return 'Session';
}

export function historyReviewBatchStats(row, rs) {
  const p = row.payload || {};
  const feedbacks = p.feedbacks || p.reviews || [];
  const sid = p.session_id || '';
  let active = 0, correct = 0, wrong = 0, hidden = 0;
  const uids = [];
  feedbacks.forEach((fb, index) => {
    const effectiveSid = sid || fb.session_id || '';
    const off = rs && (rs.retractedReviews.has(`${row.commit_id}:${index}`)
      || (!!effectiveSid && rs.retractedSessions.has(effectiveSid)));
    if (off) { hidden += 1; return; }
    active += 1;
    uids.push(fb.uid_at_that_time || fb.uid || fb.question_id || `#${index + 1}`);
    if (fb.is_correct) correct += 1;
    else wrong += 1;
  });
  return { sid, total: feedbacks.length, active, correct, wrong, hidden, uids };
}

function uidSummary(uids, total) {
  if (!uids.length) return total ? '全部已撤销' : '无题目';
  const shown = uids.slice(0, 3).join('、');
  return uids.length > 3 ? `${shown} 等 ${uids.length} 题` : shown;
}

export function historyNodeTitle(row, rs) {
  const p = row.payload || {};
  const type = row.commit_type;
  if (type === 'review.batch_submit') {
    const stats = historyReviewBatchStats(row, rs);
    return `${historySessionLabel(stats.sid)} · ${uidSummary(stats.uids, stats.total)}`;
  }
  if (type === 'legacy.bootstrap') return row.summary || '迁移旧数据';
  if (type === 'system.genesis') return '初始化 Ledger';
  if (type === 'session.create') {
    const sid = historyNodeSessionId(row);
    return `新建 ${historySessionLabel(sid)} · ${sid || '未命名'}`;
  }
  if (type === 'session.complete') return `完成 Session · ${p.session_id || ''}`;
  if (type === 'question.create' || type === 'question.create_external') {
    const q = p.question || p;
    return `新增题目 · ${q.uid || q.UID || ''}`;
  }
  if (type === 'question.move' || type === 'question.move_external') return `迁移题目 · ${p.from_uid || ''} → ${p.to_uid || ''}`;
  if (type === 'question.metadata_update' || type === 'question.metadata_update_external') return `更新题目字段 · ${p.uid_at_that_time || ''}`;
  if (type === 'question.archive' || type === 'question.archive_external') return `删除 / 归档题目 · ${p.uid_at_that_time || ''}`;
  return row.summary || row.message || type;
}

export function historyNodeSubtitle(row, rs) {
  if (row.commit_type === 'review.batch_submit') {
    const stats = historyReviewBatchStats(row, rs);
    const line = `${stats.active}/${stats.total} 题有效 · ${stats.correct} 对 ${stats.wrong} 错${stats.hidden ? ` · ${stats.hidden} 条已撤销` : ''}`;
    return stats.sid ? `${line} · ${stats.sid}` : line;
  }
  if (row.commit_type === 'legacy.bootstrap') return '旧 CSV、Session 和 Markdown 结构导入 Ledger';
  if (row.commit_type === 'system.genesis') return '创建不可变提交链起点';
  return row.summary && row.summary !== historyNodeTitle(row, rs) ? row.summary : row.message || '';
}

export function formatLedgerTime(value, zone = 'local') {
  const raw = String(value || '').trim();
  if (!raw) return '';
  // 旧记录无偏移时无法可靠转换，保留原墙上时间。
  if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(raw)) return raw.replace('T', ' ').slice(0, 19);
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw.replace('T', ' ').slice(0, 19);
  const options = { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' };
  if (zone !== 'local') options.timeZone = zone;
  try {
    const parts = new Intl.DateTimeFormat('zh-CN', options).formatToParts(date);
    const values = Object.fromEntries(parts.filter(part => part.type !== 'literal').map(part => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
  } catch { return raw.replace('T', ' ').slice(0, 19); }
}
