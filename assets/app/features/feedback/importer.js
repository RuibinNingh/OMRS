/**
 * 反馈录入的「导入」：一段文本（剪贴板 / 粘贴 / 文本框）→ 解析 → 分流 → 算出新的行与状态报告。
 * 纯函数，不碰 DOM 与旧全局：Session 通过参数传入，结果由 index.js 的控制器落到 state 上。
 * 三个入口（读剪贴板按钮、页面空白处 Ctrl/⌘+V、「导入 JSON」按钮）走同一个 planImportText()。
 * 协议细节见 AI/omr-import.md；node 侧由 tests/app/feedback.test.mjs 覆盖（原 smoke_feedback_omr_import.js 的全部断言迁来）。
 */
import {
  sessionUniqueUids, fbSessionProgress, fbRowsForSession,
  omrReadSheet, omrApplyToRows, fbImportFeedbackRows, fbPayloadKind,
} from './state.js';

/** 与旧 core.js parseLooseJson 一致：去掉 ```json 围栏，空内容报错。 */
export function parseLooseJson(text) {
  let t = String(text ?? '').trim();
  const fence = t.match(/^```[a-zA-Z0-9]*\s*\n?([\s\S]*?)\n?```$/);
  if (fence) t = fence[1].trim();
  if (!t) throw new Error('内容为空');
  return JSON.parse(t);
}

export function escapeHtml(text) {
  return String(text == null ? '' : text).replace(/[&<>"']/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

export function omrReportHtml(sheet, report, sessionCount) {
  const lines = [];
  lines.push(report.filled
    ? `✓ 读入答题卡 ${report.total} 题，自动填写 <strong>${report.filled}</strong> 题（对 ${report.correct} · 错 ${report.wrong}）。请对着中栏题面核一遍再提交。`
    : `⚠ 读入答题卡 ${report.total} 题，自动填写 <strong>0</strong> 题——没有一题能自动判定，看下面的原因。`);
  if (report.total && report.outOfRange.length === report.total) lines.push(`这张卡上的题号没有一个落在本 Session（共 ${sessionCount} 题）里，多半是 Session 选错了，或者这张卡属于另一次导出。`);
  if (report.missingRow.length) lines.push(`第 ${report.missingRow.join('、')} 题在本 Session 里找不到对应的待录入行，已忽略。`);
  if (report.manual.length) {
    const detail = report.manual.slice(0, 8).map(entry => `第 ${entry.number} 题（${escapeHtml(entry.uid)}）${escapeHtml(entry.reason)}`).join('；');
    const more = report.manual.length > 8 ? `……共 ${report.manual.length} 题` : '';
    lines.push(`⚠ ${report.manual.length} 题没有自动判定，原因已写进各自的备注：${detail}${more}`);
  }
  if (report.skippedRecorded) lines.push(`跳过 ${report.skippedRecorded} 题：本 Session 里已经录过反馈。`);
  if (report.outOfRange.length) lines.push(`⚠ 第 ${report.outOfRange.join('、')} 题超出了本 Session 的题目数（共 ${sessionCount} 题），已忽略。答题卡的行数比 Session 多是正常的；如果不是，检查是不是选错了 Session。`);
  if (sheet.status === 'needs_review') lines.push('这次扫描在 OMR 侧仍是「待复核」。unresolved 题已留给人工；也可先在 OMR 纠错，再重新复制 /result JSON。');
  if (sheet.mode === 'custom') lines.push('这是通用（A/B/C/D）答题卡，纸面只有选项、没有对错，因此一题也无法自动判定。要自动填对错，请用 OMRS 版式的答题卡。');
  // ⚠ 开头的行单独标成警示色（旧页面逐行着色，状态行整体色只反映总体结果）
  return lines.map(line => `<span class="fbw-import__line${line.startsWith('⚠') ? ' is-warn' : ''}">${line}</span>`).join('');
}

/** 答题卡：必须先选中 Session（纸面只有题号，要靠 Session 顺序对上 UID）。 */
export function planOmr(data, session) {
  const sheet = omrReadSheet(data);
  if (sheet.error) return { ok: false, tone: 'danger', html: `✕ ${escapeHtml(sheet.error)}` };
  if (!session) return { ok: false, tone: 'warn', html: '请先在上面选中这张答题卡对应的 Session：答题卡上只有题号，要靠 Session 的题目顺序才能对上 UID。' };
  const sessionUids = sessionUniqueUids(session);
  const rows = fbRowsForSession(session);
  const report = omrApplyToRows(rows, sheet.questions, sessionUids, new Set(fbSessionProgress(session).feedback_uids));
  return { ok: true, tone: report.filled ? 'ok' : 'warn', html: omrReportHtml(sheet, report, sessionUids.length), rows, report };
}

/** 反馈 JSON：带 session_id 且能找到时切到该 Session 并跳过已录入的题；activeId 是导入后应选中的 Session。 */
export function planFeedback(data, findSession) {
  const { rows, skipped, sessionId } = fbImportFeedbackRows(data);
  const matched = sessionId ? findSession(sessionId) : null;
  let finalRows = rows;
  let skippedRecorded = 0;
  if (matched) {
    const pending = new Set(fbSessionProgress(matched).pending_uids);
    finalRows = rows.filter(row => pending.has(row.uid));
    skippedRecorded = rows.length - finalRows.length;
  }
  if (!finalRows.length) return { ok: false, tone: 'warn', html: skippedRecorded ? '导入内容中的题目已全部录入，无需重复提交。' : '没有可导入的作答条目（需要 items: [{uid, is_correct, sub_score}]）' };
  return {
    ok: true, tone: 'ok', rows: finalRows, activeId: sessionId,
    html: `✓ 已导入 ${finalRows.length} 条作答${skipped ? `，跳过 ${skipped} 条无效` : ''}${skippedRecorded ? `，自动跳过 ${skippedRecorded} 条已录入` : ''}。请核对后点「提交反馈」。`,
  };
}

/**
 * 一段文本 → 导入计划。ctx = { session（当前选中的 Session 或 null）, findSession(id), from（'clipboard' 时报错措辞不同）}。
 * 返回 { ok, tone, html, rows?, activeId?, report? }；ok=false 时 rows 不存在，调用方保持原状。
 */
export function planImportText(text, { session = null, findSession = () => null, from = '' } = {}) {
  let data;
  try { data = parseLooseJson(text); }
  catch (error) { return { ok: false, tone: 'danger', html: `✕ ${from === 'clipboard' ? '剪贴板里不是 JSON' : 'JSON 解析失败'}：${escapeHtml(error.message)}` }; }
  const kind = fbPayloadKind(data);
  if (kind === 'questions') return { ok: false, tone: 'warn', html: '这是题目 JSON；题目录入页已不再提供题目 JSON 队列导入。' };
  if (kind === 'feedback') return planFeedback(data, findSession);
  return planOmr(data, session);
}
