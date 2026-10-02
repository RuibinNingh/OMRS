import { questionKey } from '../../domain/question/ref.js';
/**
 * 复习调度 ·「全题库导出」工作区的状态与纯函数（原 assets/export.js 的选题器，规则与文案原样），node 单测全覆盖。
 * 筛选语义与题库共用（旧 getFilterState('pick') + filterItems：默认排除停用题，按熟练度升序）；已选是有序 uid 列表，
 * 题目从题库消失时自动剔除。导出参数：屏幕版始终附带答案；A4 由调用方先问单 / 双栏。
 */
export const emptyExportFilters = () => ({ text: '', subject: '', category: '', tag: '', ktag: '', labels: [], labelMode: 'any',
  diffMin: '', diffMax: '', masteryMin: '', masteryMax: '', sort: 'mastery-asc' });

export const exporter = { filters: emptyExportFilters(), selection: [], view: 'flat', variant: 'a4', answers: false, gap: 0, busy: false, status: null };

export const EXPORT_SORTS = [['mastery-asc', '熟练度 ↑'], ['mastery-desc', '熟练度 ↓'], ['diff-desc', '难度 ↓'], ['diff-asc', '难度 ↑'], ['date-desc', '最近复习优先']];

const n = (v, fallback) => { const x = Number(v); return v === '' || v == null || !Number.isFinite(x) ? fallback : x; };
const pct = v => (v === '' || v == null ? null : Math.max(0, Math.min(100, n(v, 0))) / 100);

/** 页面筛选 → 共享 filterItems 的条件（与旧 getFilterState('pick') 同口径）。 */
export function sharedExportFilters(f) {
  return { text: String(f.text || '').trim().toLowerCase(), subject: f.subject, category: f.category, tag: f.tag, knowledgeTag: f.ktag,
    labels: [...(f.labels || [])], labelMode: f.labelMode || 'any', difficultyMin: n(f.diffMin, 0), difficultyMax: n(f.diffMax, 10) || 10,
    masteryMin: pct(f.masteryMin), masteryMax: pct(f.masteryMax), dueFilter: '', suspended: '', sort: f.sort || 'mastery-asc' };
}

export const filterExport = (items, f, filterAll) => filterAll(items || [], sharedExportFilters(f));

/** 已选里剔除题库里已不存在的 uid（保持原顺序）。 */
export const pruneSelection = (selection, items) => { const have = new Set((items || []).map(questionKey)); return selection.filter(uid => have.has(uid)); };
export const toggleSelection = (selection, uid) => (selection.includes(uid) ? selection.filter(u => u !== uid) : [...selection, uid]);
export function addFiltered(selection, filtered) { const seen = new Set(selection); return [...selection, ...filtered.map(questionKey).filter(uid => !seen.has(uid) && seen.add(uid))]; }
export function removeFiltered(selection, filtered) { const drop = new Set(filtered.map(questionKey)); return selection.filter(uid => !drop.has(uid)); }

export const summary = (filtered, selection) => `已筛出 ${filtered.length} 题，已选择 ${selection.length} 题。`;
export const clampGap = v => { const x = Math.trunc(Number(v)); return Number.isFinite(x) ? Math.max(0, Math.min(20, x)) : 0; };

/** 导出请求体：屏幕版一律附带答案；A4 的单双栏由调用方问过后传入。 */
export function exportPayload({ uids, question_refs, sessionId, variant, answers, gap, twoColumns }) {
  const body = { format: variant, include_answers: variant === 'screen' ? true : !!answers, question_gap_lines: clampGap(gap), a4_two_columns: variant !== 'a4' || !!twoColumns };
  if (sessionId) body.session_id = sessionId; else if (question_refs) body.question_refs = question_refs; else body.uids = [...uids];
  return body;
}
export const exportFileName = ({ sessionId, variant }) => (sessionId ? `OMRS-${sessionId}-${variant}.html` : `OMRS-Export-${variant}.html`);

/** 行的状态标签：已击杀 / 待攻克（去掉 #）。 */
export const statusTag = item => ({ label: String(item.tag || '').replace(/#/g, ''), tone: String(item.tag || '').includes('已击杀') ? 'success' : 'danger' });
