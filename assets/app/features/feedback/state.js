/**
 * 反馈录入工作台：状态与纯逻辑（不碰 DOM、不碰旧全局，由 tests/app/feedback.test.mjs 在 node 里覆盖）。
 * 状态是模块单例：离开页面再回来，Session 选择、判定、导入的行都还在（与迁移前一致）；整页刷新后清空。
 *
 * 流程：选 Session → 建出「待录入」行（rail 显示全部题目，含已录入的只读项）→ 逐题看题面、判对错、打分、写备注
 *  → 「提交反馈」把已判定的行发给 /api/feedback（提交体 {uid, sub_score, is_correct, note} 不变）。
 *  未判定的行在部分提交后保留到下一批；已录入过的题不重复提交。
 * 答题卡扫描（OMR）JSON 与反馈 JSON 走同一套解析（omrReadSheet / omrApplyToRows / fbImportFeedbackRows / fbPayloadKind）。
 *
 * 会话与题目数据（SESSIONS / ACTIVE_FB_SESSION / 题目列表）仍归旧代码所有，本模块只经 domain/sessions.js 读取，
 * 纯函数则把 session 作为参数传入（保持可单测）。
 */

// 本文件刻意不依赖 core.js 的 asNumber / clampNumber：解析器与纯逻辑要能在 node 侧单独 import 出来测。
export function num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}
function clamp(value, min, max, fallback) {
  const n = Number(value);
  return Number.isFinite(n) ? Math.min(max, Math.max(min, n)) : fallback;
}

// ── Session 进度与题目顺序（纯函数，test_feedback_ui.js 迁来后仍覆盖）────────────────
// 实现迁到 domain/sessions.js（P6 第 3 轮，复习调度与反馈录入共用）；这里原名再导出，反馈页与旧 schedule 调用方不变。
import { sessionUniqueUids, sessionProgress } from '../../domain/sessions.js';
export { sessionUniqueUids };
export const fbSessionProgress = sessionProgress;

export function fbSessionPositions(session) {
  return new Map(sessionUniqueUids(session).map((uid, index) => [uid, index + 1]));
}

/** 本 Session 待录入的行；序号沿用 Session 原始顺序。 */
export function fbRowsForSession(session) {
  const positions = fbSessionPositions(session);
  return fbSessionProgress(session).pending_uids.map((uid, index) => ({
    id: Date.now() + index, uid, number: positions.get(uid) || index + 1,
    score: 5, correct: null, note: '', scoreTouched: false,
  }));
}

/** 拆成「已判定（对/错）」与「未判定」两组，供部分提交时保留未判定行。 */
export function fbRowsForSubmit(rows) {
  const ready = [];
  const pending = [];
  (rows || []).forEach(row => (row?.correct === true || row?.correct === false) ? ready.push(row) : pending.push(row));
  return { ready, pending };
}

/**
 * rail 条目：选中 Session 时显示「全部题目」（含已录入），序号沿用 Session 原始顺序；
 * 已录入的条目 recorded=true 只读。导入 / 手动添加但不属于本 Session 的行追加到末尾（extra=true）。
 * 手动 / 导入模式（无 Session）时就是 rows 本身。
 */
export function fbRailEntries(session, rows) {
  const list = rows || [];
  const rowIndexByUid = new Map();
  list.forEach((row, index) => {
    const uid = String(row?.uid || '').trim();
    if (uid && !rowIndexByUid.has(uid)) rowIndexByUid.set(uid, index);
  });
  if (!session) {
    return list.map((row, index) => ({ uid: String(row?.uid || '').trim(), number: num(row?.number, 0) || index + 1, recorded: false, index }));
  }
  const positions = fbSessionPositions(session);
  const recorded = new Set(fbSessionProgress(session).feedback_uids);
  const entries = sessionUniqueUids(session).map(uid => ({
    uid, number: positions.get(uid) || 0, recorded: recorded.has(uid),
    index: rowIndexByUid.has(uid) ? rowIndexByUid.get(uid) : -1,
  }));
  list.forEach((row, index) => {
    const uid = String(row?.uid || '').trim();
    if (uid && positions.has(uid)) return;
    entries.push({ uid, number: entries.length + 1, recorded: false, index, extra: true });
  });
  return entries;
}

// ── 光标 / 导航（纯函数，作用在 entries + rows 上）────────────────────────────────
export function clampCursor(entries, cursor) {
  if (!entries.length) return 0;
  return Math.max(0, Math.min(entries.length - 1, num(cursor, 0)));
}

/** 第一道「未录入、未判定」的条目；没有就退回第一道未录入。 */
export function firstOpenIndex(entries, rows) {
  const at = entries.findIndex(entry => !entry.recorded && entry.index >= 0 && rows[entry.index]?.correct == null);
  return at >= 0 ? at : entries.findIndex(entry => !entry.recorded);
}

/** 从 cursor 的下一条起循环找第一道未判定题；没有返回 -1。 */
export function nextOpenIndex(entries, rows, cursor) {
  if (!entries.length) return -1;
  for (let step = 1; step <= entries.length; step += 1) {
    const at = (cursor + step) % entries.length;
    const entry = entries[at];
    if (!entry.recorded && entry.index >= 0 && rows[entry.index]?.correct == null) return at;
  }
  return -1;
}

/** 当前光标处「可编辑」的上下文；已录入 / UID 空 / 行被移除时返回 null。 */
export function currentContext(entries, rows, cursor) {
  const entry = entries[cursor];
  if (!entry || entry.recorded || entry.index < 0) return null;
  const row = rows[entry.index];
  return row ? { entry, index: entry.index, row } : null;
}

// ── 判定 / 打分（就地改行；返回是否有变化）──────────────────────────────────────
export const defaultScore = correct => (correct ? 9 : 4); // 与 importFeedbackJson 的 correct?10:4 同一心智，但手判默认略保守
export function setVerdict(row, correct) {
  if (!row) return false;
  row.correct = !!correct;
  if (!row.scoreTouched) row.score = correct ? 9 : 4;
  return true;
}
export function setScore(row, value) {
  if (!row) return false;
  row.score = Math.round(clamp(value, 0, 10, 5));
  row.scoreTouched = true;
  return true;
}

/** 已判定的行 → 提交体（顺序即 rows 顺序）。 */
export function submitPayload(rows) {
  return fbRowsForSubmit(rows).ready.map(row => ({ uid: row.uid, sub_score: row.score, is_correct: row.correct, note: row.note }));
}

// ════════════════════════════════════════════════════════════════════
// 答题卡扫描（OMR）/result 顶层协议 → 逐题结论 → 落到反馈行
// 详见 AI/omr-import.md。全部在前端完成，/api/feedback 契约不变。
// ════════════════════════════════════════════════════════════════════
const OMR_ANKI_GRADES = { E: { correct: true, score: 10 }, G: { correct: true, score: 8 }, H: { correct: true, score: 5 }, A: { correct: false, score: 1 } };
export const OMR_NOTE_PREFIX = 'OMR：';

export function omrInt(value, fallback) { const n = Number(value); return Number.isFinite(n) ? Math.round(n) : fallback; }
export function omrScore(value) { const n = Number(value); return Number.isFinite(n) ? Math.max(0, Math.min(10, Math.round(n))) : 5; }

export function omrIsResultProtocol(data) {
  return !!data && typeof data === 'object' && !Array.isArray(data)
    && Object.prototype.hasOwnProperty.call(data, 'recognition_id')
    && Object.prototype.hasOwnProperty.call(data, 'template_id')
    && Object.prototype.hasOwnProperty.call(data, 'mode')
    && Object.prototype.hasOwnProperty.call(data, 'status')
    && Array.isArray(data.questions) && Array.isArray(data.unresolved);
}

export function omrReadResultProtocol(record) {
  const status = String(record.status || '').trim().toLowerCase();
  if (status === 'failed') return { error: '这次识别是失败的，不导入。请回 OMR 查看识别详情。' };
  if (['uploaded', 'queued', 'processing'].includes(status)) return { error: `这份扫描还没识别完（当前状态 ${status}），等 OMR 跑完后重新复制 /result JSON。` };
  const mode = String(record.mode || '').trim().toLowerCase();
  const unresolvedBySeq = new Map();
  record.unresolved.forEach(entry => {
    const number = omrInt(entry?.seq, 0);
    if (!(number > 0)) return;
    if (!unresolvedBySeq.has(number)) unresolvedBySeq.set(number, []);
    unresolvedBySeq.get(number).push(entry);
  });
  const questions = record.questions.map(entry => {
    const number = omrInt(entry?.seq, 0);
    const out = { number, correct: null, score: null, scored: false, reason: '', note: '' };
    const unresolved = unresolvedBySeq.get(number) || [];
    if (unresolved.length) {
      out.reason = `待人工处理：${unresolved.map(item => `${String(item?.field || `q${number}`)}（${String(item?.status || 'unresolved')}）`).join('、')}`;
      return out;
    }
    if (mode === 'omrs') {
      const result = String(entry?.result ?? '').trim().toUpperCase();
      if (result === 'C') out.correct = true;
      else if (result === 'W') out.correct = false;
      else out.reason = result ? `对错结论「${result}」既不是 C 也不是 W` : '没有对错结论';
      if (entry?.level != null && String(entry.level).trim() !== '') { out.score = omrScore(entry.level); out.scored = true; }
    } else if (mode === 'anki') {
      const answer = String(entry?.answer ?? '').trim().toUpperCase();
      const grade = OMR_ANKI_GRADES[answer];
      if (grade) { out.correct = grade.correct; out.score = grade.score; out.scored = true; }
      else out.reason = answer ? `读出「${answer}」，不是 E / G / H / A` : '没有 Anki 档位结论';
    }
    return out;
  }).filter(question => question.number > 0).sort((a, b) => a.number - b.number);
  return { mode, status, questions, record };
}

/** 一整张（或一叠）答题卡 → 逐题结论。只接受 OMR /result 顶层协议。 */
export function omrReadSheet(data) {
  if (!omrIsResultProtocol(data)) return { error: 'OMR 剪贴板导入只接受 /api/v1/recognitions/{id}/result 顶层协议（recognition_id/template_id/mode/status/questions/unresolved）；不接受旧 raw/items、裸数组或包装层协议。' };
  return omrReadResultProtocol(data);
}

export function omrMergeNote(existing, text) {
  const base = String(existing || '').trim();
  const add = `${OMR_NOTE_PREFIX}${text}`;
  if (!text) return base;
  if (base.includes(add)) return base;
  return base ? `${base} · ${add}` : add;
}

/** 逐题结论按 Session 顺序落到反馈行；扫描没覆盖到的题原样留着（correct 仍为 null）。 */
export function omrApplyToRows(rows, questions, sessionUids, recordedUids) {
  const uids = (sessionUids || []).map(uid => String(uid || '').trim());
  const recorded = recordedUids instanceof Set ? recordedUids : new Set(recordedUids || []);
  const rowByUid = new Map();
  (rows || []).forEach((row, index) => { const uid = String(row?.uid || '').trim(); if (uid && !rowByUid.has(uid)) rowByUid.set(uid, index); });
  const report = { total: (questions || []).length, filled: 0, correct: 0, wrong: 0, manual: [], skippedRecorded: 0, outOfRange: [], missingRow: [] };
  (questions || []).forEach(question => {
    const uid = uids[question.number - 1] || '';
    if (!uid) { report.outOfRange.push(question.number); return; }
    if (recorded.has(uid)) { report.skippedRecorded++; return; }
    const index = rowByUid.get(uid);
    if (index == null) { report.missingRow.push(question.number); return; }
    const row = rows[index];
    if (question.correct == null) {
      report.manual.push({ number: question.number, uid, reason: question.reason || '需要人工判定' });
      row.note = omrMergeNote(row.note, question.reason);
      return;
    }
    row.correct = question.correct;
    row.score = question.scored ? question.score : (question.correct ? 10 : 4);
    row.scoreTouched = true;
    if (question.note) row.note = omrMergeNote(row.note, question.note);
    report.filled++;
    if (question.correct) report.correct++; else report.wrong++;
  });
  return report;
}

// ── 反馈 JSON（屏幕版 / AI）→ 反馈行 ─────────────────────────────────────────────
function looseBool(value) {
  if (value === true || value === false) return value;
  const s = String(value ?? '').trim().toLowerCase();
  if (['true', '1', 'yes', 'y', '对', '正确', 'correct'].includes(s)) return true;
  if (['false', '0', 'no', 'n', '错', '错误', 'wrong', 'incorrect'].includes(s)) return false;
  return null;
}

/** 把反馈 JSON 的条目转成反馈行（纯函数）；跳过无 UID / 判不出对错的条目。 */
export function fbImportFeedbackRows(data) {
  const rawItems = Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : (Array.isArray(data?.feedbacks) ? data.feedbacks : []));
  const rows = [];
  let skipped = 0;
  rawItems.forEach((it, i) => {
    const uid = it && (it.uid ?? it.UID) != null ? String(it.uid ?? it.UID).trim() : '';
    const correct = looseBool(it?.is_correct ?? it?.correct);
    if (!uid || correct === null) { skipped++; return; }
    rows.push({ id: Date.now() + i, uid, score: Math.max(0, Math.min(10, Math.round(num(it.sub_score ?? it.score, correct ? 10 : 4)))), correct, note: String(it?.note ?? '').trim(), scoreTouched: true });
  });
  return { rows, skipped, sessionId: String(data?.session_id || '').trim() };
}

/** 分流：answercard 扫描 / 反馈 JSON / 题目 JSON。 */
export function fbPayloadKind(data) {
  if (data && data.type === 'omrs-questions') return 'questions';
  if (data && Array.isArray(data.questions) && data.questions.some(entry => entry && (entry.uid != null || entry.question != null))) return 'questions';
  if (data && data.type === 'omrs-feedback') return 'feedback';
  const list = Array.isArray(data) ? data : (Array.isArray(data?.items) ? data.items : (Array.isArray(data?.feedbacks) ? data.feedbacks : null));
  if (Array.isArray(list) && list.some(entry => entry && typeof entry === 'object' && (entry.uid != null || entry.UID != null) && (entry.is_correct !== undefined || entry.correct !== undefined))) return 'feedback';
  return 'omr';
}

// ── 模块单例状态 ────────────────────────────────────────────────────────────────
export function createState() {
  return {
    rows: [],          // {id, uid, number, score, correct, note, scoreTouched}
    cursor: 0,         // rail 条目下标
    stageUid: '',      // 舞台上正在显示的 uid，用来避免重复重绘题面
    lastResult: null,  // {rows, okCount, total, sessionId, at}
    submitting: false,
    status: null,      // 状态行：{ tone:'ok'|'warn'|'danger', text }
    importOpen: false, // 「导入反馈」折叠面板是否展开
    importText: '',    // 导入文本框的草稿（morph 重绘时不丢）
    importStatus: null,// 导入面板状态：{ tone, html }
    promptStatus: null,// AI 提示词复制状态：{ tone, text }
    sessionsLoading: false,
    sessionsError: '',
  };
}

export const state = createState();
