/** 历史页状态和可单测的视图投影。 */
import { historyRows, formatLedgerTime } from '../../domain/history.js';

export const state = {
  commits: [], retraction: null, phase: 'idle', error: '', sort: 'desc', edit: false,
  correctionsOpen: false, busy: new Set(), note: '', writeError: '',
  hasMore: false, nextBeforeSeq: null, loadingMore: false, details: new Map(), detailErrors: new Map(),
  tab: 'learning', query: '', range: 'all', selectedSeq: null, mobileDetail: false,
  system: { records: [], phase: 'idle', error: '', selectedSeq: null, key: '', status: '',
    hasMore: false, nextBeforeSeq: null, loadingMore: false, details: new Map(), detailErrors: new Map(),
    keys: [], summary: { total: 0, success: 0, failure: 0, running: 0, interrupted: 0 } },
};

export function readPreferences(storage) {
  try {
    return { sort: storage.getItem('omrs-history-sort') === 'asc' ? 'asc' : 'desc',
      edit: storage.getItem('omrs-history-edit-mode') === '1' };
  } catch { return { sort: 'desc', edit: false }; }
}

export function timeline(s = state) {
  return historyRows(s.commits, s.retraction, s.sort);
}

export function timeGroups(rows, zone) {
  const groups = [];
  for (const row of rows) {
    const date = formatLedgerTime(row.started_at || row.created_at, zone).slice(0, 10) || '初始化';
    let group = groups[groups.length - 1];
    if (!group || group.date !== date) { group = { date, rows: [] }; groups.push(group); }
    group.rows.push(row);
  }
  return groups;
}

export function dateRange(range, zone, now = Date.now()) {
  if (!['today', '7d', '30d'].includes(range)) return {};
  const date = formatLedgerTime(new Date(now).toISOString(), zone).slice(0, 10);
  const day = Date.parse(`${date}T00:00:00Z`);
  const start = offset => {
    const target = day + offset * 86400000;
    let instant = target;
    for (let i = 0; i < 3; i++) {
      const wall = Date.parse(`${formatLedgerTime(new Date(instant).toISOString(), zone).replace(' ', 'T')}Z`);
      instant += target - wall;
    }
    return new Date(instant).toISOString();
  };
  return { since: start(range === 'today' ? 0 : range === '7d' ? -6 : -29), until: start(1) };
}

export function durationText(row) {
  if (row.duration_ms == null) return row.status === 'running' ? '执行中' : '—';
  return row.duration_ms < 1000 ? `${row.duration_ms} ms` : `${(row.duration_ms / 1000).toFixed(2)} s`;
}

export function reviewVisual(row, rs) {
  if (row.commit_type !== 'review.batch_submit') return null;
  const p = row.payload || {};
  const feedbacks = p.feedbacks || p.reviews || [];
  if (!feedbacks.length) return null;
  const sid = p.session_id || '';
  const marks = feedbacks.map((fb, index) => {
    const effectiveSid = sid || fb.session_id || '';
    if (rs.retractedReviews.has(`${row.commit_id}:${index}`)
      || (effectiveSid && rs.retractedSessions.has(effectiveSid))) return 'off';
    return fb.is_correct ? 'ok' : 'no';
  });
  const correct = marks.filter(mark => mark === 'ok').length;
  const wrong = marks.filter(mark => mark === 'no').length;
  return { marks, correct, wrong, correctPct: Math.round(100 * correct / (correct + wrong || 1)) };
}

export function restoreTarget(row, rs) {
  const p = row.payload || {};
  if (row.commit_type === 'session.retract' && p.session_id && rs.retractedSessions.has(p.session_id)) {
    return { type: 'session', id: p.session_id };
  }
  if (row.commit_type === 'review.retract' && p.target_commit_id != null) {
    const index = Number(p.target_review_index) || 0;
    if (rs.retractedReviews.has(`${p.target_commit_id}:${index}`)) {
      return { type: 'review', id: p.target_commit_id, index };
    }
  }
  return null;
}

export function historyPayloadPreview(row) {
  const payload = row.payload || {};
  let compact = payload;
  if (row.commit_type === 'legacy.bootstrap') {
    compact = { backup_dir: payload.backup_dir, questions: (payload.questions || []).length,
      mastery_rows: (payload.mastery_rows || []).length, session_rows: (payload.session_rows || []).length,
      history_rows: (payload.history_rows || []).length,
      changed_markdown_paths: (payload.changed_markdown_paths || []).slice(0, 20), notes: payload.notes || [] };
  } else if (Array.isArray(payload.feedbacks) && payload.feedbacks.length > 8) {
    compact = { ...payload, feedbacks: payload.feedbacks.slice(0, 8),
      feedbacks_truncated: `${payload.feedbacks.length - 8} more` };
  }
  const text = JSON.stringify(compact, null, 2);
  return text.length > 5000 ? `${text.slice(0, 5000)}\n... truncated ...` : text;
}

export function reviewPayload(row, kind, values) {
  const index = Math.max(0, Math.trunc(Number(values.index) || 0));
  const payload = { target_commit_id: row.commit_id, target_review_index: index,
    reason: String(values.reason || '').trim() };
  if (kind === 'replace') {
    const score = Number(values.score);
    payload.replacement = { sub_score: Math.max(0, Math.min(10, Math.round(Number.isFinite(score) ? score : 5))),
      is_correct: values.correct === 'true', note: String(values.note || '') };
  }
  return payload;
}
