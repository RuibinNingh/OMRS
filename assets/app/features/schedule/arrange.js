/**
 * 复习调度 ·「安排复习」工作区的状态与纯函数（原 assets/recommend_v2.js，规则与文案原样），node 单测全覆盖。
 * - 候选来自 /api/recommend（到期 due + 熟练度 proficiency，带 _source）；筛选语义与题库、导出共用（domain/items 的 filterAll，
 *   即旧 core.js 的 filterItems），推荐排序下恢复服务端顺序，再按推荐方式排：均衡 = 各来源内按科目轮选、到期优先 = 先到期、
 *   薄弱优先 = 先熟练度来源。
 * - 选择是 uid → 候选 的 Map，筛选变化不清空；重拉时去掉已不可安排的题并报数量。
 */
export const FIELDS = [
  ['subject', '科目'], ['text', '搜索'], ['category', '分类'], ['ktag', '知识点'], ['tag', '状态'], ['due', '到期'],
  ['diffMin', '难度 ≥'], ['diffMax', '难度 ≤'], ['masteryMin', '熟练度 ≥'], ['masteryMax', '熟练度 ≤'],
];
export const DUE_OPTIONS = [['', '全部到期状态'], ['overdue', '已逾期'], ['today', '今日到期'], ['3days', '3 天内到期'], ['7days', '7 天内到期'], ['future', '未到期']];
export const SORT_OPTIONS = [['priority', '按推荐方式'], ['mastery-asc', '熟练度从低到高'], ['mastery-desc', '熟练度从高到低'], ['diff-asc', '难度从低到高'],
  ['diff-desc', '难度从高到低'], ['date-desc', '最近复习优先'], ['due-asc', '到期日从近到远'], ['due-desc', '到期日从远到近']];
export const MODE_OPTIONS = [['balanced', '均衡复习'], ['due', '到期优先'], ['weak', '薄弱优先']];
export const VIEW_KEY = 'omrs-schedule-view';

export const emptyFilters = () => ({ subject: '', text: '', mode: 'balanced', category: '', ktag: '', tag: '', due: '', diffMin: '', diffMax: '',
  masteryMin: '', masteryMax: '', sort: 'priority', labelMode: 'any', labels: [] });

export const arrange = {
  data: null, selected: new Map(), onlySelected: false, loading: false, error: '', submitting: false, notice: '',
  view: 'list', filters: emptyFilters(), target: '10', more: false, seq: 0,
};

export function readView(storage) { try { return storage?.getItem(VIEW_KEY) === 'gallery' ? 'gallery' : 'list'; } catch (error) { return 'list'; } }
export function writeView(storage, view) { try { storage?.setItem(VIEW_KEY, view); } catch (error) { /* 隐私模式 */ } }

const num = (value, fallback) => (value === '' || value == null ? fallback : Number(value));

/** 页面筛选 → 共享 filterItems 的条件（熟练度仍是 0–100 的百分数，filterCandidates 里再换算）。 */
export function sharedFilters(f) {
  return { text: String(f.text || '').trim().toLowerCase(), subject: f.subject, category: f.category, tag: f.tag, knowledgeTag: f.ktag,
    labels: [...(f.labels || [])], labelMode: f.labelMode || 'any', difficultyMin: num(f.diffMin, 1), difficultyMax: num(f.diffMax, 10),
    masteryMin: num(f.masteryMin, null), masteryMax: num(f.masteryMax, null), dueFilter: f.due, suspended: '', sort: f.sort || 'priority' };
}

export function filterError(sf) {
  if (sf.difficultyMin < 1 || sf.difficultyMax > 10 || sf.difficultyMin > sf.difficultyMax) return '难度范围应为 1–10，且下限不能大于上限。';
  const bad = v => v != null && (v < 0 || v > 100);
  if (bad(sf.masteryMin) || bad(sf.masteryMax) || (sf.masteryMin != null && sf.masteryMax != null && sf.masteryMin > sf.masteryMax)) return '熟练度范围应为 0–100%，且下限不能大于上限。';
  return '';
}

export function roundRobin(items) {
  const groups = new Map();
  for (const item of items) {
    const key = item.subject || '未分类';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  }
  const result = [];
  for (let i = 0; result.length < items.length; i += 1) for (const group of groups.values()) if (group[i]) result.push(group[i]);
  return result;
}

export function orderItems(items, mode) {
  const due = items.filter(i => i._source === 'due');
  const prof = items.filter(i => i._source !== 'due');
  if (mode === 'weak') return [...prof, ...due];
  if (mode === 'balanced') return [...roundRobin(due), ...roundRobin(prof)];
  return [...due, ...prof];
}

/** 候选筛选与排序；filterAll 是共享筛选（旧 filterItems）。条件不合法时返回空。 */
export function filterCandidates(items, f, filterAll) {
  const sf = sharedFilters(f);
  if (filterError(sf)) return [];
  const list = items || [];
  const result = filterAll(list, { ...sf, masteryMin: sf.masteryMin == null ? null : sf.masteryMin / 100, masteryMax: sf.masteryMax == null ? null : sf.masteryMax / 100 });
  if (sf.sort !== 'priority') return result;
  const rank = new Map(list.map((item, i) => [item.uid, i]));
  return orderItems([...result].sort((a, b) => rank.get(a.uid) - rank.get(b.uid)), f.mode);
}

/** /api/recommend 的响应 → 带来源的候选；已选里不再可安排的去掉，其余换成新对象。 */
export function mergeLoaded(raw, selected) {
  const data = [...(raw?.due || []).map(i => ({ ...i, _source: 'due' })), ...(raw?.proficiency || []).map(i => ({ ...i, _source: 'proficiency' }))];
  const available = new Map(data.map(i => [i.uid, i]));
  const next = new Map();
  let removed = 0;
  for (const uid of selected.keys()) {
    if (available.has(uid)) next.set(uid, available.get(uid));
    else removed += 1;
  }
  return { data, selected: next, removed };
}

/** 选题理由：复燃 → 熟练度来源 → 到期天数。 */
export function reason(item, days) {
  if (item.is_revived) return `复燃 · 已休眠 ${Number(item.dormant_days) || 0} 天`;
  if (item._source === 'proficiency') return `提前巩固${days == null ? '' : ` · ${days} 天后到期`}`;
  if (days == null) return '待安排复习';
  return days < 0 ? `已逾期 ${-days} 天` : days === 0 ? '今日到期' : `${days} 天后到期`;
}
/** 复燃标识：停用题不算复燃；第几次击杀大于 1 时带 ×N。 */
export function revive(item) {
  if (!item?.is_revived || item.suspended) return null;
  const count = Number(item.kill_count) || 0;
  const dormant = Number(item.dormant_days) || 0;
  return { label: `复燃${count > 1 ? ` ×${count}` : ''}`, title: `第 ${count || 1} 次击杀后休眠 ${dormant} 天复燃${item.next_revive_date ? ` · 原定 ${item.next_revive_date}` : ''}` };
}

/** 已生效的筛选 → 可单独移除的 chip。 */
export function chips(f) {
  const dueLabel = Object.fromEntries(DUE_OPTIONS);
  const out = FIELDS.filter(([key]) => f[key] !== '' && f[key] != null)
    .map(([key, label]) => ({ key, label: `${label} ${key === 'due' ? dueLabel[f.due] || f.due : f[key]}` }));
  (f.labels || []).forEach(name => out.push({ key: `label:${name}`, label: `标记 ${name}` }));
  return out;
}

export function clearField(f, key) {
  if (key.startsWith('label:')) return { ...f, labels: f.labels.filter(n => n !== key.slice(6)) };
  return { ...f, [key]: '' };
}
export const resetFilters = f => ({ ...emptyFilters(), mode: f.mode });

/** 按建议选择：当前结果的前 n 题替换已选；n 必须是正整数，否则返回 null。 */
export function smartPick(filtered, n) {
  const k = Number(n);
  if (!Number.isInteger(k) || k < 1) return null;
  return new Map(filtered.slice(0, k).map(i => [i.uid, i]));
}
export const estimateMinutes = items => items.reduce((sum, i) => sum + Math.max(3, Math.round((Number(i.difficulty) || 5) * 1.5)), 0);
export const hiddenSelected = (selected, filtered) => { const shown = new Set(filtered.map(i => i.uid)); return [...selected.keys()].filter(uid => !shown.has(uid)).length; };

/** 候选区为空时的提示与主操作（'plans' 查看已有计划 / 'reset' 清除筛选 / null）。 */
export function emptyState(a, problem, activePlans) {
  let title = a.loading ? '正在读取可安排的题目…' : a.error ? '未能更新推荐，请重试。'
    : problem || (a.onlySelected ? '当前筛选内没有已选题。可关闭「只看已选」或清除筛选。' : a.data?.length ? '没有符合这些条件的题目，试试放宽筛选。' : '目前没有可安排的新题。');
  const noData = !a.loading && !a.error && !a.data?.length;
  if (noData && activePlans) title += ` 还有 ${activePlans} 个计划待完成，可以接着复习。`;
  const action = a.loading || a.error ? null : noData && activePlans ? 'plans' : 'reset';
  return { title, action };
}
