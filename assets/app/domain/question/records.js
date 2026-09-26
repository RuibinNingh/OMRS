/**
 * 练习记录（从旧 core.js 迁入）：题目详情 → 记录数组 → 派生统计 → 战绩带。
 * 正式记录是 GET /api/question 的 records[]（Ledger 投影）；只有老后端没给 records 时才解析 Markdown「## 历史」旧行。
 * 输出是字符串，旧代码（题库画廊、展示板画廊）直接拼接；战绩带的高度用 data-h 档位 + 样式表，不写 style=。
 */
import { escape } from '../../core/html.js';

const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };
const clampScore = value => Math.max(0, Math.min(10, num(value, 0)));

/** 'YYYY-MM-DD' / 'YYYY/MM/DD' 按本地日期解析；不合法返回 null（与旧 core.js::parseReviewDate 一致）。 */
export function parseDay(value) {
  if (!value) return null;
  const text = String(value).trim();
  const parts = text.includes('/') ? text.split('/') : text.split('-');
  if (parts.length !== 3) return null;
  const [y, m, d] = parts.map(Number);
  if (![y, m, d].every(Number.isInteger)) return null;
  const date = new Date(y, m - 1, d);
  return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d ? date : null;
}

const HISTORY_LINE_RE = /^(\d{4}-\d{2}-\d{2})\s+主观:(\d+),\s*(对|错)(?:,\s*备注:(.*))?$/;

/** 与后端 parse_history_lines() 同一格式；解析不出的行直接丢掉，不猜。 */
export function parseQHistory(text) {
  return String(text ?? '').split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const m = line.match(HISTORY_LINE_RE);
    return m ? { date: m[1], score: clampScore(m[2]), correct: m[3] === '对', note: (m[4] || '').trim() } : null;
  }).filter(Boolean);
}

/** 详情 → 记录数组（旧 → 新）。records 是数组就以它为准（空数组 = 后端明确说没练过）；返回值带 source。 */
export function qRecordsFromDetail(detail) {
  const raw = detail && detail.records;
  if (Array.isArray(raw)) {
    const list = raw.map(r => ({
      date: String(r?.date || '').slice(0, 10), time: String(r?.time || ''), score: clampScore(r?.score),
      correct: !!r?.correct, note: String(r?.note || '').trim(), session_id: String(r?.session_id || ''),
    })).filter(r => r.date);
    list.source = 'ledger';
    return list;
  }
  const list = parseQHistory((detail && detail.history) || '');
  list.source = 'markdown';
  return list;
}

/** 无记录只返回 {count:0}，调用方据此走空状态，而不是画一张全零的图。 */
export function qHistoryStats(records) {
  const list = Array.isArray(records) ? records : [];
  const count = list.length;
  if (!count) return { count: 0 };
  const correct = list.filter(r => r.correct).length;
  const avgScore = list.reduce((sum, r) => sum + num(r.score, 0), 0) / count;
  let tailWrong = 0;
  for (let i = count - 1; i >= 0 && !list[i].correct; i -= 1) tailWrong += 1;
  const gaps = [];
  for (let i = 1; i < count; i += 1) {
    const prev = parseDay(list[i - 1].date);
    const cur = parseDay(list[i].date);
    if (prev && cur) gaps.push(Math.round((cur - prev) / 86400000));
  }
  return {
    count, correct, wrong: count - correct, rate: Math.round((correct / count) * 100),
    avgScore: Math.round(avgScore * 10) / 10, tailWrong,
    avgGap: gaps.length ? Math.round(gaps.reduce((a, b) => a + b, 0) / gaps.length) : null,
    first: list[0], last: list[count - 1],
  };
}

/** 战绩带：一根竖条一次练习，绿对红错，高度档位 data-h（0–9）编码主观分，左 → 右是时间；更早的淡出。 */
export function qStreakHtml(records, max = 8) {
  const list = (Array.isArray(records) ? records : []).slice(-Math.max(1, num(max, 8)));
  if (!list.length) return '';
  const bars = list.map((record, index) => {
    const level = Math.round((clampScore(record.score) / 10) * 9);
    return `<i class="${record.correct ? 'ok' : 'bad'}${index < list.length - 3 ? ' dim' : ''}" data-h="${level}"></i>`;
  }).join('');
  const title = list.map(r => `${r.date} ${r.correct ? '对' : '错'} ${r.score} 分`).join('；');
  return `<span class="q-streak" title="${escape(title)}" aria-label="最近 ${list.length} 次：${escape(title)}">${bars}</span>`;
}
