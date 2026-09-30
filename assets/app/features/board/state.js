/**
 * 展示板页的模块单例与纯函数：板头、左栏树、纸面工具条、题目列表、滑入详情与浮层的视图模型。
 * 输入都是普通数据（板详情快照、板列表、预览版面）；
 * 渲染在 view.js，控制器在 index.js，板详情的所有者是 detail.js。
 * 打印状态机 boardStatusModel、留白与几何换算在 model.js；文件夹分组 boardFolderTree 在 domain/board/model.js。
 */
import { boardStatusModel, boardFormatTime, boardEffectiveGap, boardGapCm, boardColumnWidth, CUT_LINES } from './model.js';
import { boardFolderTree } from '../../domain/board/model.js';

/** 页面自己的 UI 状态：纸面缩放、就地改名、左栏（窄屏抽屉 boardsOpen / 宽屏收起 listHidden）、题目详情、
 *  详情里已显示答案的题（revealUid）与浮层。板详情、打印范围、选中题归 detail.js。 */
export const MOTION_KINDS = Object.freeze(['fade', 'slide', 'paper', 'none']);
export const MOTION_DEFAULT = Object.freeze({ kind: 'fade', duration: 280 });
export const MOTION_LIMITS = Object.freeze({ min: 100, max: 800, step: 50 });
const MOTION_KEY = 'omrs-board-motion';

export function normalizeMotion(value = {}) {
  const kind = MOTION_KINDS.includes(value?.kind) ? value.kind : MOTION_DEFAULT.kind;
  if (value?.duration == null || value.duration === '') return { kind, duration: MOTION_DEFAULT.duration };
  const raw = Number(value?.duration);
  const safe = Number.isFinite(raw) ? raw : MOTION_DEFAULT.duration;
  if (safe === MOTION_DEFAULT.duration) return { kind, duration: MOTION_DEFAULT.duration };
  const stepped = MOTION_LIMITS.min + Math.round((safe - MOTION_LIMITS.min) / MOTION_LIMITS.step) * MOTION_LIMITS.step;
  const duration = Math.max(MOTION_LIMITS.min, Math.min(MOTION_LIMITS.max, stepped));
  return { kind, duration };
}

export function readMotionPreference(storage = globalThis.localStorage) {
  try { return normalizeMotion(JSON.parse(storage?.getItem(MOTION_KEY) || '{}')); }
  catch (error) { return { ...MOTION_DEFAULT }; }
}

export function saveMotionPreference(value, storage = globalThis.localStorage) {
  const next = normalizeMotion(value);
  try { storage?.setItem(MOTION_KEY, JSON.stringify(next)); } catch (error) { /* 隐私模式 / 禁用存储时退化为内存偏好 */ }
  return next;
}

export const motionLabel = kind => ({ fade: '渐隐渐显', slide: '左右滑页', paper: '抽纸', none: '关闭动效' }[kind] || '渐隐渐显');

export const state = { zoom: 'fit', motion: readMotionPreference(), renaming: false, boardsOpen: false, listHidden: false, query: '', panel: 'list', pop: '', revealUid: '' };
const LINK_KEY = 'omrs-board-linked-labels';

/** 关联标记只存本机浏览器；板的服务端格式不因此改变。 */
export function linkedLabel(id, storage = globalThis.localStorage) {
  try { return JSON.parse(storage?.getItem(LINK_KEY) || '{}')[id] || ''; } catch (error) { return ''; }
}
export function setLinkedLabel(id, name, storage = globalThis.localStorage) {
  try {
    const values = JSON.parse(storage?.getItem(LINK_KEY) || '{}');
    if (name) values[id] = name; else delete values[id];
    storage?.setItem(LINK_KEY, JSON.stringify(values));
  } catch (error) { /* 浏览器禁用本地存储时，本次选择仍可通过现有同步对话框完成 */ }
}

export function setMotion(patch, storage = globalThis.localStorage) {
  state.motion = saveMotionPreference({ ...state.motion, ...(patch || {}) }, storage);
  return state.motion;
}

const num = (value, fallback = 0) => (Number.isFinite(Number(value)) ? Number(value) : fallback);
export const paperOf = board => board?.printed_summary || { pages: 0, count: 0, new_count: 0, changed_count: 0 };

/** 「数学 3 · 物理 1」：缺失的题不算，没有科目的记为「未分科」。 */
export function subjectSummary(items) {
  const counts = new Map();
  (items || []).filter(item => !item.missing).forEach(item => {
    const key = item.subject || '未分科';
    counts.set(key, (counts.get(key) || 0) + 1);
  });
  return [...counts].map(([key, value]) => `${key} ${value}`).join(' · ');
}

/** 板头：板名、保存状态、打印范围与主行动。snap = detail.js 的 snapshot()。 */
export function statusView(snap, folders = [], saving = false) {
  const detail = snap?.detail;
  if (!detail) return { empty: true };
  const items = detail.items || [];
  const paper = paperOf(detail);
  const status = boardStatusModel(detail, snap.mode, snap.awaiting);
  const folder = folders.find(entry => entry.id === detail.folder_id);
  const printable = items.filter(item => !item.missing && !item.suspended).length;
  const actionLabel = snap.awaiting ? '重新打开打印' : status.scope === 'new' ? `补印新增 ${num(paper.new_count)} 题`
    : paper.pages ? `重印全部 ${printable} 题` : `打印 ${printable} 题`;
  return {
    empty: false, id: detail.id, name: detail.name || '', count: items.length, subjects: subjectSummary(items),
    note: detail.note || '', locked: !!detail.print?.locked, chips: status.chips, why: status.why, scope: status.scope,
    action: status.action, actionLabel, awaiting: !!snap.awaiting, printable, folder: folder?.name || '未归档', saving,
    newCount: num(paper.new_count), canNew: !!(paper.pages && paper.new_count), hasPaper: !!paper.pages,
  };
}

/** 板行第二行：题数、已印页数、未印、缺失、停用。tone 决定颜色，不写进文字；更新时间放进悬停提示（treeView 的 time）。 */
export function boardMetaBits(board) {
  const paper = board?.printed_summary || {};
  const bits = [{ text: `${num(board?.count)} 题` }];
  if (paper.pages) bits.push({ text: `已印 ${paper.pages} 页`, tone: 'ok' });
  if (paper.new_count) bits.push({ text: `${paper.new_count} 题未印`, tone: 'new' });
  if (board?.missing) bits.push({ text: `缺失 ${board.missing}`, tone: 'warn' });
  if (board?.suspended) bits.push({ text: `停用 ${board.suspended}` });
  return bits;
}

/** 左栏树：文件夹组（折叠的组不列板）+ 恒在最后的「未归档」。boards / folders 为空时 empty。 */
export function treeView({ boards = [], folders = [], current = '', collapsed = new Set(), query = '' } = {}) {
  if (!boards.length && !folders.length) return { empty: true, count: 0, groups: [] };
  const needle = String(query).trim().toLocaleLowerCase();
  const groups = boardFolderTree(boards, folders).map(group => {
    const plain = !group.id;
    const folded = !needle && !plain && collapsed.has(group.id);
    const newCount = group.boards.reduce((sum, board) => sum + num(board.printed_summary?.new_count), 0);
    const total = group.boards.reduce((sum, board) => sum + num(board.count), 0);
    return {
      id: group.id || '', name: plain ? '未归档' : group.name, plain, folded, count: group.boards.length, newCount,
      title: plain ? '' : `${group.name}：${group.boards.length} 板 · ${total} 题${newCount ? ` · ${newCount} 题还没印上纸` : ''}`,
      boards: folded ? [] : group.boards.filter(board => !needle || `${board.name} ${board.note || ''} ${group.name || ''}`.toLocaleLowerCase().includes(needle)).map(board => ({
        id: board.id, name: board.name, title: board.note || board.name, on: board.id === current, bits: boardMetaBits(board), time: boardFormatTime(board.updated_at),
      })),
    };
  }).filter(group => !needle || group.boards.length);
  return { empty: false, count: boards.length, groups, query };
}

/** 预计页数的结构化读数（取代 model.js 里拼 HTML 的 boardEstimateText）。 */
export function estimateView(layout, scope) {
  if (!layout) return null;
  const nums = layout.page_numbers || [];
  const range = nums.length ? (nums.length === 1 ? `第 ${nums[0]} 页` : `第 ${nums[0]}–${nums[nums.length - 1]} 页`) : '—';
  return { scope: scope === 'new' ? 'new' : 'all', pages: num(layout.pages), rendered: num(layout.rendered_pages), range,
    partial: num(layout.partial_page), warnings: (layout.warnings || []).length };
}

/** 纸面工具条：纸面、未印与已改动计数，页码读常驻预览已排好的版面。 */
export function stageView(snap, { layout = null, view = null, zoom = 'fit' } = {}) {
  const detail = snap?.detail;
  if (!detail) return { empty: true };
  const items = detail.items || [];
  const paper = paperOf(detail);
  const scope = boardStatusModel(detail, snap.mode, null).scope;   // 与导出同一个判断（detail.js 的 effectiveMode）
  const numbers = layout?.page_numbers || [];
  return {
    empty: false, view: 'paper', count: items.length,
    paperCount: num(paper.count), paperPages: num(paper.pages), newCount: num(paper.new_count), changedCount: num(paper.changed_count),
    changedUid: items.find(item => item.changed && !item.missing && !item.suspended)?.uid || '',
    missing: items.filter(item => item.missing).length,
    suspended: items.filter(item => item.suspended && !item.missing).length,
    pager: {
      multi: numbers.length > 1, page: num(view?.page, 0) || numbers[0] || 1, pages: num(layout?.pages),
      jumpNew: !!paper.new_count, estimate: estimateView(layout, scope), error: snap.previewError || '',
      zoom: zoom === 'fit' ? 'fit' : '1',
      motion: { ...state.motion },
    },
  };
}

/** 「跳到新增」：第一道还没印在纸上的题（缺失、停用的不算）。 */
export function firstNewUid(items) {
  return (items || []).find(item => !item.missing && !item.suspended && !item.printed)?.uid || '';
}

/** 板 ⋯ 菜单（ui/menu 条目）；value 由 index.js 分派，移到文件夹写成 'move:<文件夹 id>'（空 id = 未归档）。 */
export function boardMenuItems(board, folders = []) {
  const moves = folders.filter(folder => folder.id !== board.folder_id).map(folder => ({ value: `move:${folder.id}`, label: `移到「${folder.name}」` }));
  if (board.folder_id) moves.push({ value: 'move:', label: '移到未归档' });
  return [
    { value: 'rename', label: '重命名' }, { value: 'note', label: '备注…' }, { value: 'duplicate', label: '复制' },
    { value: 'export', label: '导出 HTML', icon: 'download' }, { divider: true },
    ...moves, { value: 'move-new', label: '移到新文件夹…', icon: 'folder' }, { divider: true },
    { value: 'delete', label: '删除', icon: 'trash', danger: true },
  ];
}

/** 文件夹 ⋯ 菜单；已在最前 / 最后时上移 / 下移禁用。 */
export function folderMenuItems(folder, folders = []) {
  const order = num(folder.order);
  return [
    { value: 'rename', label: '重命名' }, { value: 'new-board', label: '在此新建板', icon: 'plus' },
    { value: 'up', label: '上移', disabled: order <= 0 }, { value: 'down', label: '下移', disabled: order >= folders.length - 1 },
    { divider: true }, { value: 'delete', label: '删除文件夹', icon: 'trash', danger: true },
  ];
}

export const NEW_MENU = Object.freeze([{ value: 'board', label: '新建展示板', icon: 'plus' }, { value: 'folder', label: '新建文件夹', icon: 'folder' }]);
export const SORT_MENU = Object.freeze([
  { value: 'subject', label: '按科目 / 分类' }, { value: 'mastery', label: '按熟练度 ↑' }, { value: 'due', label: '按到期' },
  { value: 'added', label: '按加入时间' }, { value: 'reverse', label: '反转顺序' },
]);
// ---------- 题目列表 / 详情与浮层 ----------

/** 纸面状态标：题目行与详情共用一套判断（缺失 / 停用优先，其后已印 p.N / 未印、已改动）。 */
export function itemFlags(item, hasPaper) {
  const flags = [];
  if (item?.missing) flags.push({ text: '缺失', tone: 'muted' });
  else if (item?.suspended) flags.push({ text: '停用', tone: 'muted' });
  if (hasPaper && item && !item.missing && !item.suspended) {
    flags.push(item.printed
      ? { text: `已印${item.printed_page ? ` p.${item.printed_page}` : ''}`, tone: 'paper', title: '已经打印在纸上' }
      : { text: '未印', tone: 'new', title: '纸上还没有这道题' });
    if (item.changed) flags.push({ text: '已改动', tone: 'changed', title: '打印后正文改过，纸面仍是旧版' });
  }
  return flags;
}

/** 题后留白的行内读数与详情读数：同一个数字只从这里算。 */
export function gapReadout(item, print) {
  const lines = boardEffectiveGap(item || {}, print || {});
  const inherited = item?.gap_lines == null;
  return { lines, inherited, cm: boardGapCm(lines), text: `留白 ${lines} 行${inherited ? '（继承）' : ''}`, long: `${lines} 行 ≈ ${boardGapCm(lines)} cm${inherited ? '（继承）' : ''}` };
}

/** 到期读数（与题库同一分档）：days = getDueDays() 的结果，null 表示没有到期日。 */
export function dueView(days) {
  if (days == null || !Number.isFinite(Number(days))) return null;
  const d = Number(days);
  if (d < 0) return { text: `逾期 ${-d} 天`, tone: 'danger' };
  if (d === 0) return { text: '今日到期', tone: 'warn' };
  return { text: `${d} 天后`, tone: d <= 3 ? 'warn' : d <= 7 ? 'info' : '' };
}

const pct = value => Math.round(num(value) * 100);

/** 题目列表：snap = detail.js 的 snapshot()；dueDays(item) 由页面注入。 */
export function contentView(snap, { dueDays = () => null } = {}) {
  const detail = snap?.detail;
  const kind = 'list';
  if (!detail) return { kind: 'none', rows: [] };
  const hasPaper = paperOf(detail).pages > 0;
  const rows = (detail.items || []).map((item, index) => ({
    uid: item.uid || '', no: index + 1, index, name: item.uid || item.question_id || '未知题目',
    missing: !!item.missing, suspended: !!item.suspended, selected: !!snap.selected && snap.selected === item.uid,
    flags: itemFlags(item, hasPaper), labels: item.labels || [],
    subject: item.subject || '', category: item.category || '',
    difficulty: item.difficulty != null && item.difficulty !== '' ? String(item.difficulty) : '',
    mastery: pct(item.mastery), due: item.missing ? null : dueView(dueDays(item)),
    gap: gapReadout(item, detail.print),
  }));
  return { kind, rows, empty: !rows.length, count: rows.filter(row => !row.missing && !row.suspended).length,
    total: rows.length, suspended: rows.filter(row => row.suspended).length, missing: rows.filter(row => row.missing).length };
}

/** 当前题的滑入详情、版式浮层与纸面记录浮层共用的派生模型。 */
export function inspectorView(snap) {
  const detail = snap?.detail;
  if (!detail) return { empty: true };
  const print = detail.print || {};
  const locked = !!print.locked;
  const hasPaper = paperOf(detail).pages > 0;
  const list = detail.items || [];
  const index = snap.selected ? list.findIndex(item => item.uid === snap.selected) : -1;
  const it = index >= 0 ? list[index] : null;
  const inherited = Math.max(0, Math.min(48, num(print.gap_lines, 2)));
  const item = it && {
    uid: it.uid, no: index + 1, index, total: list.length, name: it.uid || it.question_id || '未知题目', missing: !!it.missing, printed: !!it.printed,
    flags: itemFlags(it, hasPaper),
    meta: [it.subject, it.category].filter(Boolean).join(' · ') + (it.difficulty != null && it.difficulty !== '' ? `${it.subject || it.category ? ' · ' : ''}难度 ${it.difficulty}` : ''),
    metaBits: [[it.subject, it.category].filter(Boolean).join(' / '), it.difficulty != null && it.difficulty !== '' ? `难度 ${it.difficulty}` : '',
      it.missing ? '' : `熟练度 ${pct(it.mastery)}%`].filter(Boolean),
    labels: it.labels || [], difficulty: it.difficulty, mastery: pct(it.mastery),
    own: it.gap_lines == null ? '' : String(Math.max(0, Math.min(48, num(it.gap_lines)))), inherited, gap: gapReadout(it, print),
    note: it.printed ? `已印在${it.printed_page ? `第 ${it.printed_page} 页` : '纸上'}：${locked ? '锁定时修改实际留白需确认，确认后清空纸面记录并重新打印全部。' : '改留白只影响下次「全部重印」和当前预览，补印新增时纸上的位置不变。'}` : '',
  };
  const ratio = Math.round(num(print.note_ratio, 0.5) * 100);
  const cut = CUT_LINES.includes(print.cut_line) ? print.cut_line : 'dash';
  const gap = Math.max(0, Math.min(24, num(print.gap_lines, 2)));
  const paper = paperOf(detail);
  return {
    empty: false, selected: !!it, item,
    layout: {
      ratio, colWidth: boardColumnWidth(ratio), gap, gapText: `${gap} 行 ≈ ${boardGapCm(gap)} cm`,
      answers: print.answers === 'append' ? 'append' : 'none', showLabels: print.show_labels !== false, showMeta: print.show_meta !== false,
      cut, cutLabel: !!print.cut_label, locked,
      lockHint: '增删题目、排序和调整未打印题留白都保留纸面；锁定只在实际改变已印区域的版式或留白时确认重印。没有纸面记录时无需确认。',
    },
    paper: hasPaper
      ? { has: true, count: num(paper.count), pages: num(paper.pages), at: boardFormatTime(paper.at), cursorPage: num(paper.cursor?.page, 0) || num(paper.pages),
        cursorY: paper.cursor?.y != null ? Math.round(num(paper.cursor.y)) : null, changed: num(paper.changed_count) }
      : { has: false },
    motion: { ...state.motion },
  };
}

/** 详情层的练习记录摘要。stats = domain/question 的 qHistoryStats(records)；无记录时只给一句空状态。 */
export function recordSummaryView(stats) {
  if (!stats?.count) return { count: 0, text: '还没练过。加入复习后，这里会出现战绩和最近一次的自评。' };
  const last = stats.last || {};
  const when = String(last.date || '').replace(/^\d{4}-0?(\d+)-0?(\d+)$/, '$1 月 $2 日');
  return {
    count: stats.count, rate: stats.rate,
    text: `练习 ${stats.count} 次，答对 ${stats.correct} 次。最近一次在 ${when || '—'}，${last.correct ? '答对' : '答错'}，自评 ${last.score ?? '—'} 分。`,
    alert: stats.tailWrong >= 2 ? `最近连错 ${stats.tailWrong} 次${last.note ? `，上次卡在「${last.note}」` : '，建议重看错因'}。` : '',
  };
}

export const ANSWER_OPTIONS = Object.freeze([['none', '不含'], ['append', '末页附答案']]);
export const CUT_OPTIONS = Object.freeze([['none', '不画'], ['dash', '虚线'], ['solid', '实线']]);

// ---------- 「添加题目」对话框（add.js）的筛选 ----------
export const ADD_VIEW_KEY = 'omrs-board-add-view';
export const ADD_DEFAULTS = Object.freeze({ text: '', subject: '', category: '', ktag: '', tag: '', due: '', sort: 'mastery-asc', labels: [] });
export const ADD_TAGS = Object.freeze([['', '全部状态'], ['待攻克', '待攻克'], ['已击杀', '已击杀'], ['易错', '易错坑']]);
export const ADD_DUES = Object.freeze([['', '全部到期'], ['overdue', '逾期'], ['today', '今日'], ['7days', '7 天内']]);
export const ADD_SORTS = Object.freeze([['mastery-asc', '熟练度 ↑'], ['due-asc', '到期 ↑'], ['diff-desc', '难度 ↓'], ['date-desc', '最近复习']]);

/** 对话框筛选 → 全站共用的 filterItems() 条件（与旧 boardAddFilterState 同义：标记任一命中、停用题不列）。 */
export function addFilters(f = ADD_DEFAULTS) {
  return {
    text: String(f.text || '').trim().toLowerCase(), subject: f.subject || '', category: f.category || '',
    tag: f.tag || '', knowledgeTag: f.ktag || '', labels: [...(f.labels || [])], labelMode: 'any',
    difficultyMin: 0, difficultyMax: 10, masteryMin: null, masteryMax: null, dueFilter: f.due || '', suspended: '', sort: f.sort || 'mastery-asc',
  };
}

/** 对话框的行：已在板里的标灰并跳过；selected 是勾选集合（唯一真相，切视图不丢）。 */
export function addRows(visible, existing, selected) {
  return (visible || []).map(item => ({
    uid: item.uid, in: existing.has(item.uid), on: existing.has(item.uid) || selected.has(item.uid),
    subject: item.subject || '', category: item.category || '', difficulty: item.difficulty ?? '', mastery: pct(item.mastery), labels: item.labels || [],
  }));
}

/** 「全选筛选结果」：只加还不在板里的。返回新集合。 */
export function addSelectAll(visible, existing, selected) {
  const next = new Set(selected);
  (visible || []).forEach(item => { if (!existing.has(item.uid)) next.add(item.uid); });
  return next;
}
