/** 日历日期统一入口：严格解析，按日序号求天差；业务今天使用 Asia/Shanghai。 */
export const BUSINESS_TIME_ZONE = 'Asia/Shanghai';

export function parseDay(value) {
  if (!value) return null;
  const parts = String(value).trim().split(/[-/]/).map(Number);
  if (parts.length !== 3 || !parts.every(Number.isInteger)) return null;
  const [year, month, day] = parts;
  const date = new Date(year, month - 1, day);
  return date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day ? date : null;
}

export function dayNumber(value) {
  const date = value instanceof Date ? value : parseDay(value);
  if (!date || Number.isNaN(date.getTime())) return null;
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / 86400000;
}

export function daysBetween(from, to) {
  const a = dayNumber(from), b = dayNumber(to);
  return a === null || b === null ? null : b - a;
}

export function businessToday(now = new Date(), timeZone = BUSINESS_TIME_ZONE) {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: 'numeric', day: 'numeric' }).formatToParts(now);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return new Date(Number(values.year), Number(values.month) - 1, Number(values.day));
}

export function dayKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
