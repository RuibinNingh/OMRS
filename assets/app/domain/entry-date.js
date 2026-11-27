import { businessToday, dayKey, parseDay } from '../core/date.js';

export const ENTRY_DATE_DEFAULTS = Object.freeze({ entryDateMode: '', entryDateFrom: '', entryDateTo: '' });
export const ENTRY_DATE_OPTIONS = [
  { value: '', label: '全部' }, { value: 'today', label: '今天' },
  { value: '7days', label: '最近 7 天' }, { value: '30days', label: '最近 30 天' },
  { value: 'custom', label: '自定义' },
];
export const ENTRY_DATE_SORTS = [['entry-asc', '最早录入优先'], ['entry-desc', '最近录入优先']];
const DAYS = { today: 1, '7days': 7, '30days': 30 };

function calendarDay(value) {
  const text = String(value ?? '').trim();
  if (!/^\d{4}([-\/])\d{1,2}\1\d{1,2}$/.test(text)) return '';
  const date = parseDay(text);
  return date ? dayKey(date) : '';
}

export function entryDateOf(item) {
  const recorded = calendarDay(item.entry_date);
  if (recorded) return recorded;
  const created = String(item.created_at ?? '').trim();
  if (!/^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(created) || !calendarDay(created.slice(0, 10))) return '';
  const instant = new Date(created);
  return Number.isFinite(instant.getTime()) ? dayKey(businessToday(instant)) : '';
}

export function entryDateError({ from, to }) {
  const start = calendarDay(from), end = calendarDay(to);
  if ((from && !start) || (to && !end)) return '请输入有效的日期。';
  if (start && end && start > end) return '开始日期不能晚于结束日期。';
  return '';
}

export function entryDateDraft(filters, draft) {
  if (draft) return draft;
  if (filters.entryDateMode === 'custom') return { from: filters.entryDateFrom, to: filters.entryDateTo };
  return null;
}

/** 只有应用有效范围或切换快捷项才改变结果。 */
export function editEntryDate(filters, draft, field, value) {
  const current = entryDateDraft(filters, draft) ?? { from: '', to: '' };
  if (field === 'mode') {
    if (value === 'custom') return { filters, draft: current };
    if (!ENTRY_DATE_OPTIONS.some(option => option.value === value)) return { filters, draft };
    return { filters: { ...filters, ...ENTRY_DATE_DEFAULTS, entryDateMode: value }, draft: null };
  }
  if (field === 'apply') {
    if (entryDateError(current) || (!current.from && !current.to)) return { filters, draft };
    return { filters: { ...filters, entryDateMode: 'custom',
      entryDateFrom: calendarDay(current.from), entryDateTo: calendarDay(current.to) }, draft: null };
  }
  return { filters, draft: { ...current, [field]: value } };
}

export function entryDateRange(filters, today) {
  const { entryDateMode: mode, entryDateFrom: from = '', entryDateTo: to = '' } = filters;
  if (mode === 'custom' && (from || to) && !entryDateError({ from, to })) {
    return { from: calendarDay(from), to: calendarDay(to) };
  }
  const count = Object.hasOwn(DAYS, mode) ? DAYS[mode] : 0;
  if (!count) return null;
  const first = new Date(today ?? businessToday());
  const last = dayKey(first);
  first.setDate(first.getDate() - count + 1);
  return { from: dayKey(first), to: last };
}

export function normalizeEntryDate(filters) {
  const { entryDateMode: mode, entryDateFrom: from, entryDateTo: to } = filters;
  if (mode === 'custom' && (from || to) && !entryDateError({ from, to })) {
    return { entryDateMode: mode, entryDateFrom: calendarDay(from), entryDateTo: calendarDay(to) };
  }
  return { ...ENTRY_DATE_DEFAULTS, entryDateMode: Object.hasOwn(DAYS, mode) ? mode : '' };
}

export function entryDateChip(filters) {
  const mode = filters.entryDateMode;
  if (mode === 'custom') {
    const { entryDateFrom: from, entryDateTo: to } = filters;
    const range = from && to ? (from === to ? from : `${from} 至 ${to}`) : from ? `${from} 起` : `截至 ${to}`;
    return `录入日期 · ${range}`;
  }
  const label = mode && ENTRY_DATE_OPTIONS.find(option => option.value === mode)?.label;
  return label ? `录入日期 · ${label}` : '';
}

export const sortsByEntryDate = sort => sort === 'entry-asc' || sort === 'entry-desc';
export const showsEntryDate = filters => !!filters.entryDateMode || sortsByEntryDate(filters.sort);

export function filterEntryDates(items, range, sort) {
  const order = sortsByEntryDate(sort);
  if (!range && !order) return items;
  let dated = items.map(item => ({ item, day: entryDateOf(item) }));
  if (range) dated = dated.filter(({ day }) => day && (!range.from || day >= range.from) && (!range.to || day <= range.to));
  if (order) dated.sort((a, b) => {
    if (!a.day || !b.day) {
      if (a.day) return -1;
      if (b.day) return 1;
    }
    if (a.day !== b.day) return sort === 'entry-asc' ? a.day.localeCompare(b.day) : b.day.localeCompare(a.day);
    return String(a.item.uid || '').localeCompare(String(b.item.uid || ''), 'zh-CN');
  });
  return dated.map(({ item }) => item);
}
