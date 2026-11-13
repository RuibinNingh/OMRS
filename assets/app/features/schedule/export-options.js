/** 两处导出共用的参数契约；只在成功下载后记忆，取消不覆盖上次设置。 */
export const EXPORT_OPTIONS_KEY = 'omrs-export-options-v1';
export const DEFAULT_EXPORT_OPTIONS = Object.freeze({
  variant: 'a4', twoColumns: true, answers: false, gap: 0,
  historyPosition: 'feedback', historyLimit: 8, historyScores: true, historyDates: true,
});
let remembered = { ...DEFAULT_EXPORT_OPTIONS };

const integer = (value, fallback, max, min = 0) => {
  const n = value === '' || value == null ? NaN : Number(value);
  return Number.isFinite(n) ? Math.max(min, Math.min(max, Math.trunc(n))) : fallback;
};
const bool = (value, fallback) => typeof value === 'boolean' ? value : fallback;

export function normalizeExportOptions(value = {}) {
  const v = value && typeof value === 'object' ? value : {};
  const d = DEFAULT_EXPORT_OPTIONS;
  return {
    variant: v.variant === 'screen' ? 'screen' : 'a4',
    twoColumns: bool(v.twoColumns, d.twoColumns), answers: bool(v.answers, d.answers),
    gap: integer(v.gap, d.gap, 20),
    historyPosition: ['none', 'question', 'feedback'].includes(v.historyPosition) ? v.historyPosition : d.historyPosition,
    historyLimit: integer(v.historyLimit, d.historyLimit, 16, 1),
    historyScores: bool(v.historyScores, d.historyScores), historyDates: bool(v.historyDates, d.historyDates),
  };
}

export function loadExportOptions() {
  try {
    const raw = globalThis.localStorage?.getItem(EXPORT_OPTIONS_KEY);
    if (raw) remembered = normalizeExportOptions(JSON.parse(raw));
  } catch (_) { /* 存储受限或损坏时仍可导出，沿用本次打开期间的设置。 */ }
  return { ...remembered };
}

export function saveExportOptions(options) {
  remembered = normalizeExportOptions(options);
  try {
    if (!globalThis.localStorage) return false;
    globalThis.localStorage.setItem(EXPORT_OPTIONS_KEY, JSON.stringify(remembered));
    return true;
  } catch (_) { return false; }
}

export function historyOptions(options) {
  const o = normalizeExportOptions(options);
  return { position: o.historyPosition, limit: o.historyLimit, scores: o.historyScores, dates: o.historyDates };
}
