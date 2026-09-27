/**
 * 展示板页的模块单例与纯函数（P7 第 5 轮起；第 6 轮加列表 / 画廊与检查器）：状态条、左栏树、舞台头（舞台栏 / 翻页 / 警告）、
 * 列表行、画廊卡、检查器三段与三个菜单的视图模型。输入都是普通数据（板详情快照、板列表、预览版面），node 单测全覆盖；
 * 渲染在 view.js，控制器在 index.js，板详情的所有者是 detail.js。
 * 打印状态机 boardStatusModel、留白与几何换算在 model.js；文件夹分组 boardFolderTree 在 domain/board/model.js。
 */
import { boardStatusModel, boardFormatTime, boardEffectiveGap, boardGapCm, boardColumnWidth, CUT_LINES } from './model.js';
import { boardFolderTree } from '../../domain/board/model.js';

/** 页面自己的 UI 状态：纸面缩放档、状态条上的就地改名。板详情、打印范围、视图、选中题归 detail.js。 */
export const state = { zoom: 'fit', renaming: false };

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

/** 状态条：板名 · 状态 chips · 为什么 · 打印范围 · 唯一主行动。snap = detail.js 的 snapshot()。 */
export function statusView(snap) {
  const detail = snap?.detail;
  if (!detail) return { empty: true };
  const items = detail.items || [];
  const paper = paperOf(detail);
  const status = boardStatusModel(detail, snap.mode, snap.awaiting);
  return {
    empty: false, id: detail.id, name: detail.name || '', count: items.length, subjects: subjectSummary(items),
    note: detail.note || '', locked: !!detail.print?.locked, chips: status.chips, why: status.why, scope: status.scope,
    action: status.action, newCount: num(paper.new_count), canNew: !!(paper.pages && paper.new_count),
  };
}

/** 板行第二行：题数 · 已印页数（+未印）· 缺失 · 停用 · 更新时间。tone 决定颜色，不写进文字。 */
export function boardMetaBits(board) {
  const paper = board?.printed_summary || {};
  const bits = [{ text: `${num(board?.count)} 题` }];
  if (paper.pages) bits.push({ text: `已印 ${paper.pages} 页`, tone: 'ok', plus: paper.new_count ? `+${paper.new_count}` : '' });
  if (board?.missing) bits.push({ text: `缺失 ${board.missing}`, tone: 'warn' });
  if (board?.suspended) bits.push({ text: `停用 ${board.suspended}` });
  const time = boardFormatTime(board?.updated_at);
  if (time) bits.push({ text: time });
  return bits;
}

/** 左栏树：文件夹组（折叠的组不列板）+ 恒在最后的「未归档」。boards / folders 为空时 empty。 */
export function treeView({ boards = [], folders = [], current = '', collapsed = new Set() } = {}) {
  if (!boards.length && !folders.length) return { empty: true, count: 0, groups: [] };
  const groups = boardFolderTree(boards, folders).map(group => {
    const plain = !group.id;
    const folded = !plain && collapsed.has(group.id);
    const newCount = group.boards.reduce((sum, board) => sum + num(board.printed_summary?.new_count), 0);
    const total = group.boards.reduce((sum, board) => sum + num(board.count), 0);
    return {
      id: group.id || '', name: plain ? '未归档' : group.name, plain, folded, count: group.boards.length, newCount,
      title: plain ? '' : `${group.name}：${group.boards.length} 板 · ${total} 题${newCount ? ` · ${newCount} 题还没印上纸` : ''}`,
      boards: folded ? [] : group.boards.map(board => ({
        id: board.id, name: board.name, title: board.note || board.name, on: board.id === current, bits: boardMetaBits(board),
      })),
    };
  });
  return { empty: false, count: boards.length, groups };
}

/** 预计页数的结构化读数（取代 model.js 里拼 HTML 的 boardEstimateText）。 */
export function estimateView(layout, scope) {
  if (!layout) return null;
  const nums = layout.page_numbers || [];
  const range = nums.length ? (nums.length === 1 ? `第 ${nums[0]} 页` : `第 ${nums[0]}–${nums[nums.length - 1]} 页`) : '—';
  return { scope: scope === 'new' ? 'new' : 'all', pages: num(layout.pages), rendered: num(layout.rendered_pages), range,
    partial: num(layout.partial_page), warnings: (layout.warnings || []).length };
}

/** 舞台头：视图、题数、缺失 / 停用警告；纸面视图另有翻页条（页码读常驻预览已排好的版面）。 */
export function stageView(snap, { layout = null, view = null, zoom = 'fit' } = {}) {
  const detail = snap?.detail;
  if (!detail) return { empty: true };
  const items = detail.items || [];
  const paper = paperOf(detail);
  const scope = boardStatusModel(detail, snap.mode, null).scope;   // 与导出同一个判断（detail.js 的 effectiveMode）
  const numbers = layout?.page_numbers || [];
  return {
    empty: false, view: snap.view === 'list' || snap.view === 'gallery' ? snap.view : 'paper', count: items.length,
    missing: items.filter(item => item.missing).length,
    suspended: items.filter(item => item.suspended && !item.missing).length,
    pager: {
      multi: numbers.length > 1, page: num(view?.page, 0) || numbers[0] || 1, pages: num(layout?.pages),
      jumpNew: !!paper.new_count, estimate: estimateView(layout, scope), error: snap.previewError || '',
      zoom: zoom === 'fit' ? 'fit' : '1',
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
export const VIEWS = Object.freeze([['paper', '纸面'], ['list', '列表'], ['gallery', '画廊']]);

// ---------- 列表 / 画廊 / 检查器（P7 第 6 轮起） ----------

/** 纸面状态标：列表行、画廊卡、检查器共用一套判断（缺失 / 停用优先，其后已印 p.N / 新增、已改动）。tone 决定颜色。 */
export function itemFlags(item, hasPaper) {
  const flags = [];
  if (item?.missing) flags.push({ text: '缺失', tone: 'muted' });
  else if (item?.suspended) flags.push({ text: '停用', tone: 'muted' });
  if (hasPaper && item && !item.missing && !item.suspended) {
    flags.push(item.printed
      ? { text: `已印${item.printed_page ? ` p.${item.printed_page}` : ''}`, tone: 'paper', title: '已经打印在纸上' }
      : { text: '新增', tone: 'new', title: '纸上还没有这道题' });
    if (item.changed) flags.push({ text: '已改动', tone: 'changed', title: '打印后正文改过，纸面仍是旧版' });
  }
  return flags;
}

/** 题后留白的只读回显（列表行、画廊卡）与检查器读数：同一个数字只从这里算，板级留白一改三处一起变。 */
export function gapReadout(item, print) {
  const lines = boardEffectiveGap(item || {}, print || {});
  const inherited = item?.gap_lines == null;
  return { lines, inherited, text: `留白 ${lines} 行${inherited ? '（继承）' : ''}`, long: `${lines} 行 ≈ ${boardGapCm(lines)} cm${inherited ? '（继承）' : ''}` };
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

/** 列表 / 画廊：snap = detail.js 的 snapshot()；dueDays(item) 由页面注入（旧 getDueDays）。纸面视图不出条目。 */
export function contentView(snap, { dueDays = () => null } = {}) {
  const detail = snap?.detail;
  const kind = snap?.view === 'list' || snap?.view === 'gallery' ? snap.view : 'paper';
  if (!detail || kind === 'paper') return { kind: 'none', rows: [] };
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
  return { kind, rows, empty: !rows.length };
}

/** 检查器三段：选中的题 / 版式 / 纸面记录。三段永远在右栏同一处，与当前视图无关；题后留白只有这里能改。 */
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
    uid: it.uid, no: index + 1, name: it.uid || it.question_id || '未知题目', missing: !!it.missing, printed: !!it.printed,
    flags: itemFlags(it, hasPaper),
    meta: [it.subject, it.category].filter(Boolean).join(' · ') + (it.difficulty != null && it.difficulty !== '' ? `${it.subject || it.category ? ' · ' : ''}难度 ${it.difficulty}` : ''),
    own: it.gap_lines == null ? '' : String(Math.max(0, Math.min(48, num(it.gap_lines)))), inherited, gap: gapReadout(it, print),
    note: it.printed ? `这道题纸上已经有了：${locked ? '锁定时修改实际留白需确认，确认后清空纸面记录并重新打印全部。' : '改留白只影响下次「打印全部」和当前预览，纸面记录保留旧占位。'}` : '',
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
