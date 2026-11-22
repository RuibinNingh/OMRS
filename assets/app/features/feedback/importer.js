import { sessionEntries, sessionEntryKey, entryFeedbackState, feedbackStateLabel } from '../../domain/sessions.js';
/**
 * 反馈录入的「导入」：一段文本（剪贴板 / 粘贴 / 文本框）→ 解析 → 分流 → 算出新的行与状态报告。
 * 纯函数，不碰 DOM 与旧全局：Session 通过参数传入，结果由 index.js 的控制器落到 state 上。
 * 三个入口（读剪贴板按钮、页面空白处 Ctrl/⌘+V、「导入 JSON」按钮）走同一个 planImportText()。
 * 协议细节见 AI/omr-import.md；node 侧由 tests/app/feedback.test.mjs 覆盖（原 smoke_feedback_omr_import.js 的全部断言迁来）。
 */
import {
  sessionUniqueUids, fbSessionProgress,
  omrReadSheet, omrApplyToRows, fbImportFeedbackRows, fbPayloadKind, mergeSessionRows,
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
  if (report.skippedRecorded) lines.push(`已录 ${report.skippedRecorded} 题，已经录过反馈，保留原记录。`);
  for (const kind of ['skipped', 'unavailable', 'unresolved']) {
    if (report[kind].length) lines.push(`${feedbackStateLabel[kind]} ${report[kind].length} 题（原题号 ${report[kind].join('、')}）。`);
  }
  if (report.outOfRange.length) lines.push(`⚠ 第 ${report.outOfRange.join('、')} 题超出了本 Session 的题目数（共 ${sessionCount} 题），已忽略。答题卡的行数比 Session 多是正常的；如果不是，检查是不是选错了 Session。`);
  if (sheet.status === 'needs_review') lines.push('这次扫描在 OMR 侧仍是「待复核」。unresolved 题已留给人工；也可先在 OMR 纠错，再重新复制 /result JSON。');
  if (sheet.mode === 'custom') lines.push('这是通用（A/B/C/D）答题卡，纸面只有选项、没有对错，因此一题也无法自动判定。要自动填对错，请用 OMRS 版式的答题卡。');
  // ⚠ 开头的行单独标成警示色（旧页面逐行着色，状态行整体色只反映总体结果）
  return lines.map(line => `<span class="fbw-import__line${line.startsWith('⚠') ? ' is-warn' : ''}">${line}</span>`).join('');
}

/** 答题卡：必须先选中 Session（纸面只有题号，要靠 Session 顺序对上 UID）。 */
export function planOmr(data, session, drafts = []) {
  const sheet = omrReadSheet(data);
  if (sheet.error) return { ok: false, tone: 'danger', html: `✕ ${escapeHtml(sheet.error)}` };
  if (!session) return { ok: false, tone: 'warn', html: '请先在上面选中这张答题卡对应的 Session：答题卡上只有题号，要靠 Session 的题目顺序才能对上 UID。' };
  const sessionUids = sessionUniqueUids(session);
  const rows = mergeSessionRows(session, drafts.map(row => ({ ...row })));
  const report = omrApplyToRows(rows, sheet.questions, sessionEntries(session), new Set(fbSessionProgress(session).feedback_uids));
  return { ok: session.status !== 'completed' && session.status !== 'paused', tone: report.filled ? 'ok' : 'warn',
    html: session.status === 'paused' ? '计划已暂停，请恢复后导入。' : omrReportHtml(sheet, report, sessionUids.length), rows, report };
}

/** 先按原题号或明确的身份找到条目，再检查处置。UID 不唯一时交给人工核对。 */
export function planFeedback(data, findSession, current = null) {
  const { rows, skipped, sessionId } = fbImportFeedbackRows(data);
  const usesOrdinal = rows.some(row => row.number || row.entry_id);
  const matched = sessionId ? findSession(sessionId) : usesOrdinal ? current : null;
  const report = { recorded: 0, skipped: 0, unavailable: 0, unresolved: 0, unmatched: 0 };
  let candidates = rows;
  if (matched) {
    const entries = sessionEntries(matched);
    const seen = new Set();
    candidates = rows.flatMap(row => {
      let matches = entries;
      if (row.number) matches = matches.filter((entry, index) => index + 1 === row.number);
      if (row.entry_id) matches = matches.filter(entry => entry.entry_id === row.entry_id);
      if (row.question_id) matches = matches.filter(entry => entry.question_id === row.question_id);
      if (row.uid) matches = matches.filter(entry => [entry.uid, entry.uid_at_creation].includes(row.uid));
      const entry = matches.length === 1 ? matches[0] : null;
      if (!entry || seen.has(sessionEntryKey(entry))) { report.unmatched++; return []; }
      const kind = entryFeedbackState(entry);
      if (kind !== 'pending') { report[kind]++; return []; }
      if (matched.status === 'paused' || matched.status === 'completed') return [];
      seen.add(sessionEntryKey(entry));
      return [{ ...row, ...entry, uid: entry.uid || entry.uid_at_creation || '', number: entries.indexOf(entry) + 1 }];
    });
  } else if (usesOrdinal || (sessionId && !sessionId.startsWith('TMP-'))) {
    return { ok: false, tone: 'warn', html: '找不到对应复习计划，请选择原计划并核对题号后导入。' };
  }
  const reasons = Object.keys(feedbackStateLabel).filter(kind => report[kind])
    .map(kind => `${feedbackStateLabel[kind]} ${report[kind]} 条`);
  if (report.unmatched) reasons.push(`无法匹配原条目 ${report.unmatched} 条`);
  if (skipped) reasons.unshift(`跳过 ${skipped} 条无效`);
  const detail = reasons.length ? `，${reasons.join('，')}` : '';
  if (!candidates.length) {
    const message = matched?.status === 'paused' ? '计划已暂停，请恢复后导入'
      : matched?.status === 'completed' ? '计划已结束'
      : report.recorded === rows.length && rows.length ? '导入内容中的题目已全部录入' : '没有可导入的作答条目';
    return { ok: false, tone: 'warn', html: `${message}${detail}。`, report };
  }
  return { ok: true, tone: 'ok', rows: candidates, activeId: matched?.session_id || '',
    html: `✓ 已导入 ${candidates.length} 条作答${detail}。请核对后点「提交反馈」。`, report };
}

/**
 * 一段文本 → 导入计划。ctx = { session（当前选中的 Session 或 null）, findSession(id), from（'clipboard' 时报错措辞不同）}。
 * 返回 { ok, tone, html, rows?, activeId?, report? }；ok=false 时 rows 不存在，调用方保持原状。
 */
export function planImportText(text, { session = null, findSession = () => null, drafts = [], from = '' } = {}) {
  let data;
  try { data = parseLooseJson(text); }
  catch (error) { return { ok: false, tone: 'danger', html: `✕ ${from === 'clipboard' ? '剪贴板里不是 JSON' : 'JSON 解析失败'}：${escapeHtml(error.message)}` }; }
  const kind = fbPayloadKind(data);
  if (kind === 'questions') return { ok: false, tone: 'warn', html: '这是题目 JSON；题目录入页已不再提供题目 JSON 队列导入。' };
  if (kind === 'feedback') return planFeedback(data, findSession, session);
  return planOmr(data, session, drafts);
}

export function buildFeedbackAiPrompt(activeId, rows, items) {
  const selected = rows.filter(row => entryFeedbackState(row) === 'pending' && (row.uid || '').trim());
  const sessionLine = activeId ? `当前 Session_ID：${activeId}` : '当前未选择 Session；如果我没有另行说明，请输出空 session_id。';
  const scoped = selected.length
    ? selected.map((row, i) => `${row.number || i + 1}. ${row.uid}`).join('\n')
    : items.slice(0, 200).map((item, i) => `${i + 1}. ${item.uid}（${item.subject || ''}/${item.category || ''}）`).join('\n');
  return [
    '你是 OMRS 错题复习反馈整理助手。我会给你一份纸面批改结果、口述复盘、表格或截图内容。请只把它整理成 OMRS 可导入的反馈 JSON，不要解释。', '',
    '规则：',
    '1. 每条反馈必须对应一个准确 UID；如果无法确定 UID，就不要输出该条。',
    '2. is_correct 只能是 true 或 false。答对/全对/正确=true；答错/错误/不会/漏做=false。',
    '3. sub_score 是 0-10 的整数。未给分时：答对默认 10，答错默认 4；明显完全不会可给 0-2。',
    '4. note 写简短备注，如页码、错因、计算失误；没有就空字符串。',
    '5. 只输出一个 JSON 对象，可被 JSON.parse 直接解析。不要 Markdown 代码块，不要多余文字。', '',
    sessionLine, '', '可用 UID 清单：', scoped || '（暂无预置 UID；请按我提供的 UID 输出）', '',
    '输出格式：', '{"type":"omrs-feedback","version":1,"session_id":"","items":[{"uid":"","is_correct":true,"sub_score":10,"note":""}]}',
  ].join('\n');
}
