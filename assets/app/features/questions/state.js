/**
 * 题库页状态：模块单例 + 纯函数（tests/app/questions.test.mjs 全覆盖）。
 * - filters 是页面自己的数据，不读 DOM；toItemFilters() 翻成旧 core.js filterItems() 的条件形状，全站筛选语义不变。
 * - live 是双滑块拖动中的预览值（只更新命中数与滑块文案），松手才并进 filters 重排列表。
 * - prefs（视图、列、密度、画廊列数、战绩带、元数据）存 localStorage，键名沿用旧版，升级后偏好不丢。
 * - 视图预设与仪表盘跳转预设沿用旧格式：字段以旧元素 id（q-search、q-filter-subj…）为键，旧版存下的视图照样能用。
 * - 题面换行（简略 / 完整）是 qview 的显示偏好，归 domain/question/markdown.js。
 */
export const FILTER_DEFAULTS = Object.freeze({
  text: '', subject: '', category: '', ktag: '', labels: Object.freeze([]), labelMode: 'any',
  diffMin: 1, diffMax: 10, masteryMin: 0, masteryMax: 100, due: '', tag: '', suspended: '', sort: 'mastery-asc',
});
export const defaultFilters = () => ({ ...FILTER_DEFAULTS, labels: [] });

export const FIELD_IDS = Object.freeze({
  'q-search': 'text', 'q-filter-subj': 'subject', 'q-filter-category': 'category', 'q-filter-tag': 'tag',
  'q-filter-ktag': 'ktag', 'q-filter-due': 'due', 'q-filter-suspended': 'suspended', 'q-filter-diff-min': 'diffMin',
  'q-filter-diff-max': 'diffMax', 'q-filter-mastery-min': 'masteryMin', 'q-filter-mastery-max': 'masteryMax',
  'q-label-mode': 'labelMode', 'q-sort': 'sort',
});
export const RANGES = Object.freeze({ diff: { lo: 'diffMin', hi: 'diffMax', min: 1, max: 10, step: 1 }, mastery: { lo: 'masteryMin', hi: 'masteryMax', min: 0, max: 100, step: 5 } });

export const SORTS = [['mastery-asc', '熟练度 ↑'], ['mastery-desc', '熟练度 ↓'], ['due-asc', '到期日 ↑'], ['due-desc', '到期日 ↓'],
  ['diff-desc', '难度 ↓'], ['diff-asc', '难度 ↑'], ['date-desc', '最近复习优先']];
export const DUE_OPTIONS = [['', '全部'], ['overdue', '逾期'], ['today', '今日'], ['3days', '3 天'], ['7days', '7 天'], ['future', '未到期']];
export const TAG_OPTIONS = [['', '全部'], ['待攻克', '待攻克'], ['已击杀', '已击杀'], ['易错', '易错坑']];
export const SUSPENDED_OPTIONS = [['', '活动'], ['suspended', '仅停用'], ['all', '全部']];
export const DUE_LABELS = { overdue: '逾期', today: '今日到期', '3days': '3 天内到期', '7days': '7 天内到期', future: '未到期' };
export const SUSPENDED_LABELS = { suspended: '仅停用题目', all: '含停用题目' };

export const COLUMN_ORDER = ['select', 'main', 'labels', 'mastery', 'due', 'status', 'difficulty', 'decayed', 'attempts', 'last_review', 'ef', 'actions'];
export const DEFAULT_COLUMNS = ['select', 'main', 'labels', 'mastery', 'due', 'status', 'actions'];
export const FIXED_COLUMNS = ['select', 'main', 'actions'];
export const COLUMN_LABELS = { select: '选择', main: 'UID / 题目', labels: '标记', mastery: '熟练度', due: '到期', status: '状态', difficulty: '难度', decayed: '衰减后', attempts: '次数', last_review: '上次复习', ef: 'EF', actions: '操作' };
export const OPTIONAL_COLUMNS = COLUMN_ORDER.filter(key => !FIXED_COLUMNS.includes(key));

export const PREF_KEYS = Object.freeze({ view: 'omrs-q-view', density: 'omrs-qb-density', galleryDetail: 'omrs-qb-gallery-detail', streak: 'omrs-qb-streak', galleryCols: 'omrs-qb-gallery-cols', columns: 'omrs-qb-columns' });
export const VIEWS_KEY = 'omrs-question-views';

export const defaultPrefs = () => ({ view: 'table', density: 'comfortable', galleryDetail: false, streak: true, galleryCols: 0, columns: null });

export const state = { filters: defaultFilters(), live: null, quick: '', prefs: defaultPrefs(), selected: new Set(), cursor: '', drawer: false, menu: false, loaded: false };

const num = (value, fallback) => { const n = Number(value); return value === '' || value == null || !Number.isFinite(n) ? fallback : n; };
const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

// ── 偏好 ──
export function clampCols(value) { const n = Math.round(Number(value)); return Number.isFinite(n) ? clamp(n, 0, 6) : 0; }
const readKey = (storage, key) => { try { return storage ? storage.getItem(key) : null; } catch (error) { return null; } };
export function readPrefs(storage) {
  const prefs = defaultPrefs();
  prefs.view = readKey(storage, PREF_KEYS.view) === 'gallery' ? 'gallery' : 'table';
  prefs.density = readKey(storage, PREF_KEYS.density) === 'compact' ? 'compact' : 'comfortable';
  prefs.galleryDetail = readKey(storage, PREF_KEYS.galleryDetail) === '1';
  prefs.streak = readKey(storage, PREF_KEYS.streak) !== '0';
  prefs.galleryCols = clampCols(readKey(storage, PREF_KEYS.galleryCols));
  try {
    const cols = JSON.parse(readKey(storage, PREF_KEYS.columns) || 'null');
    prefs.columns = Array.isArray(cols) ? cols.filter(key => COLUMN_ORDER.includes(key)) : null;
  } catch (error) { prefs.columns = null; }
  return prefs;
}
export function writePrefs(storage, prefs) {
  const put = (key, value) => { try { if (value == null) storage?.removeItem(key); else storage?.setItem(key, value); } catch (error) { /* 隐私模式等：偏好只在本次会话生效 */ } };
  put(PREF_KEYS.view, prefs.view === 'gallery' ? 'gallery' : 'table');
  put(PREF_KEYS.density, prefs.density === 'compact' ? 'compact' : 'comfortable');
  put(PREF_KEYS.galleryDetail, prefs.galleryDetail ? '1' : '0');
  put(PREF_KEYS.streak, prefs.streak ? '1' : '0');
  put(PREF_KEYS.galleryCols, String(clampCols(prefs.galleryCols)));
  put(PREF_KEYS.columns, Array.isArray(prefs.columns) ? JSON.stringify(prefs.columns) : null);
}
/** 「恢复默认显示」：视图（表格 / 画廊）保留，其余回到默认。 */
export const resetLayout = prefs => ({ ...defaultPrefs(), view: prefs.view });

/** 可见列（Set，保持插入顺序）：勾选、主列、操作三列恒在。 */
export function visibleColumns(columns) {
  const set = new Set(Array.isArray(columns) ? columns : DEFAULT_COLUMNS);
  FIXED_COLUMNS.forEach(key => set.add(key));
  return set;
}
export const columnList = columns => { const set = visibleColumns(columns); return COLUMN_ORDER.filter(key => set.has(key)); };
export function toggleColumn(columns, key, on) {
  const set = visibleColumns(columns);
  if (FIXED_COLUMNS.includes(key)) return [...set];
  if (on) set.add(key); else set.delete(key);
  return [...set];
}
/** 画廊列数步进（[ / ]）：0 是自动，从自动往下调先落到 6，往上调落到 1。 */
export const stepCols = (cols, step) => clampCols(cols === 0 ? (step > 0 ? 1 : 6) : cols + step);

// ── 筛选 ──
export function withLive(filters, live) { return live ? { ...filters, ...live } : filters; }
export function toItemFilters(filters) {
  const f = filters || FILTER_DEFAULTS;
  return {
    text: String(f.text || '').trim().toLowerCase(), subject: f.subject || '', category: f.category || '', tag: f.tag || '',
    knowledgeTag: f.ktag || '', labels: [...(f.labels || [])], labelMode: f.labelMode === 'all' ? 'all' : 'any',
    difficultyMin: num(f.diffMin, 1), difficultyMax: num(f.diffMax, 10) || 10,
    masteryMin: num(f.masteryMin, 0) / 100, masteryMax: num(f.masteryMax, 100) / 100,
    dueFilter: f.due || '', suspended: f.suspended || '', sort: f.sort || 'mastery-asc',
  };
}
/** 「用户设了什么」：入参是 filterItems 形状；滑块在两端、下拉为空都算未设。每项带 kind 供 clearFilter 撤销。 */
export function activeFilters(filters) {
  const f = filters || {};
  const out = [];
  if (f.text) out.push({ kind: 'text', label: `搜索：${f.text}` });
  if (f.subject) out.push({ kind: 'subject', label: `科目：${f.subject}` });
  if (f.category) out.push({ kind: 'category', label: `分类：${f.category}` });
  if (f.knowledgeTag) out.push({ kind: 'ktag', label: `知识点：${f.knowledgeTag}` });
  (f.labels || []).forEach(name => out.push({ kind: 'label', label: '', chip: name, value: name }));
  if ((f.labels || []).length > 1 && f.labelMode === 'all') out.push({ kind: 'labelMode', label: '标记：全部命中' });
  const dMin = num(f.difficultyMin, 1), dMax = num(f.difficultyMax, 10) || 10;
  if (dMin > 1 || dMax < 10) out.push({ kind: 'diff', label: `难度 ${dMin}–${dMax}` });
  const mMin = f.masteryMin == null ? 0 : f.masteryMin, mMax = f.masteryMax == null ? 1 : f.masteryMax;
  if (mMin > 0 || mMax < 1) out.push({ kind: 'mastery', label: `熟练度 ${Math.round(mMin * 100)}–${Math.round(mMax * 100)}%` });
  if (f.dueFilter) out.push({ kind: 'due', label: `到期：${DUE_LABELS[f.dueFilter] || f.dueFilter}` });
  if (f.tag) out.push({ kind: 'tag', label: `状态：${f.tag === '易错' ? '易错坑' : f.tag}` });
  if (f.suspended) out.push({ kind: 'suspended', label: `题目：${SUSPENDED_LABELS[f.suspended] || f.suspended}` });
  return out;
}
export const filterCount = filters => activeFilters(filters).length;

export function resetFilters(filters, keepSearch = false) {
  return { ...defaultFilters(), sort: filters?.sort || FILTER_DEFAULTS.sort, text: keepSearch ? (filters?.text || '') : '' };
}
export function clearFilter(filters, kind, value) {
  if (kind === 'all') return resetFilters(filters);
  const next = { ...filters, labels: [...(filters.labels || [])] };
  if (kind === 'label') next.labels = next.labels.filter(name => name !== value);
  else if (kind === 'diff') { next.diffMin = 1; next.diffMax = 10; }
  else if (kind === 'mastery') { next.masteryMin = 0; next.masteryMax = 100; }
  else if (kind in FILTER_DEFAULTS) next[kind] = FILTER_DEFAULTS[kind];
  return next;
}
export function toggleLabel(filters, name) {
  const labels = filters.labels.includes(name) ? filters.labels.filter(n => n !== name) : [...filters.labels, name];
  return { ...filters, labels };
}
/** 双滑块：保证 lo ≤ hi（拖的是哪一头就推动另一头），返回并进 filters 的片段。 */
export function rangeValues(kind, lo, hi, moved) {
  const r = RANGES[kind];
  let a = clamp(num(lo, r.min), r.min, r.max), b = clamp(num(hi, r.max), r.min, r.max);
  if (a > b) { if (moved === 'lo') b = a; else a = b; }
  return { [r.lo]: a, [r.hi]: b };
}

// ── 计数条快捷筛选：一键切到「逾期 / 待攻克 / 顽固题 / 停用」，再点一次取消 ──
export function applyQuick(filters, current, key) {
  const next = resetFilters(filters, true);
  if (current === key) return { filters: next, quick: '' };
  if (key === 'overdue') next.due = 'overdue';
  else if (key === 'attack') next.tag = '待攻克';
  else if (key === 'suspended') next.suspended = 'suspended';
  else if (key === 'leech') next.sort = 'mastery-asc';
  return { filters: next, quick: key };
}
/** 顽固题没有对应筛选字段，filterItems 之后再过一遍。 */
export const postFilter = (items, quick) => (quick === 'leech' ? items.filter(item => item.is_leech) : items);
/** 改了搜索 / 排序 / 下拉之后快捷筛选失效；顽固题是后置过滤，与这些条件可以叠加，保留。 */
export const quickAfterEdit = quick => (quick === 'leech' ? 'leech' : '');

export function countsOf(all, dueDays) {
  const active = all.filter(item => !item.suspended);
  return {
    total: all.length,
    overdue: active.filter(item => { const d = dueDays(item); return d != null && d < 0; }).length,
    attack: active.filter(item => String(item.tag || '').includes('待攻克')).length,
    leech: active.filter(item => item.is_leech).length,
    suspended: all.length - active.length,
  };
}

// ── 预设（仪表盘跳转、视图预设）：旧元素 id 为键 ──
export function filtersFromFields(fields, labels) {
  const f = defaultFilters();
  Object.entries(fields || {}).forEach(([id, value]) => {
    const key = FIELD_IDS[id];
    if (!key) return;
    if (['diffMin', 'diffMax', 'masteryMin', 'masteryMax'].includes(key)) {
      const r = key.startsWith('diff') ? RANGES.diff : RANGES.mastery;
      f[key] = clamp(num(value, FILTER_DEFAULTS[key]), r.min, r.max);
    } else if (key === 'labelMode') f.labelMode = value === 'all' ? 'all' : 'any';
    else if (key === 'sort') f.sort = SORTS.some(([v]) => v === value) ? value : FILTER_DEFAULTS.sort;
    else f[key] = String(value ?? '');
  });
  f.labels = [...new Set((labels || []).filter(Boolean).map(String))];
  return f;
}
export const fieldsFromFilters = f => Object.fromEntries(Object.entries(FIELD_IDS).map(([id, key]) => [id, String(f[key] ?? '')]));
const normalized = f => { const x = filtersFromFields(fieldsFromFilters(f), f.labels); x.labels = [...x.labels].sort(); return JSON.stringify(x); };
export const sameFilters = (a, b) => normalized(a) === normalized(b);

export function snapshot(filters, prefs, mdMode) {
  return {
    fields: fieldsFromFilters(filters), labels: [...filters.labels], view: prefs.view, columns: [...visibleColumns(prefs.columns)],
    density: prefs.density, galleryCols: prefs.galleryCols, galleryDetail: prefs.galleryDetail, streak: prefs.streak, mdMode: mdMode || 'lean',
  };
}
export function applySnapshot(view, prefs) {
  const v = view || {};
  const next = { ...prefs };
  if (v.view === 'gallery' || v.view === 'table') next.view = v.view;
  if (Array.isArray(v.columns)) next.columns = v.columns.filter(key => COLUMN_ORDER.includes(key));
  if (v.density) next.density = v.density === 'compact' ? 'compact' : 'comfortable';
  if (v.galleryCols != null) next.galleryCols = clampCols(v.galleryCols);
  if (v.galleryDetail != null) next.galleryDetail = !!v.galleryDetail;
  if (v.streak != null) next.streak = !!v.streak;
  return { filters: filtersFromFields(v.fields, v.labels), prefs: next, mdMode: v.mdMode ? (v.mdMode === 'full' ? 'full' : 'lean') : null };
}
export function readViews(storage) {
  try { const v = JSON.parse(readKey(storage, VIEWS_KEY) || '{}'); return v && typeof v === 'object' && !Array.isArray(v) ? v : {}; } catch (error) { return {}; }
}
export function writeViews(storage, views) { try { storage?.setItem(VIEWS_KEY, JSON.stringify(views)); } catch (error) { /* 同上 */ } }
export const currentViewName = (views, filters) => Object.entries(views || {}).find(([, v]) => sameFilters(filtersFromFields(v.fields, v.labels), filters))?.[0] || '';
export function describeView(view) {
  const f = filtersFromFields(view?.fields, view?.labels);
  const bits = [f.subject, f.category, f.labels.length ? `标记 ${f.labels.join('/')}` : '', f.due ? (DUE_LABELS[f.due] || f.due) : '', f.tag].filter(Boolean);
  return bits.join(' · ') || '无筛选条件';
}

// ── 选择与光标 ──
export function selectionOf(selected, uids) {
  const n = uids.filter(uid => selected.has(uid)).length;
  return { count: selected.size, all: uids.length > 0 && n === uids.length, some: n > 0 && n < uids.length };
}
export function toggleAll(selected, uids, on) {
  const next = new Set(selected);
  uids.forEach(uid => (on ? next.add(uid) : next.delete(uid)));
  return next;
}
export function moveCursor(uids, cursor, delta) {
  if (!uids.length) return '';
  const i = uids.indexOf(cursor);
  return uids[i < 0 ? (delta > 0 ? 0 : uids.length - 1) : clamp(i + delta, 0, uids.length - 1)];
}
export const cursorOrFirst = (uids, cursor) => (uids.includes(cursor) ? cursor : (uids[0] || ''));

// ── 列表展示用的纯函数 ──
export function dueInfo(days) {
  if (days == null) return { text: '—', tone: 'none' };
  if (days < 0) return { text: `逾期 ${-days} 天`, tone: 'overdue' };
  if (days === 0) return { text: '今日到期', tone: 'today' };
  return { text: `${days} 天后`, tone: days <= 3 ? 'soon' : days <= 7 ? 'week' : 'later' };
}
export function statusOf(item) {
  if (item.suspended) return { label: '停用', kind: 'suspended' };
  const tag = String(item.tag || '').replace(/^#/, '').replace(/^状态\//, '');
  return { label: tag || '待攻克', kind: tag.includes('已击杀') ? 'kill' : tag.includes('易错') ? 'trap' : 'attack' };
}
/** 复燃：已击杀题休眠够久后重新入列；「这题不是击杀了吗」必须在列表上直接读到。停用题不谈复燃。 */
export function reviveOf(item) {
  if (!item || !item.is_revived || item.suspended) return null;
  const count = num(item.kill_count, 0), dormant = num(item.dormant_days, 0);
  return { label: `复燃${count > 1 ? ` ×${count}` : ''}`, title: `第 ${count || 1} 次击杀后休眠 ${dormant} 天复燃${item.next_revive_date ? ` · 原定 ${item.next_revive_date}` : ''}` };
}
export const masteryPct = item => Math.round(clamp(num(item.mastery, 0), 0, 1) * 100);
export const masteryTone = pct => (pct > 80 ? 'success' : pct > 40 ? 'warning' : 'danger');
/** 画廊卡只在「异常」时亮标：停用 / 复燃 / 逾期 / 今日 / 顽固；显示元数据时另给「N 天后」。 */
export function galleryFlags(item, days, detail) {
  const flags = [];
  if (item.suspended) flags.push({ text: '停用', tone: 'muted' });
  else if (item.is_revived) flags.push({ text: '复燃', tone: 'info', title: '已击杀题休眠够久，重新入列' });
  else if (days != null && days < 0) flags.push({ text: `逾期 ${-days} 天`, tone: 'danger' });
  else if (days === 0) flags.push({ text: '今日', tone: 'warning' });
  else if (detail && days != null) flags.push({ text: `${days} 天后`, tone: 'muted' });
  if (item.is_leech) flags.push({ text: '顽固', tone: 'warning' });
  return flags;
}
/** 画廊缩略预览的 qview 选项：截断行数随「显示元数据」与密度变化。 */
export function galleryCardOpts(prefs) {
  const compact = prefs.density === 'compact';
  const clampLines = prefs.galleryDetail ? (compact ? 6 : 8) : (compact ? 3 : 5);
  return { layout: 'stack', showMeta: false, showAnswer: false, showNotes: false, showHistory: false, actions: [], bare: true, clamp: clampLines };
}
export function rowMenuItems(item) {
  return [
    { value: 'view', label: '查看详情', icon: 'eye' }, { value: 'board', label: '加入展示板', icon: 'bookmark', hint: 'Shift 直加' },
    { value: 'labels', label: '打标记', icon: 'tag' }, { value: 'edit', label: '编辑 Markdown', icon: 'edit' },
    { value: 'move', label: '迁移分类', icon: 'folder' },
    item?.suspended ? { value: 'resume', label: '恢复题目', icon: 'play' } : { value: 'suspend', label: '停用题目', icon: 'pause' },
    { divider: true }, { value: 'delete', label: '删除题目', icon: 'trash', danger: true },
  ];
}
/** 批量打标记对话框的取值（复选框 id 按标记下标编号）→ 要添加 / 移除 / 新建的标记名。 */
export function batchLabelPlan(values, names) {
  const pick = prefix => names.filter((name, i) => values?.[`${prefix}-${i}`] === true);
  const fresh = String(values?.['qlb-lbl-new'] || '').trim();
  const add = pick('qlb-lbl-add');
  return { add: fresh && !add.includes(fresh) ? [...add, fresh] : add, remove: pick('qlb-lbl-rm').filter(name => name !== fresh), create: fresh && !names.includes(fresh) ? fresh : '' };
}
