/**
 * 展示板领域纯函数：选板浮层的分组、行状态、过滤、最近使用、行模型与点击决策，以及 UID 归一化。
 * 选板浮层是所有「加入展示板」入口的唯一实现（题目库、数据复盘、复习调度、展示板页都会调），所以放在 domain。
 * P7 第 1 步从 assets/board.js、assets/board_picker.js 原样搬来；旧脚本经过渡桥 installBoardBridge 读同名全局。
 * 不碰 DOM、不读全局；单测见 tests/app/board.test.mjs。
 */
const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };
const byOrder = (a, b) => num(a.order, 0) - num(b.order, 0);

/** 去空白、去空、去重，保留首次出现的顺序。 */
export function boardUniqueUids(uids) {
  return [...new Set((uids || []).map(uid => String(uid || '').trim()).filter(Boolean))];
}

/**
 * 按文件夹分组：文件夹按 order 在前，未归档恒在最后；空文件夹保留（左栏要显示「把板拖进来」占位），
 * `dropEmpty` 时去掉。未归档不是真文件夹：没有板时不占一行；一个文件夹都没有时退回单个「未归档」组。
 */
export function boardFolderTree(boards, folders, options = {}) {
  const list = Array.isArray(boards) ? boards : [];
  const groups = (Array.isArray(folders) ? folders : [])
    .slice()
    .sort(byOrder)
    .map(folder => ({ id: folder.id, name: folder.name, folder, boards: [] }));
  const index = new Map(groups.map(group => [group.id, group]));
  const unfiled = { id: '', name: '未归档', folder: null, boards: [] };
  list.forEach(board => (index.get(board.folder_id) || unfiled).boards.push(board));
  groups.forEach(group => group.boards.sort(byOrder));
  unfiled.boards.sort(byOrder);
  const result = options.dropEmpty ? groups.filter(group => group.boards.length) : groups;
  return unfiled.boards.length && result.length ? [...result, unfiled] : (result.length ? result : [unfiled]);
}

/** 行状态：全新 / 部分已在板中 / 全部已在板中。pending 是这次点击真正会加进去的那些题。 */
export function boardPickerRowState(board, uids) {
  const wanted = boardUniqueUids(uids);
  const owned = new Set(board?.uids || []);
  const pending = wanted.filter(uid => !owned.has(uid));
  const have = wanted.length - pending.length;
  if (!wanted.length) return { kind: 'new', have: 0, total: 0, pending: [] };
  if (!have) return { kind: 'new', have, total: wanted.length, pending };
  if (!pending.length) return { kind: 'full', have, total: wanted.length, pending };
  return { kind: 'partial', have, total: wanted.length, pending };
}

/** 过滤态展平分组，每行带上所属文件夹名（否则同名板分不清）；板名与文件夹名都参与匹配。空查询返回 null。 */
export function boardPickerFilter(groups, query) {
  const needle = String(query || '').trim().toLowerCase();
  if (!needle) return null;
  const rows = [];
  (groups || []).forEach(group => {
    const folderHit = String(group.name || '').toLowerCase().includes(needle);
    group.boards.forEach(board => {
      if (folderHit || String(board.name || '').toLowerCase().includes(needle)) {
        rows.push({ board, folderName: group.id ? group.name : '' });
      }
    });
  });
  return rows;
}

/** 最近：上次用过的板 + 最近更新的，最多 limit 条。 */
export function boardPickerRecent(boards, lastId, limit = 2) {
  const list = (boards || []).slice();
  const last = list.find(board => board.id === lastId);
  const rest = list
    .filter(board => board.id !== lastId)
    .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  return [last, ...rest].filter(Boolean).slice(0, limit);
}

/* ---------- 选板浮层的行模型与决策（P7 第 4 轮：浮层迁进 domain/board/picker.js，这里是它不碰 DOM 的部分） ---------- */

const hasKey = (added, id) => !!added && typeof added.has === 'function' && added.has(id);

/**
 * 浮层列表：items 是渲染顺序里的分组标题与板行，rows 只含板行（键盘高亮在它上面走）。
 * 过滤态展平（行带文件夹名）；否则「最近」（板多于 6 个才有，板少时它只会让同一个板出现两次）+ 按文件夹分组，
 * 有文件夹时才显示组标题，折叠的文件夹只留标题。每行的 key 带分区前缀，「最近」里的板与组里的同一个板不重名。
 * input: { boards, folders, uids, query, lastId, collapsed: Set, added: Map|Set }
 */
export function boardPickerItems({ boards = [], folders = [], uids = [], query = '', lastId = '', collapsed = null, added = null } = {}) {
  const list = Array.isArray(boards) ? boards : [];
  const folderList = Array.isArray(folders) ? folders : [];
  const groups = boardFolderTree(list, folderList, { dropEmpty: true });
  const needle = String(query || '').trim();
  const row = (section, board, folderName) => ({
    type: 'row', key: `${section}:${board.id}`, board, folderName, state: boardPickerRowState(board, uids), added: hasKey(added, board.id),
  });
  const items = [];
  const filtered = boardPickerFilter(groups, needle);
  if (filtered) {
    filtered.forEach(hit => items.push(row('b', hit.board, hit.folderName)));
    return { items, rows: items, empty: items.length ? '' : `没有匹配「${needle}」的板` };
  }
  const recent = list.length > 6 ? boardPickerRecent(list, lastId) : [];
  if (recent.length) {
    items.push({ type: 'group', key: 'g:~recent', id: '', name: '最近', plain: true, count: null, folded: false });
    recent.forEach(board => items.push(row('r', board, '')));
  }
  const showGroups = folderList.length > 0;
  groups.forEach(group => {
    const folded = !!group.id && hasKey(collapsed, group.id);
    if (showGroups) items.push({ type: 'group', key: `g:${group.id || '~unfiled'}`, id: group.id, name: group.name, plain: !group.id, count: group.boards.length, folded });
    if (!folded) group.boards.forEach(board => items.push(row('b', board, '')));
  });
  return { items, rows: items.filter(item => item.type === 'row'), empty: items.length ? '' : '还没有展示板：下面新建一个。' };
}

/** 默认高亮：第一个「点了有用」的行——上次用的板如果题目全在里面，Enter 不该是空动作。没有行时 -1。 */
export function boardPickerDefaultActive(rows) {
  const list = rows || [];
  if (!list.length) return -1;
  const first = list.findIndex(item => item.state?.kind !== 'full');
  return first >= 0 ? first : 0;
}

/** ↑↓ 循环移动高亮。 */
export function boardPickerStep(active, step, count) {
  if (!count) return -1;
  const from = active >= 0 ? active : (step > 0 ? -1 : 0);
  return (((from + step) % count) + count) % count;
}

/** ←/→ 折叠 / 展开的目标：高亮行所在的文件夹组（它前面最近的组标题）；在「最近」、未归档或没有组标题时返回 ''。 */
export function boardPickerFoldTarget(items, activeKey) {
  const list = items || [];
  const at = list.findIndex(item => item.type === 'row' && item.key === activeKey);
  for (let i = at - 1; i >= 0; i -= 1) {
    if (list[i].type === 'group') return list[i].plain ? '' : (list[i].id || '');
  }
  return '';
}

/**
 * 折叠 / 展开之后高亮落在哪一行：组标题后面的第一行（展开时是组里第一行，折叠时是组后面的第一行）；后面没有行时取它前面最后一行。
 * 返回行 key，没有行时 ''。
 */
export function boardPickerRowAfterGroup(items, groupId) {
  const list = items || [];
  const at = list.findIndex(item => item.type === 'group' && !item.plain && item.id === groupId);
  if (at < 0) return '';
  const after = list.slice(at + 1).find(item => item.type === 'row');
  if (after) return after.key;
  const before = list.slice(0, at).reverse().find(item => item.type === 'row');
  return before ? before.key : '';
}

/**
 * 点一行（或 Enter / Ctrl+Enter）要做什么：
 * - 全部已在板中且不是本次加的：不重复加入，改为打开这个板（open）；
 * - ⌘ / Ctrl 点本次已加过的行：撤回本次加进去的那些题（undo，只撤本次会话加的，不动板里原有的）；
 * - 否则加入（add）：只加还不在板里的题，全在时按原题目列表加（服务端回「已经在板里了」）；additive 时浮层不关，可以连加。
 */
export function boardPickerPlan(board, { uids = [], added = null } = {}, additive = false) {
  const state = boardPickerRowState(board, uids);
  const mine = hasKey(added, board?.id);
  if (state.kind === 'full' && !mine) return { kind: 'open' };
  if (additive && mine) return { kind: 'undo', uids: typeof added.get === 'function' ? (added.get(board.id) || []) : [] };
  return { kind: 'add', uids: state.pending.length ? state.pending : boardUniqueUids(uids), additive: !!additive };
}

/** 锚定弹出的位置：左对齐锚点、不出视口（边距 10）；下方放不下时翻到锚点上方。 */
export function boardPickerPosition(anchor, size, viewport) {
  const width = size?.width || 318;
  const height = size?.height || 340;
  const left = Math.max(10, Math.min(viewport.width - width - 10, anchor.left));
  let top = anchor.bottom + 6;
  if (top + height > viewport.height - 10) top = Math.max(10, anchor.top - height - 6);
  return { left: Math.round(left), top: Math.round(top) };
}
