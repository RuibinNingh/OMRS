/**
 * 格式化：日期、相对天数、百分比、数字、时长。空值与非法值一律显示「—」。
 * 'YYYY-MM-DD' 字符串按本地日期解析（不按 UTC），与旧页面的日期显示一致。
 */
import { parseDay, daysBetween } from './date.js';
const DASH = '—';
const pad = n => String(n).padStart(2, '0');

export function toDate(value) {
  if (value instanceof Date) return value;
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return parseDay(value) || new Date(NaN);
  }
  return new Date(value);
}

const valid = d => d instanceof Date && !Number.isNaN(d.getTime());

/** kind：date → 2026-09-25；datetime → 2026-09-25 14:05；time → 14:05；short → 9/25 */
export function formatDate(value, kind = 'date') {
  if (value == null || value === '') return DASH;
  const d = toDate(value);
  if (!valid(d)) return DASH;
  const date = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const time = `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return { date, datetime: `${date} ${time}`, time, short: `${d.getMonth() + 1}/${d.getDate()}` }[kind] || date;
}

/** 按自然日比较：今天 / 明天 / 昨天 / N 天后 / N 天前 */
export function relativeDays(value, now = new Date()) {
  if (value == null || value === '') return DASH;
  const d = toDate(value);
  if (!valid(d)) return DASH;
  const days = daysBetween(now, d);
  if (days === 0) return '今天';
  if (days === 1) return '明天';
  if (days === -1) return '昨天';
  return days > 0 ? `${days} 天后` : `${-days} 天前`;
}

/** formatPercent(0.625) → '63%'；ratio:false 时传入的就是百分数 */
export function formatPercent(value, { digits = 0, ratio = true } = {}) {
  const n = Number(value);
  if (value == null || value === '' || !Number.isFinite(n)) return DASH;
  return `${(ratio ? n * 100 : n).toFixed(digits)}%`;
}

/** formatNumber(1284) → '1,284' */
export function formatNumber(value, { digits = 0 } = {}) {
  const n = Number(value);
  if (value == null || value === '' || !Number.isFinite(n)) return DASH;
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** formatDuration(80) → '1 分 20 秒'；只到时分秒 */
export function formatDuration(seconds) {
  const n = Math.round(Number(seconds));
  if (seconds == null || seconds === '' || !Number.isFinite(n) || n < 0) return DASH;
  const h = Math.floor(n / 3600);
  const m = Math.floor((n % 3600) / 60);
  const s = n % 60;
  if (h) return `${h} 小时${m ? ` ${m} 分` : ''}`;
  if (m) return `${m} 分${s ? ` ${s} 秒` : ''}`;
  return `${s} 秒`;
}
