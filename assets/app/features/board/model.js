/**
 * 展示板页纯函数（P7 第 1 步从 assets/board.js 原样搬来）：
 * 纸面几何、打印状态机、题后留白、排序、保存载荷、锁定边界、估算文案、预览用的内容签名与留白表。
 * 不碰 DOM、不读全局；旧 board.js 经过渡桥 installBoardBridge 读同名全局，页面 UI 迁完（P7 第 7 步）后直接 import。
 * 单测见 tests/app/board.test.mjs、tests/app/board-regions.test.mjs。
 */
const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };
const clamp = (value, min, max, fallback = 0) => Math.max(min, Math.min(max, num(value, fallback)));
const paperOf = board => (board && board.printed_summary) || { pages: 0, count: 0, new_count: 0, changed_count: 0 };

/** 切割线样式，与 omrs/boards.py::CUT_LINES 同步。 */
export const CUT_LINES = ['none', 'dash', 'solid'];
/**
 * 纸面几何常量：与导出模板同解，改一处就要改另一处。
 *   omrs/export_templates/board.css：.question-gap{height:calc(var(--gap-lines) * 18px)}
 *   omrs/export_templates/board.js：const MM = 3.779528
 */
export const BOARD_LINE_PX = 18;
export const BOARD_MM_PX = 3.779528;

/** 「留几行」对使用者是抽象的，「大概多少厘米」才是纸上真正能写多少字的直觉。 */
export function boardGapCm(lines) {
  return Math.round(clamp(lines, 0, 48, 0) * BOARD_LINE_PX / BOARD_MM_PX / 10 * 10) / 10;
}

/** 题栏宽度（px）：与导出模板的 COL_W 同一算式（A4 793.7px 宽，左右 10mm，栏间距 24px）。 */
export function boardColumnWidth(ratioPercent) {
  return Math.round((793.7 - 20 * BOARD_MM_PX - 24) * (1 - clamp(ratioPercent, 30, 55, 50) / 100));
}

/**
 * 打印状态机：整块展示板只有这一处决定「现在到哪步、下一步做什么」。
 * 返回 {chips, scope, action, why}；scope 是实际导出范围（'new' 只在有纸面且有新增时成立）。
 */
export function boardStatusModel(board, mode, awaiting) {
  const paper = paperOf(board);
  const total = ((board && board.items) || []).length;
  const hasPaper = paper.pages > 0;
  const scope = mode === 'new' && hasPaper && paper.new_count ? 'new' : 'all';
  const chips = [];
  if (!hasPaper) chips.push({ kind: 'muted', text: '还没打印过' }, { kind: 'count', text: `${total} 题` });
  else {
    chips.push({ kind: 'paper', text: `已印 ${paper.count} 题 / ${paper.pages} 页` });
    if (paper.new_count) chips.push({ kind: 'new', text: `新增 ${paper.new_count} 题未印` });
  }
  if (paper.changed_count) chips.push({ kind: 'changed', text: `${paper.changed_count} 题已改动` });
  if (awaiting) {
    chips.push({ kind: 'wait', text: '等待记录纸面' });
    return { chips, scope, action: { type: 'mark-printed', label: '✓ 记录纸面' },
      why: '打完了就点这里，系统会记住每道题印在第几页；没打成的话换回打印就行。' };
  }
  if (scope === 'new') return { chips, scope,
    action: { type: 'preview', label: `🖨 补印新增 ${paper.new_count} 题` },
    why: `接在第 ${(paper.cursor && paper.cursor.page) || paper.pages} 页的空白处，原纸放回打印机即可。` };
  return { chips, scope, action: { type: 'preview', label: '🖨 打印全部' },
    why: !hasPaper ? '第一次打印会用掉新的一叠纸；打完回来点「记录纸面」，之后加题就只补印新增。'
      : paper.new_count ? '打印全部会重排整叠纸，已经写过的那几张就作废了。只想加印新题请切到「仅新增」。'
        : '没有新增题需要补印。排序不改变旧纸面；需要按当前顺序重新排版时可主动打印全部。' };
}

/** 把 from 位置的条目移到 to；越界或原地不动时返回原顺序的副本。 */
export function boardMoveItems(items, from, to) {
  const result = [...(items || [])];
  if (from < 0 || from >= result.length || to < 0 || to >= result.length || from === to) return result;
  const [item] = result.splice(from, 1);
  result.splice(to, 0, item);
  return result;
}

/**
 * 保存用的 items：gap_lines 是「这道题之后留白的绝对行数」，null = 继承板的全局设置。
 * null 原样传回后端，否则会被当成 0 行，行内留白一保存就退化成「不留白」。
 */
export function boardItemsPayload(items) {
  return (items || []).map(item => ({
    question_id: item.question_id || '', uid: item.uid || '', added_at: item.added_at || '',
    gap_lines: item.gap_lines == null ? null : clamp(item.gap_lines, 0, 48, 0), pin: !!item.pin,
  }));
}

/** 某题实际的题后留白：自身为 null 时继承板设置（缺失回默认 2），两者都夹到 0–48。 */
export function boardEffectiveGap(item, print) {
  const own = (item || {}).gap_lines;
  return own == null ? clamp((print || {}).gap_lines, 0, 48, 2) : clamp(own, 0, 48, 0);
}

/**
 * 导出内容签名：题目集合、顺序，以及会影响「这题上不上纸」的停用 / 缺失状态。
 * 版面设置不在里面，因为几何改动走 relayout，不该触发重新导出。
 */
export function boardItemsSignature(items) {
  return (items || [])
    .map(item => `${item.uid || item.question_id || ''}${item.missing ? '!' : ''}${item.suspended ? '-' : ''}`)
    .join(',');
}

/** 传给预览的逐题留白 {uid: 行数 | null}：null 原样保留，让 iframe 自己按当前全局值继承。 */
export function boardGapMap(items) {
  const map = {};
  (items || []).forEach(item => { if (item.uid) map[item.uid] = item.gap_lines == null ? null : clamp(item.gap_lines, 0, 48, 0); });
  return map;
}

/**
 * 锁定板的改动是否会改变旧纸面（与服务端 update_board 同一边界）：引用成员 / 顺序独立于纸面，
 * 只有版式真实变化，或保留的已印题有效留白变化才算。没有纸面时恒为 false。
 */
export function boardPaperLayoutChanged(board, changes = {}) {
  if (!(paperOf(board).pages > 0)) return false;
  const before = board.print || {}, after = { ...before, ...(changes.print || {}) };
  if (['note_ratio', 'show_labels', 'show_meta', 'cut_line'].some(key => before[key] !== after[key])) return true;
  if (after.cut_line !== 'none' && before.cut_label !== after.cut_label) return true;
  const old = new Map((board.items || []).map(item => [item.question_id || item.uid, item]));
  const printed = new Set((board.printed?.items || []).map(item => item.question_id));
  return (changes.items || board.items || []).some(item => {
    const previous = old.get(item.question_id || item.uid);
    return previous && (previous.printed || printed.has(item.question_id))
      && boardEffectiveGap(previous, before) !== boardEffectiveGap(item, after);
  });
}

/** 脏字段累加而不是互相替换：「先改行内留白再拖版面滑块」曾把前一次改动整个丢掉。 */
export function boardDirtyMerge(current, kind) {
  return kind ? { ...(current || {}), [String(kind)]: true } : (current || null);
}

/**
 * 一次 POST 承载全部脏字段：/api/board/update 同一请求里能同时收 items 与 print，
 * 后端也保证 items 的 v2 折算用的是本次请求后的全局留白。没有板或没有脏字段时返回 null（不发请求）。
 */
export function boardSavePayload(detail, dirty) {
  if (!detail || !dirty || !Object.keys(dirty).length) return null;
  const payload = { id: detail.id, ...(Number.isInteger(detail.revision) ? { expected_revision: detail.revision } : {}) };
  if (dirty.items) payload.items = boardItemsPayload(detail.items || []);
  if (dirty.print) payload.print = detail.print;
  return payload;
}

/** 估算文案：layout 为导出模板回传的 OMRS_LAYOUT。返回可信的 HTML 片段（只含数字与固定文案）。 */
export function boardEstimateText(layout, mode) {
  const nums = layout.page_numbers || [];
  const range = nums.length ? (nums.length === 1 ? `第 ${nums[0]} 页` : `第 ${nums[0]}–${nums[nums.length - 1]} 页`) : '—';
  const warn = layout.warnings?.length ? ` · <span class="warn">⚠ ${layout.warnings.length} 处切图告警</span>` : '';
  if (mode === 'new') return `本次补印 <b>${layout.rendered_pages}</b> 页（${range}）${layout.partial_page ? `，第 ${layout.partial_page} 页印在原纸上` : ''} · 打印后整板共 <b>${layout.pages}</b> 页${warn}`;
  return `预计 <b>${layout.pages}</b> 页 · A4 纵向 · 左右 10 / 上下 12mm${warn}`;
}

/** 短时间「M/D HH:MM」（本地时区）；解析不了时退回原串的前 16 个字符。 */
export function boardFormatTime(value) {
  const raw = String(value || '');
  if (!raw) return '';
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw.slice(0, 16).replace('T', ' ');
  const pad = n => String(n).padStart(2, '0');
  return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/** 纸面记录摘要（没有纸面时是全 0 的空摘要）。 */
export const BOARD_EMPTY_PAPER = Object.freeze({ pages: 0, count: 0, new_count: 0, changed_count: 0 });
export const boardPaperSummary = board => board?.printed_summary || BOARD_EMPTY_PAPER;

/** 「排序」菜单（P7 第 6 轮由 board.js 的 boardSort 抽出）：返回新数组，不改原数组；未知选项按科目 / 分类 / UID。 */
export function boardSortItems(items, choice) {
  const list = [...(items || [])];
  const n = value => (Number.isFinite(Number(value)) ? Number(value) : 0);
  if (choice === 'reverse') return list.reverse();
  if (choice === 'mastery') return list.sort((a, b) => n(a.mastery) - n(b.mastery));
  if (choice === 'due') return list.sort((a, b) => String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')));
  if (choice === 'added') return list.sort((a, b) => String(a.added_at || '').localeCompare(String(b.added_at || '')));
  const key = item => `${item.subject || ''}\u0000${item.category || ''}\u0000${item.uid || ''}`;
  return list.sort((a, b) => key(a).localeCompare(key(b), 'zh-CN'));
}
