// === assets/board.js — 展示板：板 CRUD、条目增删排序、版面设置、打印（全部 / 仅新增）与纸面记录 ===
// 依赖 core.js（api / uiToast / uiPrompt / uiConfirm / filterItems）、labels.js（lblChips / LABELS）、
// questions.js（viewQ / QUESTION_CACHE）；必须排在 export.js 之后。
// 打印链路：/api/export {format:'board', mode} → 自包含 HTML（board.js 模板在浏览器里分页）
//   → 打印；「标记为已打印」时把同一份 HTML 放进隐藏 iframe 测量版面 → POST /api/board/printed 记录纸面。
// 页数估算：同一份 HTML 在隐藏 iframe 里排一次；新估算会取消上一次未完成的；打印预览窗口
//   排好后回传的版面直接当估算结果，预览开着时不再后台重算。
let BOARD_DATA = [];
let BOARD_CURRENT = '';
let BOARD_DETAIL = null;
let BOARD_SAVE_TIMER = null;
let BOARD_DIRTY = null;                       // 待保存的脏字段 {items?:true, print?:true}
let BOARD_SELECTED_UID = '';
let BOARD_PRINT_MODE = 'all';                 // 'all' | 'new'
let BOARD_LOAD_SEQ = 0;                       // 数据加载序号：只采纳最后一次请求的结果
let BOARD_FOLDERS = [];                       // 展示板文件夹（单层，未归档用空 folder_id 表示）
let BOARD_POP = null;                         // 当前打开的版式与打印浮层 {kind:'settings', node, anchor}
let BOARD_LAYOUT_CONFIRM = null;              // 锁定版式的确认请求，合并同一轮输入事件
let BOARD_LAYOUT_GRANTED = false;             // 本轮去抖保存前已确认过版式变更
const CUT_LINES = ['none', 'dash', 'solid'];  // 与 omrs/boards.py::CUT_LINES 同步
// 纸面几何常量：与导出模板同解，改一处就要改另一处。
//   board.css: .question-gap{height:calc(var(--gap-lines) * 18px)}
//   board.js:  const MM = 3.779528
const BOARD_LINE_PX = 18;
const BOARD_MM_PX = 3.779528;
// 「留几行」对使用者是抽象的，「大概多少厘米」才是纸上真正能写多少字的直觉
function boardGapCm(lines) {
  return Math.round(clampNumber(lines, 0, 48, 0) * BOARD_LINE_PX / BOARD_MM_PX / 10 * 10) / 10;
}
const BOARD_LAST_KEY = 'omrs-board-last';
const BOARD_FOLD_KEY = 'omrs-board-folders-collapsed';   // 折叠状态属于 UI 状态，不进 boards.json
const BOARD_VIEW_KEY = 'omrs-board-view';               // 纸面 / 列表 / 画廊，同样只存本地
const BOARD_WINDOWS = new Map();              // 打印预览窗口 -> {boardId, mode}

// ---------- 小工具 ----------
function boardAvailableBoards() { return Array.isArray(BOARD_DATA) ? BOARD_DATA : []; }
function boardView() {
  try { const value = localStorage.getItem(BOARD_VIEW_KEY); return value === 'list' || value === 'gallery' ? value : 'paper'; }
  catch (error) { return 'paper'; }
}
function boardSetView(view) {
  const next = view === 'list' || view === 'gallery' ? view : 'paper';
  try { localStorage.setItem(BOARD_VIEW_KEY, next); } catch (error) {}
  boardRender();
}
// 导出内容签名：题目集合、顺序、以及会影响「这题上不上纸」的停用/缺失状态。
// 版面设置不在里面，因为几何改动走 relayout，不该触发重新导出。
function boardContentSignature() {
  return (BOARD_DETAIL?.items || [])
    .map(item => `${item.uid || item.question_id || ''}${item.missing ? '!' : ''}${item.suspended ? '-' : ''}`)
    .join(',');
}
// 传给预览的逐题留白：null 原样保留，让 iframe 自己按当前全局值继承
function boardPreviewGaps() {
  const map = {};
  (BOARD_DETAIL?.items || []).forEach(item => { if (item.uid) map[item.uid] = item.gap_lines == null ? null : clampNumber(item.gap_lines, 0, 48, 0); });
  return map;
}
function boardLastId() { try { return localStorage.getItem(BOARD_LAST_KEY) || ''; } catch (error) { return ''; } }
function boardRemember(id) { BOARD_CURRENT = id || ''; try { if (id) localStorage.setItem(BOARD_LAST_KEY, id); } catch (error) {} }
function boardCurrentItem(uid) { return (BOARD_DETAIL?.items || []).find(item => item.uid === uid || item.question_id === uid) || null; }
function boardSelectedIndex() { return (BOARD_DETAIL?.items || []).findIndex(item => item.uid === BOARD_SELECTED_UID); }
function boardMoveItems(items, from, to) {
  const result = [...(items || [])];
  if (from < 0 || from >= result.length || to < 0 || to >= result.length || from === to) return result;
  const [item] = result.splice(from, 1);
  result.splice(to, 0, item);
  return result;
}
// gap_lines 是「这道题之后留白的绝对行数」：null = 继承板的全局设置，数字 = 覆盖。
// 原样把 null 传回后端，否则会被当成 0 行，行内留白一保存就退化成「不留白」。
function boardItemsPayload(items) {
  return (items || []).map(item => ({
    question_id: item.question_id || '', uid: item.uid || '', added_at: item.added_at || '',
    gap_lines: item.gap_lines == null ? null : clampNumber(item.gap_lines, 0, 48, 0), pin: !!item.pin,
  }));
}
function boardEffectiveGap(item, print) {
  const own = (item || {}).gap_lines;
  return own == null ? clampNumber((print || {}).gap_lines, 0, 48, 2) : clampNumber(own, 0, 48, 0);
}
function boardUniqueUids(uids) { return [...new Set((uids || []).map(uid => String(uid || '').trim()).filter(Boolean))]; }
function boardPost(path, body) { return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) }); }
function boardFormatTime(value) { const raw = String(value || ''); if (!raw) return ''; const date = new Date(raw); if (Number.isNaN(date.getTime())) return raw.slice(0, 16).replace('T', ' '); const pad = n => String(n).padStart(2, '0'); return `${date.getMonth() + 1}/${date.getDate()} ${pad(date.getHours())}:${pad(date.getMinutes())}`; }
function boardPrintedSummary(board) { return (board || BOARD_DETAIL || {}).printed_summary || { pages: 0, count: 0, new_count: 0, changed_count: 0 }; }
function boardHasPaper(board) { return boardPrintedSummary(board).pages > 0; }
function showBoardToast(message, options) { return uiToast(message, options); }

// ---------- 数据加载 ----------
async function boardInit() {
  if (!document.getElementById('panel-board')) return;
  await boardReloadData();
}
// 收件箱录完题会同时触发全局 reloadData() 和用户点的「加入展示板」，两条链都会重读展示板；
// 用序号保证先发后到的旧响应不会把新数据盖掉。
async function boardReloadData() {
  if (!document.getElementById('bd-list')) return;
  if (typeof boardPreviewInvalidate === 'function') boardPreviewInvalidate();
  const seq = ++BOARD_LOAD_SEQ;
  try {
    const result = await api('/api/boards');
    if (seq !== BOARD_LOAD_SEQ) return;
    BOARD_DATA = result.boards || [];
    BOARD_FOLDERS = result.folders || [];
    const preferred = BOARD_CURRENT || boardLastId();
    const selected = BOARD_DATA.find(board => board.id === preferred) || BOARD_DATA[0];
    if (selected) {
      boardRemember(selected.id);
      await boardLoad(selected.id, false, seq);
      if (seq !== BOARD_LOAD_SEQ) return;
    } else {
      BOARD_DETAIL = null;
      BOARD_CURRENT = '';
    }
  } catch (error) {
    if (seq !== BOARD_LOAD_SEQ) return;
    BOARD_DATA = [];
    BOARD_FOLDERS = [];
    BOARD_DETAIL = null;
  }
  BOARD_LAYOUT_GRANTED = false;
  boardRender();
}
async function boardLoad(id, render = true, seq = null) {
  if (!id) return;
  await boardFlushSave();          // 切板前把上一块板的待存改动落盘，否则会写到新板上或整个丢掉
  const token = seq ?? ++BOARD_LOAD_SEQ;
  boardRemember(id);   // 先记住用户选的板：期间若有 reloadData 并发进来，重载的也是这个板
  try {
    const result = await api(`/api/board?id=${encodeURIComponent(id)}`);
    if (token !== BOARD_LOAD_SEQ) return;
    BOARD_DETAIL = result.board || null;
    if (!BOARD_DETAIL?.items?.some(item => item.uid === BOARD_SELECTED_UID)) BOARD_SELECTED_UID = '';
    if (BOARD_PRINT_MODE === 'new' && !boardHasPaper()) BOARD_PRINT_MODE = 'all';
    if (render) boardRender();
  } catch (error) {
    if (token !== BOARD_LOAD_SEQ) return;
    uiToast(`读取展示板失败：${error.message}`, { kind: 'error' });
  }
}

// ---------- 渲染：板列表（文件夹 → 板 两级树） ----------
function boardMoveMenuHtml(board) {
  const targets = BOARD_FOLDERS.filter(folder => folder.id !== board.folder_id);
  if (!targets.length && !board.folder_id) return '';
  return `<div class="bd-menu-sec">移到</div>${targets.map(folder =>
    `<button type="button" data-board-action="move-to" data-board-id="${escapeAttr(board.id)}" data-board-folder="${escapeAttr(folder.id)}">${escapeHtml(folder.name)}</button>`).join('')}
    ${board.folder_id ? `<button type="button" data-board-action="move-to" data-board-id="${escapeAttr(board.id)}" data-board-folder="">未归档</button>` : ''}
    <button type="button" data-board-action="move-new" data-board-id="${escapeAttr(board.id)}">新文件夹…</button>`;
}

function boardItemHtml(board) {
  const paper = board.printed_summary || {};
  const bits = [`${board.count} 题`];
  if (paper.pages) bits.push(`<span class="pt">已印 ${paper.pages} 页</span>${paper.new_count ? `<span class="nw"> +${paper.new_count}</span>` : ''}`);
  if (board.missing) bits.push(`<span class="warn">缺失 ${board.missing}</span>`);
  if (board.suspended) bits.push(`停用 ${board.suspended}`);
  bits.push(boardFormatTime(board.updated_at));
  return `<div class="bd-board-item ${board.id === BOARD_CURRENT ? 'on' : ''}" draggable="true"
    data-board-select="${escapeAttr(board.id)}" data-board-drag="${escapeAttr(board.id)}"
    title="${escapeAttr(board.note || board.name)}">
    <div class="bd-board-name">${escapeHtml(board.name)}</div>
    <div class="bd-board-actions"><button type="button" class="btn sm ghost" data-board-menu-toggle="${escapeAttr(board.id)}" aria-label="展示板操作">⋯</button>
      <div class="bd-board-menu" data-board-menu="${escapeAttr(board.id)}">
        <button type="button" data-board-action="rename" data-board-id="${escapeAttr(board.id)}">重命名</button>
        <button type="button" data-board-action="note" data-board-id="${escapeAttr(board.id)}">备注…</button>
        <button type="button" data-board-action="duplicate" data-board-id="${escapeAttr(board.id)}">复制</button>
        <button type="button" data-board-action="export-board" data-board-id="${escapeAttr(board.id)}">导出 HTML</button>
        ${boardMoveMenuHtml(board)}
        <button type="button" class="danger" data-board-action="delete" data-board-id="${escapeAttr(board.id)}">删除</button>
      </div></div>
    <div class="bd-board-meta">${bits.join(' · ')}</div>
  </div>`;
}

function boardGroupHtml(group, collapsed) {
  if (!group.id) {
    // 未归档：不是真文件夹，没有重命名 / 删除，只是一个恒在最后的落脚点
    return `<div class="bd-folder plain" data-board-folder-drop="">
        <span class="bd-folder-name">未归档</span><em class="bd-folder-count">${group.boards.length}</em></div>
      <div class="bd-folder-body">${group.boards.map(boardItemHtml).join('')}</div>`;
  }
  const folded = collapsed.has(group.id);
  const newCount = group.boards.reduce((sum, board) => sum + asNumber(board.printed_summary?.new_count, 0), 0);
  const total = group.boards.reduce((sum, board) => sum + asNumber(board.count, 0), 0);
  return `<div class="bd-folder ${folded ? 'folded' : ''}" draggable="true"
      data-board-folder-drop="${escapeAttr(group.id)}" data-board-folder-drag="${escapeAttr(group.id)}"
      title="${escapeAttr(`${group.name}：${group.boards.length} 板 · ${total} 题${newCount ? ` · ${newCount} 题还没印上纸` : ''}`)}">
      <button type="button" class="bd-folder-chev" data-board-fold="${escapeAttr(group.id)}" aria-expanded="${folded ? 'false' : 'true'}" aria-label="折叠">▾</button>
      <span class="bd-folder-name">${escapeHtml(group.name)}</span>
      ${newCount ? `<span class="nw bd-folder-new" title="这组里有 ${newCount} 题还没印上纸">+${newCount}</span>` : ''}
      <em class="bd-folder-count">${group.boards.length}</em>
      <div class="bd-board-actions"><button type="button" class="btn sm ghost" data-board-menu-toggle="${escapeAttr(group.id)}" aria-label="文件夹操作">⋯</button>
        <div class="bd-board-menu" data-board-menu="${escapeAttr(group.id)}">
          <button type="button" data-board-action="folder-rename" data-board-folder-id="${escapeAttr(group.id)}">重命名</button>
          <button type="button" data-board-action="folder-new-board" data-board-folder-id="${escapeAttr(group.id)}">在此新建板</button>
          <button type="button" data-board-action="folder-up" data-board-folder-id="${escapeAttr(group.id)}">上移</button>
          <button type="button" data-board-action="folder-down" data-board-folder-id="${escapeAttr(group.id)}">下移</button>
          <button type="button" class="danger" data-board-action="folder-delete" data-board-folder-id="${escapeAttr(group.id)}">删除文件夹</button>
        </div></div></div>
    <div class="bd-folder-body">${folded ? '' : (group.boards.length
      ? group.boards.map(boardItemHtml).join('')
      : '<div class="bd-folder-empty">把板拖进来</div>')}</div>`;
}

function boardListHtml() {
  if (!BOARD_DATA.length && !BOARD_FOLDERS.length) {
    return `<div class="bd-empty"><div class="bd-empty-icon">▤</div><strong>还没有展示板</strong>
      <p>把考前必看的题集中到一个板里，随时加题、重排，打印成左题右空的活页纸；之后新增的题还能只补印一页。</p>
      <button class="btn sm primary" type="button" data-board-action="create">新建第一个展示板</button></div>`;
  }
  const collapsed = boardFolderCollapsed();
  const groups = boardFolderTree(BOARD_DATA, BOARD_FOLDERS);
  return `<div class="bd-list-head"><div class="card-title">展示板<small>${BOARD_DATA.length}</small></div>
      <div class="bd-board-actions"><button class="btn sm primary" type="button" data-board-menu-toggle="__new__" title="新建（N）">＋ 新建 ▾</button>
        <div class="bd-board-menu" data-board-menu="__new__">
          <button type="button" data-board-action="create">新建展示板</button>
          <button type="button" data-board-action="folder-create">新建文件夹</button>
        </div></div></div>
    <div class="bd-tree" data-board-tree>${groups.map(group => boardGroupHtml(group, collapsed)).join('')}</div>
    <div class="hint bd-list-note">板里存的是题目引用，题目改了重印即最新；纸面标题固定为「错题集」。</div>`;
}

// ---------- 渲染：板内容 ----------
function boardRowHtml(item, index, hasPaper) {
  const labels = typeof lblChips === 'function' ? lblChips(item.labels || [], { add: true }) : '';
  const badges = [];
  if (item.missing) badges.push('<span class="bd-badge muted">缺失</span>');
  else if (item.suspended) badges.push('<span class="bd-badge muted">停用</span>');
  if (hasPaper && !item.missing) {
    if (item.printed) badges.push(`<span class="bd-badge printed" title="已经打印在纸上">已印${item.printed_page ? ` p.${item.printed_page}` : ''}</span>`);
    else if (!item.suspended) badges.push('<span class="bd-badge new" title="纸上还没有这道题">新增</span>');
    if (item.changed) badges.push('<span class="bd-badge changed" title="打印后题目正文改过，纸面仍是旧版">已改动</span>');
  }
  const due = typeof getDueDays === 'function' && !item.missing ? formatDueInfo(getDueDays({ due_date: item.due_date })) : '';
  // 数字框留空 = 继承板的全局留白（placeholder 显示继承成几行），填数字 = 覆盖成绝对行数
  const inherited = clampNumber((BOARD_DETAIL?.print || {}).gap_lines, 0, 48, 2);
  const gap = item.gap_lines == null ? '' : clampNumber(item.gap_lines, 0, 48, 0);
  const meta = item.missing
    ? '<span class="warn">题目已删除或无法解析；导出时跳过</span>'
    : `<span>${escapeHtml(item.subject || '')} · ${escapeHtml(item.category || '')}</span><span>难度 ${escapeHtml(item.difficulty ?? '')}</span><span class="bd-mastery">${typeof masteryBarHtml === 'function' ? masteryBarHtml(item, 44) : `${(asNumber(item.mastery, 0) * 100).toFixed(0)}%`}</span>${due ? `<span>${due}</span>` : ''}`;
  return `<div class="bd-row ${item.missing ? 'missing' : ''} ${item.suspended ? 'suspended' : ''} ${BOARD_SELECTED_UID === item.uid ? 'is-selected' : ''}" draggable="true" tabindex="0" data-board-row="${escapeAttr(item.uid)}" data-board-index="${index}" title="双击或 Enter 打开题目">
    <span class="bd-grip" title="拖拽排序（Ctrl+↑/↓ 也可）">⠿</span><span class="bd-no">${index + 1}</span>
    <div class="bd-main"><span class="bd-row-head"><strong>${escapeHtml(item.uid || item.question_id || '未知题目')}</strong>${badges.join('')}<span class="bd-row-labels" data-lbl-target="${escapeAttr(item.uid)}">${labels}</span></span><span class="bd-row-meta">${meta}</span></div>
    <div class="bd-acts"><label class="bd-gap ${gap === '' ? '' : 'has'}" title="这道题之后留几行空白（每行 18px）；留空表示继承板设置的 ${inherited} 行">留白<input type="number" class="input" min="0" max="48" value="${gap}" placeholder="${inherited}" data-board-gap="${escapeAttr(item.uid)}"></label>
      <button type="button" class="btn sm ghost bd-row-open" data-board-action="preview-item" data-board-uid="${escapeAttr(item.uid)}" ${item.missing ? 'disabled' : ''} title="打开题目详情">详情</button>
      <button type="button" class="btn sm ghost bd-row-x" data-board-action="remove-item" data-board-uid="${escapeAttr(item.uid)}" title="从板中移除（Delete）" aria-label="移除">✕</button></div>
  </div>`;
}
function boardContentHtml() {
  if (!BOARD_DETAIL) return '<div class="empty-inline">请选择或新建一个展示板。</div>';
  const items = BOARD_DETAIL.items || [];
  const missing = items.filter(item => item.missing).length;
  const suspended = items.filter(item => item.suspended && !item.missing).length;
  const paper = boardPrintedSummary();
  const hasPaper = paper.pages > 0;
  const subjects = {};
  items.filter(item => !item.missing).forEach(item => { subjects[item.subject || '未分科'] = (subjects[item.subject || '未分科'] || 0) + 1; });
  const subText = Object.entries(subjects).map(([k, v]) => `${k} ${v}`).join(' · ');
  const paperText = hasPaper ? ` · <span class="pt">已印 ${paper.count} 题 / ${paper.pages} 页</span>${paper.new_count ? ` · <span class="nw">新增 ${paper.new_count} 题未打印</span>` : ''}` : '';
  const warns = [];
  if (missing) warns.push(`<div class="bd-warn danger">⚠ ${missing} 道题已缺失（文件被删或无法解析），导出时会跳过。<button class="btn sm" type="button" data-board-action="clean-missing">清理缺失条目</button></div>`);
  if (suspended) warns.push(`<div class="bd-warn">⚠ ${suspended} 道题已停用，导出时会跳过。<button class="btn sm" type="button" data-board-action="clean-suspended">移出停用题</button></div>`);
  if (hasPaper && paper.changed_count) warns.push(`<div class="bd-warn">✎ ${paper.changed_count} 道已打印题目的正文在打印后改过，纸面仍是旧版；需要更新请「打印全部」换新纸。</div>`);
  const view = boardView();
  const segs = [['paper', '纸面'], ['list', '列表'], ['gallery', '画廊']];
  const viewSeg = `<span class="seg bd-views" data-board-views>${segs.map(([key, label]) =>
    `<button type="button" class="${view === key ? 'on' : ''}" data-board-view="${key}">${label}</button>`).join('')}</span>`;
  return `<div class="bd-toolbar"><div class="bd-title-wrap"><div class="bd-title" data-board-rename-target title="双击重命名">${escapeHtml(BOARD_DETAIL.name)}</div><div class="bd-sub">${items.length} 题${subText ? ` · ${subText}` : ''}${paperText}${BOARD_DETAIL.note ? ` · ${escapeHtml(BOARD_DETAIL.note)}` : ''}${BOARD_DETAIL.print?.locked ? ' · <span class="bd-lock-state">版式已锁定</span>' : ''}</div></div>
    <button class="btn sm primary" type="button" data-board-action="add" title="添加题目（A）">＋ 添加题目</button><button class="btn sm" type="button" data-board-action="sync-label">按标记同步</button>
    <span class="bd-sort-wrap"><button class="btn sm" type="button" data-board-sort-toggle>排序 ▾</button><div class="bd-sort-menu" data-board-sort-menu><button type="button" data-board-sort="subject">按科目 / 分类</button><button type="button" data-board-sort="mastery">按熟练度 ↑</button><button type="button" data-board-sort="due">按到期</button><button type="button" data-board-sort="added">按加入时间</button><button type="button" data-board-sort="reverse">反转顺序</button></div></span>
    <button class="btn sm" type="button" data-board-pop="settings" aria-expanded="false" aria-haspopup="dialog" title="版式、打印与锁定设置">版式与打印 ▾</button>
    ${viewSeg}<button class="btn sm ghost" type="button" data-board-action="clear" ${items.length ? '' : 'disabled'}>清空</button></div>
    ${view === 'paper' ? boardPagerHtml() : ''}
    ${hasPaper ? '<div class="hint bd-order-note">已打印题目在纸上的位置已固定；这里重排只影响下次「打印全部」，「仅打印新增」按纸面顺序续排。</div>' : ''}
    ${warns.join('')}
`;
}
// 条目列表只在列表视图渲染；纸面视图下中栏交给常驻预览 iframe
function boardContentBodyHtml() {
  if (!BOARD_DETAIL) return '';
  if (boardView() === 'gallery') return boardGalleryHtml();
  if (boardView() !== 'list') return '';
  const items = BOARD_DETAIL.items || [];
  const hasPaper = boardPrintedSummary().pages > 0;
  return `<div class="bd-rows" data-board-rows>${items.length ? items.map((item, index) => boardRowHtml(item, index, hasPaper)).join('') : '<div class="bd-empty"><div class="bd-empty-icon">＋</div><strong>板里还没有题目</strong>点「添加题目」筛选加入，或在题库勾选后批量加入；题目 Modal、反馈判错、录入题目后也有「加入展示板」。</div>'}</div>`;
}
// ---------- 画廊视图 ----------
// 与题目库画廊共用 qvGalleryCard 骨架；差异（序号、纸面状态标、定位按钮）由这里算好传进去。
// 缩略题面同样走 qview，与 Modal / 题库卡片是同一套渲染，不另写一份模板。
const BOARD_CARD_OPTS = { layout: 'stack', showMeta: false, showAnswer: false, showNotes: false, showHistory: false, actions: [], bare: true, clamp: 5 };
function boardBadgesHtml(item, hasPaper) {
  const badges = [];
  if (item.missing) badges.push('<span class="gc-flag muted">缺失</span>');
  else if (item.suspended) badges.push('<span class="gc-flag muted">停用</span>');
  if (hasPaper && !item.missing && !item.suspended) {
    badges.push(item.printed
      ? `<span class="gc-flag green" title="已经打印在纸上">已印${item.printed_page ? ` p.${item.printed_page}` : ''}</span>`
      : '<span class="gc-flag yellow" title="纸上还没有这道题">新增</span>');
    if (item.changed) badges.push('<span class="gc-flag red" title="打印后正文改过，纸面仍是旧版">已改动</span>');
  }
  return badges.join('');
}
function boardGalleryCardHtml(item, index, hasPaper) {
  const uid = item.uid || '';
  const cached = typeof QUESTION_CACHE !== 'undefined' ? QUESTION_CACHE[uid] : null;
  const previewHtml = item.missing
    ? '<div class="preview-placeholder">题目已删除或无法解析，导出时会跳过</div>'
    : (cached && typeof qvHtml === 'function' ? qvHtml(cached, item, BOARD_CARD_OPTS) : '');
  const gap = boardEffectiveGap(item, BOARD_DETAIL.print);
  const foot = [
    `<span class="gc-stat muted">${escapeHtml(item.subject || '')}${item.category ? ` · ${escapeHtml(item.category)}` : ''}</span>`,
    item.difficulty != null && item.difficulty !== '' ? `<span class="gc-stat muted">难度 ${escapeHtml(item.difficulty)}</span>` : '',
    `<span class="gc-stat muted" title="这道题之后留白 ${gap} 行">留白 ${gap} 行</span>`,
  ].filter(Boolean).join('');
  return qvGalleryCard({
    uid,
    className: `bd-gallery-card ${item.missing ? 'missing' : ''} ${item.suspended ? 'q-card-suspended' : ''} ${BOARD_SELECTED_UID === uid ? 'is-selected' : ''}`,
    rowAttr: `data-board-row="${escapeAttr(uid)}" data-board-index="${index}" tabindex="0" title="点击选中，双击打开题目"`,
    leadHtml: `<span class="bd-gc-no">${index + 1}</span>`,
    idHtml: typeof qvGalleryIdHtml === 'function' ? qvGalleryIdHtml(uid, item.category) : escapeHtml(uid),
    flagsHtml: boardBadgesHtml(item, hasPaper),
    menuHtml: `<button type="button" class="btn sm ghost" data-board-action="gallery-locate" data-board-uid="${escapeAttr(uid)}" title="回到纸面上这道题" ${item.missing || item.suspended ? 'disabled' : ''}>⌖</button>`,
    previewClass: 'board-gallery-preview',
    previewHtml,
    footHtml: foot,
    labelsHtml: typeof lblChips === 'function' ? lblChips(item.labels || [], { add: true, max: 3 }) : '',
  });
}
function boardGalleryHtml() {
  const items = BOARD_DETAIL.items || [];
  if (!items.length) return '<div class="bd-empty"><div class="bd-empty-icon">＋</div><strong>板里还没有题目</strong>点「添加题目」筛选加入，或在题库勾选后批量加入。</div>';
  const hasPaper = boardPrintedSummary().pages > 0;
  return `<div class="gallery-grid bd-gallery">${items.map((item, index) => boardGalleryCardHtml(item, index, hasPaper)).join('')}</div>`;
}
// 与题库画廊同样的懒水合：先出骨架，再逐张把题面填进去，避免一次性阻塞
async function boardHydrateGallery() {
  if (boardView() !== 'gallery' || typeof ensureQuestionDetail !== 'function') return;
  const boardId = BOARD_DETAIL?.id;
  const nodes = [...document.querySelectorAll('.board-gallery-preview[data-question-preview-uid]')];
  await Promise.all(nodes.map(async node => {
    const uid = node.dataset.questionPreviewUid;
    const item = boardCurrentItem(uid);
    if (!uid || !item || item.missing) return;
    let detail = null;
    try { detail = await ensureQuestionDetail(uid); } catch (error) { return; }
    // 期间换了板或换了视图：这张卡已经不在页面上了，别往里写
    if (!detail || BOARD_DETAIL?.id !== boardId || !node.isConnected) return;
    node.innerHTML = qvHtml(detail, item, BOARD_CARD_OPTS);
    node.classList.toggle('is-clipped', node.scrollHeight - node.clientHeight > 4);
  }));
}

// 翻页条：页数不再单独跑一遍排版估算，直接读预览 iframe 已经排好的版面
function boardPagerHtml() {
  const layout = typeof boardPreviewLayout === 'function' ? boardPreviewLayout() : null;
  const view = typeof boardPreviewView === 'function' ? boardPreviewView() : { page: 1 };
  const numbers = layout?.page_numbers || [];
  const paper = boardPrintedSummary();
  const summary = layout ? boardEstimateText(layout, boardEffectiveMode(), BOARD_DETAIL.print) : '<span class="busy">正在排版…</span>';
  return `<div class="bd-pager" data-board-pager>
    <button class="btn sm ghost" type="button" data-board-page="prev" ${numbers.length > 1 ? '' : 'disabled'} title="上一页（←）">←</button>
    <label class="bd-page-jump">第 <input class="input" type="number" min="1" value="${view.page || numbers[0] || 1}" data-board-page-input> / ${layout?.pages || '—'} 页</label>
    <button class="btn sm ghost" type="button" data-board-page="next" ${numbers.length > 1 ? '' : 'disabled'} title="下一页（→）">→</button>
    ${paper.new_count ? '<button class="btn sm ghost" type="button" data-board-page="new" title="跳到第一道还没印在纸上的题">⚑ 跳到新增</button>' : ''}
    <span class="bd-pager-sum">${summary}</span>
    <span class="seg bd-zoom"><button type="button" data-board-zoom="fit">适应宽度</button><button type="button" data-board-zoom="1">100%</button></span>
  </div>`;
}

// ---------- 每题留白 ----------
// 唯一写入口：列表行数字框、检视条、拖切割线都走它。画面先动（relayout 去抖 120ms、零请求），
// 保存走 500ms 脏队列，与版面改动合并成一次 POST。
async function boardSetItemGap(uid, value, options = {}) {
  const item = boardCurrentItem(uid);
  if (!item || !BOARD_DETAIL) return null;
  if (boardLayoutLocked() && !BOARD_LAYOUT_GRANTED && !(await boardAllowLayoutChange())) {
    document.querySelectorAll(`[data-board-gap="${CSS.escape(uid)}"],[data-board-inspect-gap="${CSS.escape(uid)}"]`).forEach(node => {
      node.value = item.gap_lines == null ? '' : item.gap_lines;
    });
    return null;
  }
  if (boardLayoutLocked()) BOARD_LAYOUT_GRANTED = true;
  item.gap_lines = value == null ? null : clampNumber(value, 0, 48, 0);
  boardPushRelayout();
  boardMarkDirty('items');
  // 列表行的数字框与检视条显示同一个值，改一处另一处要跟上（正在输入的那个不动）
  document.querySelectorAll(`[data-board-gap="${CSS.escape(uid)}"],[data-board-inspect-gap="${CSS.escape(uid)}"]`).forEach(node => {
    if (node !== document.activeElement) node.value = item.gap_lines == null ? '' : item.gap_lines;
    node.closest('.bd-gap,.bd-inspect-gap')?.classList.toggle('has', item.gap_lines != null);
  });
  if (options.keepFocus) {
    // 输入过程中不重建检视条，否则每敲一个数字就丢一次焦点；只更新厘米换算
    const cm = document.querySelector('.bd-inspect-cm');
    if (cm) cm.textContent = `行 ≈ ${boardGapCm(boardEffectiveGap(item, BOARD_DETAIL.print))} cm${item.gap_lines == null ? '（继承）' : ''}`;
  } else if (uid === BOARD_SELECTED_UID) {
    boardRenderInspect();
  }
  return item;
}

// ---------- 选中题检视条 ----------
// 纸面视图里没有行内控件可点，选中一道题之后的所有操作都收在这一条上。
// 只重写 #bd-inspect 这一个节点：整块渲染会把常驻预览 iframe 卷进去重载。
function boardInspectHtml() {
  const item = boardCurrentItem(BOARD_SELECTED_UID);
  if (!item) return '';
  const index = (BOARD_DETAIL.items || []).indexOf(item);
  const print = BOARD_DETAIL.print || {};
  const inherited = clampNumber(print.gap_lines, 0, 48, 2);
  const own = item.gap_lines;
  const effective = boardEffectiveGap(item, print);
  const badges = [];
  if (item.missing) badges.push('<span class="bd-badge muted">缺失</span>');
  else if (item.suspended) badges.push('<span class="bd-badge muted">停用</span>');
  if (boardHasPaper() && !item.missing && !item.suspended) {
    badges.push(item.printed
      ? `<span class="bd-badge printed">已印${item.printed_page ? ` p.${item.printed_page}` : ''}</span>`
      : '<span class="bd-badge new">新增</span>');
    if (item.changed) badges.push('<span class="bd-badge changed" title="打印后正文改过，纸面仍是旧版">已改动</span>');
  }
  return `<div class="bd-inspect-main">
      <span class="bd-inspect-no">第 ${index + 1} 题</span>
      <strong class="bd-inspect-uid" title="${escapeAttr(item.uid || item.question_id || '')}">${escapeHtml(item.uid || item.question_id || '未知题目')}</strong>
      ${badges.join('')}
      <span class="bd-inspect-meta">${escapeHtml(item.subject || '')}${item.category ? ` · ${escapeHtml(item.category)}` : ''}</span>
    </div>
    <label class="bd-inspect-gap ${own == null ? '' : 'has'}">题后留白
      <input class="input" type="number" min="0" max="48" value="${own == null ? '' : clampNumber(own, 0, 48, 0)}" placeholder="${inherited}" data-board-inspect-gap="${escapeAttr(item.uid)}" title="留空 = 继承板设置的 ${inherited} 行">
      <span class="bd-inspect-cm">行 ≈ ${boardGapCm(effective)} cm${own == null ? '（继承）' : ''}</span>
    </label>
    ${own == null ? '' : '<button class="btn sm ghost" type="button" data-board-action="inspect-inherit" title="改回继承板的全局留白">继承</button>'}
    <span class="grow"></span>
    <button class="btn sm ghost" type="button" data-board-action="inspect-locate" title="翻到这道题所在的页">⌖ 定位</button>
    <button class="btn sm ghost" type="button" data-board-action="inspect-regen" title="题目正文在别处改过、预览还是旧的时，强制重新生成纸面">↻ 重新生成</button>
    <button class="btn sm ghost" type="button" data-board-action="inspect-open" ${item.missing ? 'disabled' : ''} title="打开题目详情">打开题目</button>
    <button class="btn sm ghost bd-inspect-x" type="button" data-board-action="inspect-clear" aria-label="取消选中">✕</button>
    ${item.printed ? '<div class="bd-inspect-note">这道题纸上已经有了：改留白只影响下次「打印全部」和当前预览，<b>不会改动已印出来的纸</b>，也不会改纸面记录。</div>' : ''}`;
}
function boardRenderInspect() {
  const node = document.getElementById('bd-inspect');
  if (!node) return;
  const html = BOARD_DETAIL && boardView() === 'paper' ? boardInspectHtml() : '';
  node.innerHTML = html;
  node.hidden = !html;
}
// 选中的唯一入口：纸面点击、列表点击、键盘上下都走它，三处选中态才不会各说各话
function boardSelect(uid) {
  BOARD_SELECTED_UID = uid || '';
  document.querySelectorAll('[data-board-row]').forEach(node =>
    node.classList.toggle('is-selected', node.dataset.boardRow === BOARD_SELECTED_UID));
  boardRenderInspect();
}

// 版式与打印属于同一组会影响纸面的设置，统一收进一个浮层，避免用户
// 在工具条上来回寻找「版式」和「打印」两个入口。
function boardSettingsPopHtml() {
  const print = BOARD_DETAIL.print || {};
  const paper = boardPrintedSummary();
  const hasPaper = paper.pages > 0;
  const mode = BOARD_PRINT_MODE === 'new' && hasPaper ? 'new' : 'all';
  const ratio = Math.round(asNumber(print.note_ratio, .50) * 100);
  const cut = CUT_LINES.includes(print.cut_line) ? print.cut_line : 'dash';
  const modeHint = mode === 'new'
    ? `只排纸上还没有的 ${paper.new_count} 题，接在第 ${paper.cursor?.page || paper.pages} 页的空白处。`
    : `整板从第 1 页重新排版，用新纸打${hasPaper ? '；确认后会替换现有纸面记录' : ''}。`;
  return `<div class="bd-pop-head"><span>版式与打印</span><small>${print.locked ? '版式已锁定' : '可直接调整'}</small><button type="button" class="bd-pop-x" data-board-pop-close aria-label="关闭">✕</button></div>
    <div class="bd-field"><label>右侧留白 <b data-board-ratio-value>${ratio}%</b><span class="hint">题栏约 ${boardColumnWidth(ratio)}px</span></label><input type="range" min="30" max="55" step="2" value="${ratio}" data-board-print="note_ratio" title="右侧空白区占内容区宽度的比例"></div>
    <div class="bd-field"><label>题间留白（行）</label><input class="input" type="number" min="0" max="24" value="${clampNumber(print.gap_lines, 0, 24, 2)}" data-board-print="gap_lines" title="每题之后空几行；单题可在列表或检视条里覆盖"></div>
    <div class="bd-field-row">
      <div class="bd-field"><label>打印范围</label><div class="seg block bd-modes" data-board-modes><button type="button" class="${mode === 'all' ? 'on' : ''}" data-board-mode="all">打印全部</button><button type="button" class="${mode === 'new' ? 'on' : ''}" data-board-mode="new" ${hasPaper ? '' : 'disabled'}>仅打印新增${hasPaper ? `（${paper.new_count}）` : ''}</button></div></div>
      <div class="bd-field"><label>答案</label><div class="seg" data-board-seg="answers"><button type="button" class="${print.answers === 'append' ? '' : 'on'}" data-value="none">不含</button><button type="button" class="${print.answers === 'append' ? 'on' : ''}" data-value="append">末页附答案</button></div></div>
    </div>
    <div class="bd-field"><label>题头显示</label><div class="bd-checks"><label><input type="checkbox" data-board-print="show_labels" ${print.show_labels !== false ? 'checked' : ''}> 标记</label><label><input type="checkbox" data-board-print="show_meta" ${print.show_meta !== false ? 'checked' : ''}> 科目 · 难度</label></div></div>
    <div class="bd-field"><label>切割线<span class="hint">每题留白末尾的裁切提示</span></label><div class="seg" data-board-seg="cut_line">${[['none', '不画'], ['dash', '虚线'], ['solid', '实线']].map(([value, label]) => `<button type="button" class="${cut === value ? 'on' : ''}" data-value="${value}">${label}</button>`).join('')}</div><div class="bd-checks"><label><input type="checkbox" data-board-print="cut_label" ${print.cut_label ? 'checked' : ''} ${cut === 'none' ? 'disabled' : ''}> 线右端标「第 N 题止」</label></div></div>
    <div class="bd-field bd-lock"><label><input type="checkbox" data-board-print="locked" ${print.locked ? 'checked' : ''}> 锁定版式</label><span class="hint">锁定后调整版式、题间留白、排序或增删题目会先确认，并把打印状态恢复为未打印。</span></div>
    <div class="hint bd-mode-hint">${modeHint}</div>
    <div class="bd-settings-actions"><button class="btn primary" type="button" data-board-action="preview" title="打印预览（P）">🖨 打印预览</button><button class="btn" type="button" data-board-action="export" title="下载自包含 HTML，离线打印">下载 HTML</button><button class="btn" type="button" data-board-action="mark-printed" title="打印后记录每道题印在第几页、印到哪里">✓ 标记为已打印</button></div>
    <div class="hint bd-print-tip">打印时选 A4、缩放 100%，不要勾「适合页面」。</div>
    <div class="bd-paper">${hasPaper ? `<div><span class="bd-paper-k">纸面记录</span>已印 <b>${paper.count}</b> 题 · <b>${paper.pages}</b> 页 · ${boardFormatTime(paper.at)}${paper.changed_count ? ` · <span class="warn">${paper.changed_count} 题已改动</span>` : ''}</div><div><span class="bd-paper-k">续排位置</span>第 <b>${paper.cursor?.page || paper.pages}</b> 页</div><button class="btn sm ghost" type="button" data-board-action="reset-printed">重置纸面记录</button>` : '<div><span class="bd-paper-k">纸面记录</span>还没有。打印后点「标记为已打印」，之后加题只需补印新增。</div>'}</div>`;
}

function boardLayoutLocked() { return !!BOARD_DETAIL?.print?.locked; }
async function boardAllowLayoutChange() {
  if (!boardLayoutLocked() || BOARD_LAYOUT_GRANTED) return true;
  if (!BOARD_LAYOUT_CONFIRM) {
    BOARD_LAYOUT_CONFIRM = uiConfirm('版式已锁定，确认修改？', {
      hint: '确认后会清空当前纸面记录，打印状态恢复为未打印，需要重新打印全部。',
      okText: '确认修改', cancelText: '保持锁定',
    }).then(ok => { BOARD_LAYOUT_CONFIRM = null; if (ok) BOARD_LAYOUT_GRANTED = true; return ok; });
  }
  return BOARD_LAYOUT_CONFIRM;
}

// 浮层：开 / 关 / 点外部关 / Esc 关 / 窄屏不出界；同一个入口再点一次是关闭
function boardPopClose() {
  if (!BOARD_POP) return;
  document.removeEventListener('keydown', BOARD_POP.onKey, true);
  document.removeEventListener('click', BOARD_POP.onOutside, true);
  window.removeEventListener('resize', BOARD_POP.onReflow);
  window.removeEventListener('scroll', BOARD_POP.onReflow, true);
  BOARD_POP.node.remove();
  const anchor = BOARD_POP.anchor;
  BOARD_POP = null;
  document.querySelectorAll('[data-board-pop]').forEach(node => {
    node.classList.remove('on');
    node.setAttribute('aria-expanded', 'false');
  });
  if (anchor?.isConnected) anchor.focus?.({ preventScroll: true });
}
// 锚定在入口按钮下方；下方放不下就往上翻，左右都夹在视口里（窄屏不出界）
function boardPopPlace() {
  if (!BOARD_POP) return;
  const box = BOARD_POP.node;
  const anchor = BOARD_POP.anchor;
  if (!anchor?.getBoundingClientRect || !anchor.isConnected) { box.classList.add('centered'); return; }
  box.classList.remove('centered');
  const rect = anchor.getBoundingClientRect();
  const width = box.offsetWidth || 300;
  const height = box.offsetHeight || 320;
  box.style.left = `${Math.max(10, Math.min(window.innerWidth - width - 10, rect.left))}px`;
  let top = rect.bottom + 6;
  if (top + height > window.innerHeight - 10) top = Math.max(10, rect.top - height - 6);
  box.style.top = `${top}px`;
}
function boardPopRefresh() {
  if (!BOARD_POP || !BOARD_DETAIL) return;
  BOARD_POP.node.innerHTML = boardSettingsPopHtml();
  boardPopPlace();
}
function boardPopOpen(kind, anchor) {
  const reopening = BOARD_POP?.kind === kind;
  boardPopClose();
  if (reopening || !BOARD_DETAIL) return;
  const node = document.createElement('div');
  node.className = 'bd-pop';
  node.setAttribute('role', 'dialog');
  node.setAttribute('aria-label', '版式与打印设置');
  document.body.appendChild(node);
  BOARD_POP = {
    kind, node, anchor,
    onKey: event => { if (event.key === 'Escape') { event.stopPropagation(); boardPopClose(); } },
    // 点浮层内部、或再点一次入口按钮（那条由 click 委托处理成 toggle）都不该在这里关
    onOutside: event => {
      if (node.contains(event.target) || event.target.closest?.('[data-board-pop]')) return;
      boardPopClose();
    },
    onReflow: () => boardPopPlace(),
  };
  document.addEventListener('keydown', BOARD_POP.onKey, true);
  document.addEventListener('click', BOARD_POP.onOutside, true);
  window.addEventListener('resize', BOARD_POP.onReflow);
  window.addEventListener('scroll', BOARD_POP.onReflow, true);
  boardPopRefresh();
  if (anchor) { anchor.classList.add('on'); anchor.setAttribute('aria-expanded', 'true'); }
  node.querySelector('input,select,button:not(.bd-pop-x)')?.focus?.({ preventScroll: true });
}

// 题栏宽度（px）：与浏览器模板 board.js 的 COL_W 同一算式（A4 793.7px 宽，左右 10mm，栏间距 24px）
function boardColumnWidth(ratioPercent) {
  const mm = 3.779528;
  return Math.round((793.7 - 20 * mm - 24) * (1 - clampNumber(ratioPercent, 30, 55, 50) / 100));
}
function boardRender() {
  const list = document.getElementById('bd-list');
  const head = document.getElementById('bd-content-head') || document.getElementById('bd-content');
  const body = document.getElementById('bd-content-body');
  if (list) list.innerHTML = boardListHtml();
  if (head) head.innerHTML = boardContentHtml();
  if (body) body.innerHTML = boardContentBodyHtml();
  // 浮层挂在 body 上，不会被上面的 innerHTML 卷走；但内容要跟着新板刷新
  if (BOARD_POP) { if (BOARD_DETAIL) boardPopRefresh(); else boardPopClose(); }
  boardRenderInspect();
  const stage = document.getElementById('bd-stage');
  const paper = !!BOARD_DETAIL && boardView() === 'paper';
  if (stage) {
    stage.hidden = !paper;
    if (paper && typeof boardPreviewMount === 'function') boardPreviewMount(stage);
  }
  boardBindDrag();
  boardBindTreeDrag();
  boardSyncPreview();
  if (boardView() === 'gallery') boardHydrateGallery();
}
// 只重画翻页条，不动舞台：版面回传后刷新页码 / 页数，避免整块 innerHTML 把 iframe 卷进去
function boardRenderPager() {
  if (!BOARD_DETAIL || boardView() !== 'paper') return;
  const node = document.querySelector('[data-board-pager]');
  if (!node) return;
  const wrap = document.createElement('div');
  wrap.innerHTML = boardPagerHtml();
  node.replaceWith(wrap.firstElementChild);
}

// ---------- 板 CRUD ----------
async function boardCreate(initialUids = null, folderId = '') {
  const folder = BOARD_FOLDERS.find(item => item.id === folderId);
  const name = await uiPrompt('新建展示板', '', {
    placeholder: '如：考前速览·三角函数',
    hint: folder ? `放进「${folder.name}」；板名只在系统内使用，纸面标题固定为「错题集」。`
                 : '板名只在系统内使用，纸面标题固定为「错题集」。',
  });
  if (!name) return null;
  try {
    const result = await boardPost('/api/board/create', { name, uids: initialUids || [], folder_id: folderId || '' });
    boardRemember(result.board.id);
    BOARD_DETAIL = result.board;
    await boardReloadData();
    uiToast(`已新建《${name}》${initialUids?.length ? `，加入 ${result.board.items.length} 题` : ''}`);
    return result.board;
  } catch (error) { uiToast(`新建展示板失败：${error.message}`, { kind: 'error' }); return null; }
}
async function boardRename(id) {
  const board = BOARD_DATA.find(item => item.id === id) || BOARD_DETAIL;
  if (!board) return;
  const name = await uiPrompt('重命名展示板', board.name);
  if (name === null || !name || name === board.name) return;
  try { await boardPost('/api/board/update', { id, name }); await boardReloadData(); } catch (error) { uiToast(`重命名失败：${error.message}`, { kind: 'error' }); }
}
function boardInlineRename() {
  const title = document.querySelector('[data-board-rename-target]');
  if (!title || !BOARD_DETAIL) return;
  const input = document.createElement('input');
  input.className = 'input bd-rename';
  input.value = BOARD_DETAIL.name;
  title.replaceWith(input);
  input.focus(); input.select();
  let done = false;
  const finish = async save => {
    if (done) return; done = true;
    const name = input.value.trim();
    if (save && name && name !== BOARD_DETAIL.name) {
      try { await boardPost('/api/board/update', { id: BOARD_DETAIL.id, name }); await boardReloadData(); return; }
      catch (error) { uiToast(`重命名失败：${error.message}`, { kind: 'error' }); }
    }
    boardRender();
  };
  input.addEventListener('keydown', event => { if (event.key === 'Enter') finish(true); else if (event.key === 'Escape') finish(false); });
  input.addEventListener('blur', () => finish(true));
}
async function boardEditNote(id) {
  const board = BOARD_DATA.find(item => item.id === id) || BOARD_DETAIL;
  if (!board) return;
  const note = await uiPrompt('展示板备注', board.note || '', { placeholder: '如：9/10 月考前用', hint: '只在系统内显示，不上纸。' });
  if (note === null) return;
  try { await boardPost('/api/board/update', { id, note }); await boardReloadData(); } catch (error) { uiToast(`保存备注失败：${error.message}`, { kind: 'error' }); }
}
async function boardDuplicate(id) {
  const board = BOARD_DATA.find(item => item.id === id) || BOARD_DETAIL;
  if (!board) return;
  const name = await uiPrompt('复制展示板为', `${board.name} 副本`, { hint: '复制题目引用与版面设置；纸面记录不复制（新板对应新纸）。' });
  if (!name) return;
  try { const result = await boardPost('/api/board/duplicate', { id, name }); boardRemember(result.board.id); await boardReloadData(); uiToast(`已复制为《${name}》`); }
  catch (error) { uiToast(`复制失败：${error.message}`, { kind: 'error' }); }
}
async function boardDelete(id) {
  const board = BOARD_DATA.find(item => item.id === id) || BOARD_DETAIL;
  if (!board) return;
  const ok = await uiConfirm(`删除展示板「${board.name}」？`, { hint: '只删除这个板（含它的纸面记录），题目本身不受影响。', okText: '删除', danger: true });
  if (!ok) return;
  try {
    await boardPost('/api/board/delete', { id });
    if (BOARD_CURRENT === id) { BOARD_CURRENT = ''; BOARD_DETAIL = null; }
    await boardReloadData();
    uiToast(`已删除《${board.name}》`);
  } catch (error) { uiToast(`删除展示板失败：${error.message}`, { kind: 'error' }); }
}

// ---------- 加题（六处入口统一走这里） ----------
async function boardAddToBoard(boardId, uids, options = {}) {
  const clean = boardUniqueUids(uids);
  if (!clean.length || !boardId) return null;
  const target = BOARD_DATA.find(board => board.id === boardId);
  const targetLocked = !!(target?.print?.locked || (BOARD_CURRENT === boardId && BOARD_DETAIL?.print?.locked));
  if (targetLocked && !(BOARD_CURRENT === boardId && BOARD_LAYOUT_GRANTED)) {
    const ok = await uiConfirm('目标展示板的版式已锁定，确认加入题目？', {
      hint: '加入后会清空当前纸面记录，打印状态恢复为未打印，需要重新打印全部。',
      okText: '确认加入', cancelText: '取消',
    });
    if (!ok) return null;
    if (BOARD_CURRENT === boardId) BOARD_LAYOUT_GRANTED = true;
  }
  try {
    const result = await boardPost('/api/board/items/add', { id: boardId, uids: clean });
    const board = result.board;
    boardRemember(board.id);
    if (BOARD_CURRENT === board.id) BOARD_DETAIL = board;
    await boardReloadData();
    if (options.goto && typeof switchTab === 'function') switchTab('board');
    const added = Number(result.board.added ?? clean.length);
    // 选择已经前置到浮层里了，所以这里不再需要「换个板」这条临时纠错通道
    const actions = [];
    if (added) actions.push({ label: '撤销', onClick: () => boardPost('/api/board/items/remove', { id: board.id, uids: clean }).then(boardReloadData).then(() => uiToast('已撤销加入')) });
    if (BOARD_CURRENT !== board.id || !document.getElementById('panel-board')?.classList.contains('active')) {
      actions.push({ label: '打开展示板', onClick: () => { if (typeof switchTab === 'function') switchTab('board'); boardLoad(board.id); } });
    }
    const done = options.moveFromName
      ? `已从《${options.moveFromName}》移到《${board.name}》`
      : `已加入《${board.name}》（现共 ${board.items.length} 题）`;
    if (!options.silent) uiToast(added ? done : `这些题已经在《${board.name}》里了`, { actions, kind: added ? 'ok' : 'warn' });
    return board;
  } catch (error) { uiToast(`加入展示板失败：${error.message}`, { kind: 'error' }); return null; }
}

// 「加入展示板」按钮在动作发生前就要说清默认目标。标题是悬停 / 聚焦时现算的：
// 上次用的板随时会变，烘进模板会过期。
function boardHintText() {
  const last = BOARD_DATA.find(board => board.id === boardLastId()) || BOARD_DATA[0];
  return last ? `加入展示板（上次：${last.name}）· Shift 点击直接加入` : '加入展示板（还没有板，会先新建）';
}
if (typeof document !== 'undefined') {
  const stamp = event => {
    const button = event.target?.closest?.('[data-board-hint]');
    if (button) button.title = boardHintText();
  };
  document.addEventListener('pointerover', stamp, true);
  document.addEventListener('focusin', stamp, true);
}

// ---------- 展示板文件夹 ----------
function boardFolderCollapsed() {
  try { return new Set(JSON.parse(localStorage.getItem(BOARD_FOLD_KEY) || '[]')); }
  catch (error) { return new Set(); }
}
function boardFolderToggle(id, force) {
  if (!id) return;
  const set = boardFolderCollapsed();
  const next = force === undefined ? !set.has(id) : force;
  next ? set.add(id) : set.delete(id);
  try { localStorage.setItem(BOARD_FOLD_KEY, JSON.stringify([...set])); } catch (error) {}
  if (BOARD_PICKER) BOARD_PICKER.collapsed = set;
  return set;
}

async function boardFolderCreate(seedBoardId = '') {
  const name = await uiPrompt('新建文件夹', '', { placeholder: '如：高三上·期中', hint: '只用来在左栏和选板浮层里分组，不影响纸面。' });
  if (!name) return null;
  try {
    const result = await boardPost('/api/board/folder/create', { name });
    if (seedBoardId) await boardPost('/api/board/move', { id: seedBoardId, folder_id: result.folder.id });
    await boardReloadData();
    uiToast(`已新建文件夹「${name}」`);
    return result.folder;
  } catch (error) { uiToast(`新建文件夹失败：${error.message}`, { kind: 'error' }); return null; }
}
async function boardFolderRename(id) {
  const folder = BOARD_FOLDERS.find(item => item.id === id);
  if (!folder) return;
  const name = await uiPrompt('重命名文件夹', folder.name);
  if (name === null || !name || name === folder.name) return;
  try { await boardPost('/api/board/folder/update', { id, name }); await boardReloadData(); }
  catch (error) { uiToast(`重命名失败：${error.message}`, { kind: 'error' }); }
}
async function boardFolderReorder(id, step) {
  const folder = BOARD_FOLDERS.find(item => item.id === id);
  if (!folder) return;
  const to = asNumber(folder.order, 0) + step;
  if (to < 0 || to > BOARD_FOLDERS.length - 1) return;
  try { await boardPost('/api/board/folder/update', { id, order: to }); await boardReloadData(); }
  catch (error) { uiToast(`调整顺序失败：${error.message}`, { kind: 'error' }); }
}
async function boardFolderDelete(id) {
  const folder = BOARD_FOLDERS.find(item => item.id === id);
  if (!folder) return;
  const inside = BOARD_DATA.filter(board => board.folder_id === id);
  let keep = true;
  if (inside.length) {
    const res = await uiDialog({
      title: `删除文件夹「${folder.name}」？`,
      hint: `里面有 ${inside.length} 个板。`,
      okText: '删除文件夹', danger: true,
      body: `<div class="bd-folder-del">
        <label><input type="radio" name="bd-fd" id="bd-fd-keep" checked><span>把这些板移到未归档<small>板和纸面记录都保留</small></span></label>
        <label><input type="radio" name="bd-fd" id="bd-fd-drop"><span>连同 ${inside.length} 个板一起删除<small>板的纸面记录一并消失，题目本身不受影响</small></span></label></div>`,
    });
    if (!res.ok) return;
    keep = res.values['bd-fd-drop'] !== true;
  } else if (!await uiConfirm(`删除空文件夹「${folder.name}」？`, { okText: '删除', danger: true })) return;
  try {
    await boardPost('/api/board/folder/delete', { id, keep_boards: keep });
    await boardReloadData();
    uiToast(keep && inside.length ? `已删除文件夹，${inside.length} 个板移到未归档` : `已删除文件夹「${folder.name}」`);
  } catch (error) { uiToast(`删除文件夹失败：${error.message}`, { kind: 'error' }); }
}
async function boardMoveToFolder(boardId, folderId, index) {
  try {
    await boardPost('/api/board/move', { id: boardId, folder_id: folderId ?? '', index });
    await boardReloadData();
  } catch (error) { uiToast(`移动失败：${error.message}`, { kind: 'error' }); }
}

function boardAddUids(uids) { return boardQuickAdd(uids); }
function qbChooseBoardForUids(uids) { return boardChooseAndAdd(uids); }

// 添加题目对话框：复用 filterItems + 标记筛选
function boardAddFilterState(modal) {
  const value = selector => modal.querySelector(selector)?.value || '';
  return {
    text: value('[data-bdadd="search"]').trim().toLowerCase(), subject: value('[data-bdadd="subject"]'), category: value('[data-bdadd="category"]'),
    tag: value('[data-bdadd="tag"]'), knowledgeTag: value('[data-bdadd="ktag"]'),
    labels: [...modal.querySelectorAll('[data-bdadd-label].on')].map(node => node.dataset.bdaddLabel), labelMode: 'any',
    difficultyMin: 0, difficultyMax: 10, masteryMin: null, masteryMax: null,
    dueFilter: value('[data-bdadd="due"]'), suspended: '', sort: value('[data-bdadd="sort"]') || 'mastery-asc',
  };
}
const BOARD_ADD_VIEW_KEY = 'omrs-board-add-view';
function boardAddView(next) {
  if (next != null) { try { localStorage.setItem(BOARD_ADD_VIEW_KEY, next === 'gallery' ? 'gallery' : 'list'); } catch (error) {} }
  try { return localStorage.getItem(BOARD_ADD_VIEW_KEY) === 'gallery' ? 'gallery' : 'list'; } catch (error) { return 'list'; }
}
// 选题弹窗的画廊同样懒水合：只给当前这一批可见卡拉详情
async function boardAddHydrate(modal, items) {
  if (typeof ensureQuestionDetail !== 'function') return;
  await Promise.all((items || []).map(async item => {
    const node = modal.querySelector(`.bdadd-gallery-preview[data-question-preview-uid="${CSS.escape(item.uid)}"]`);
    if (!node || node.innerHTML.trim()) return;
    let detail = null;
    try { detail = await ensureQuestionDetail(item.uid); } catch (error) { return; }
    if (!detail || !node.isConnected) return;
    node.innerHTML = qvHtml(detail, item, BOARD_CARD_OPTS);
    node.classList.toggle('is-clipped', node.scrollHeight - node.clientHeight > 4);
  }));
}
async function boardAddPrompt() {
  if (!BOARD_DETAIL) return;
  const allItems = getItems().filter(item => !item.suspended);
  const options = (values, placeholder) => `<option value="">${escapeHtml(placeholder)}</option>${values.map(v => `<option value="${escapeAttr(v)}">${escapeHtml(v)}</option>`).join('')}`;
  const subjects = [...new Set(allItems.map(item => item.subject).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const categories = [...new Set(allItems.map(item => item.category).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const ktags = [...new Set(allItems.flatMap(item => item.knowledge_tags || []).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const existing = new Set((BOARD_DETAIL.items || []).map(item => item.uid));
  const selected = new Set();
  const modal = document.createElement('div');
  modal.className = 'modal-overlay open';
  modal.innerHTML = `<div class="modal board-add-modal">
    <div class="modal-close" data-bdadd-close>✕</div>
    <h2>添加题目到「${escapeHtml(BOARD_DETAIL.name)}」</h2>
    <div class="hint">筛选后勾选；已在板里的题目会标灰并跳过。</div>
    <div class="board-add-filters">
      <input class="input qb-search" data-bdadd="search" placeholder="搜索 UID / 科目 / 分类 / 知识点 / 标记…" autocomplete="off">
      <select class="input" data-bdadd="subject">${options(subjects, '全部科目')}</select>
      <select class="input" data-bdadd="category">${options(categories, '全部分类')}</select>
      <select class="input" data-bdadd="ktag">${options(ktags, '全部知识点')}</select>
      <select class="input" data-bdadd="tag"><option value="">全部状态</option><option value="待攻克">待攻克</option><option value="已击杀">已击杀</option><option value="易错">易错坑</option></select>
      <select class="input" data-bdadd="due"><option value="">全部到期</option><option value="overdue">逾期</option><option value="today">今日</option><option value="7days">7 天内</option></select>
      <select class="input" data-bdadd="sort"><option value="mastery-asc">熟练度 ↑</option><option value="due-asc">到期 ↑</option><option value="diff-desc">难度 ↓</option><option value="date-desc">最近复习</option></select>
    </div>
    <div class="board-add-labels"><span>标记：</span>${(LABELS || []).filter(label => !label.archived).map(label => `<button type="button" class="label-filter-chip" data-bdadd-label="${escapeAttr(label.name)}">${lblChip(label)}</button>`).join('') || '<span class="hint">暂无标记</span>'}<span class="grow"></span><span class="seg bd-views" data-bdadd-views><button type="button" data-bdadd-view="list">列表</button><button type="button" data-bdadd-view="gallery">画廊</button></span></div>
    <div class="board-add-list" data-bdadd-list></div>
    <div class="board-add-foot"><span class="hint" data-bdadd-count>已选 0 题</span><button class="btn sm ghost" type="button" data-bdadd-all>全选筛选结果</button><span class="grow"></span><button class="btn" type="button" data-bdadd-close>取消</button><button class="btn primary" type="button" data-bdadd-confirm>加入展示板</button></div>
  </div>`;
  document.body.appendChild(modal);
  const list = modal.querySelector('[data-bdadd-list]');
  const count = modal.querySelector('[data-bdadd-count]');
  let visible = [];
  // 视图只是同一份筛选结果的两种画法：勾选集合 selected 是唯一真相，
  // 所以来回切视图不会丢选择，也不用把选中态往 DOM 里存。
  let addView = boardAddView();
  const checkboxHtml = item => `<input type="checkbox" data-bdadd-uid="${escapeAttr(item.uid)}" ${existing.has(item.uid) ? 'disabled checked' : selected.has(item.uid) ? 'checked' : ''}>`;
  const rowHtml = item => `<label class="board-add-item ${existing.has(item.uid) ? 'in' : ''}">
      ${checkboxHtml(item)}
      <span><strong>${escapeHtml(item.uid)}</strong>${existing.has(item.uid) ? ' <span class="bd-badge muted">已在板中</span>' : ''}<small>${escapeHtml(item.subject || '')} · ${escapeHtml(item.category || '')} · 难度 ${escapeHtml(item.difficulty)} · 熟练度 ${(asNumber(item.mastery, 0) * 100).toFixed(0)}%</small></span>
      <span class="board-add-labels-cell">${typeof lblChips === 'function' ? lblChips(item.labels || [], { max: 3 }) : ''}</span></label>`;
  const cardHtml = item => {
    const cached = typeof QUESTION_CACHE !== 'undefined' ? QUESTION_CACHE[item.uid] : null;
    return qvGalleryCard({
      uid: item.uid,
      className: `bdadd-card ${existing.has(item.uid) ? 'in' : ''} ${selected.has(item.uid) ? 'is-selected' : ''}`,
      rowAttr: `data-bdadd-card="${escapeAttr(item.uid)}"`,
      leadHtml: `<label class="gc-pick">${checkboxHtml(item)}</label>`,
      idHtml: typeof qvGalleryIdHtml === 'function' ? qvGalleryIdHtml(item.uid, item.category) : escapeHtml(item.uid),
      flagsHtml: existing.has(item.uid) ? '<span class="gc-flag muted">已在板中</span>' : '',
      previewClass: 'bdadd-gallery-preview',
      previewHtml: cached && typeof qvHtml === 'function' ? qvHtml(cached, item, BOARD_CARD_OPTS) : '',
      footHtml: `<span class="gc-stat muted">${escapeHtml(item.subject || '')}${item.category ? ` · ${escapeHtml(item.category)}` : ''}</span><span class="gc-stat muted">难度 ${escapeHtml(item.difficulty)}</span><span class="gc-stat muted">熟练度 ${(asNumber(item.mastery, 0) * 100).toFixed(0)}%</span>`,
      labelsHtml: typeof lblChips === 'function' ? lblChips(item.labels || [], { max: 3 }) : '',
    });
  };
  const render = () => {
    visible = filterItems(allItems, boardAddFilterState(modal));
    list.classList.toggle('is-gallery', addView === 'gallery');
    modal.querySelectorAll('[data-bdadd-view]').forEach(node => node.classList.toggle('on', node.dataset.bdaddView === addView));
    if (!visible.length) list.innerHTML = '<div class="empty-inline">没有匹配的题目。</div>';
    else if (addView === 'gallery') list.innerHTML = `<div class="gallery-grid">${visible.map(cardHtml).join('')}</div>`;
    else list.innerHTML = visible.map(rowHtml).join('');
    count.textContent = `已选 ${selected.size} 题`;
    if (addView === 'gallery') boardAddHydrate(modal, visible);
  };
  modal.querySelectorAll('[data-bdadd]').forEach(node => node.addEventListener(node.tagName === 'INPUT' ? 'input' : 'change', render));
  modal.addEventListener('change', event => {
    const box = event.target.closest('[data-bdadd-uid]');
    if (!box || box.disabled) return;
    if (box.checked) selected.add(box.dataset.bdaddUid); else selected.delete(box.dataset.bdaddUid);
    box.closest('[data-bdadd-card]')?.classList.toggle('is-selected', box.checked);
    count.textContent = `已选 ${selected.size} 题`;
  });
  modal.addEventListener('click', async event => {
    const label = event.target.closest('[data-bdadd-label]');
    if (label) { label.classList.toggle('on'); render(); return; }
    const viewButton = event.target.closest('[data-bdadd-view]');
    if (viewButton) { addView = boardAddView(viewButton.dataset.bdaddView); render(); return; }
    if (event.target.closest('[data-bdadd-all]')) { visible.forEach(item => { if (!existing.has(item.uid)) selected.add(item.uid); }); render(); return; }
    if (event.target === modal || event.target.closest('[data-bdadd-close]')) { modal.remove(); return; }
    if (!event.target.closest('[data-bdadd-confirm]')) return;
    const uids = [...selected];
    modal.remove();
    if (uids.length) await boardAddToBoard(BOARD_DETAIL.id, uids);
  });
  render();
  modal.querySelector('[data-bdadd="search"]')?.focus();
}

// ---------- 条目操作 ----------
async function boardRemoveItem(uid) {
  if (!BOARD_DETAIL) return;
  const item = boardCurrentItem(uid);
  if (boardLayoutLocked() && !BOARD_LAYOUT_GRANTED && !(await boardAllowLayoutChange())) return;
  if (boardLayoutLocked()) BOARD_LAYOUT_GRANTED = true;
  try {
    const boardId = BOARD_DETAIL.id;
    const result = await boardPost('/api/board/items/remove', { id: boardId, uids: [uid] });
    BOARD_DETAIL = result.board;
    await boardReloadData();
    uiToast(`已移除 ${uid}${item?.printed && !boardLayoutLocked() ? '（纸上仍有这道题，纸面记录保留其占位）' : ''}`, { actions: [{ label: '撤销', onClick: () => boardAddToBoard(boardId, [uid], { silent: true }) }] });
  } catch (error) { uiToast(`移除失败：${error.message}`, { kind: 'error' }); }
}
async function boardPersistItems(items, message = '') {
  if (!BOARD_DETAIL) return;
  if (boardLayoutLocked() && !BOARD_LAYOUT_GRANTED && !(await boardAllowLayoutChange())) return;
  if (boardLayoutLocked()) BOARD_LAYOUT_GRANTED = true;
  if (BOARD_DIRTY?.items) { const rest = { ...BOARD_DIRTY }; delete rest.items; BOARD_DIRTY = Object.keys(rest).length ? rest : null; }
  const result = await boardPost('/api/board/update', { id: BOARD_DETAIL.id, items: boardItemsPayload(items) });
  BOARD_DETAIL = result.board;
  await boardReloadData();
  if (message) uiToast(message);
}
// 行内留白与版面滑块曾各自持有同一个 BOARD_SAVE_TIMER、互相 clearTimeout，
// 「先改留白再拖滑块」会把前一次改动整个丢掉。改成按字段记脏、到点合并成一次 POST；
// 后端 /api/board/update 本就支持同一请求里同时收 items 与 print。
function boardDirtyMerge(current, kind) {
  return kind ? { ...(current || {}), [String(kind)]: true } : (current || null);
}
// 一次 POST 承载全部脏字段：/api/board/update 同一请求里能同时收 items 与 print，
// 后端也保证 items 的 v2 折算用的是本次请求后的全局留白。
function boardSavePayload(detail, dirty) {
  if (!detail || !dirty || !Object.keys(dirty).length) return null;
  const payload = { id: detail.id };
  if (dirty.items) payload.items = boardItemsPayload(detail.items || []);
  if (dirty.print) payload.print = detail.print;
  return payload;
}
function boardMarkDirty(kind) {
  if (!BOARD_DETAIL) return;
  BOARD_DIRTY = boardDirtyMerge(BOARD_DIRTY, kind);
  clearTimeout(BOARD_SAVE_TIMER);
  BOARD_SAVE_TIMER = setTimeout(boardFlushSave, 500);
}
async function boardFlushSave(options = {}) {
  clearTimeout(BOARD_SAVE_TIMER);
  const dirty = BOARD_DIRTY;
  BOARD_DIRTY = null;
  const payload = boardSavePayload(BOARD_DETAIL, dirty);
  if (!payload) return true;
  const hadPaper = boardHasPaper(BOARD_DETAIL);
  try {
    const result = await boardPost('/api/board/update', payload);
    if (BOARD_DETAIL && result.board?.id === BOARD_DETAIL.id) BOARD_DETAIL = result.board;
    BOARD_LAYOUT_GRANTED = false;
    if (hadPaper && !boardHasPaper(BOARD_DETAIL)) boardRender();
    else boardScheduleEstimate();
    return true;
  } catch (error) {
    BOARD_DIRTY = { ...(dirty), ...(BOARD_DIRTY || {}) };   // 失败不丢脏标记，下次改动会再试
    if (!options.silent) uiToast(`保存展示板失败：${error.message}`, { kind: 'error' });
    return false;
  }
}
// 拖切割线松手：一次合并保存；失败就把这道题的留白恢复成拖动前的值，别让纸面和磁盘各说各话
async function boardApplyGapDrag(uid, lines) {
  const item = boardCurrentItem(uid);
  if (!item) return;
  const before = item.gap_lines;
  boardSelect(uid);
  if (!(await boardSetItemGap(uid, clampNumber(lines, 0, 48, 0)))) return;
  if (await boardFlushSave({ silent: true })) return;
  boardSetItemGap(uid, before);
  uiToast('题后留白没能保存，已恢复拖动前的值', { kind: 'error' });
}
function boardSchedulePersist() { boardMarkDirty('items'); }
async function boardSort(choice) {
  if (!BOARD_DETAIL || !choice) return;
  const items = [...(BOARD_DETAIL.items || [])];
  if (choice === 'reverse') items.reverse();
  else if (choice === 'mastery') items.sort((a, b) => asNumber(a.mastery, 0) - asNumber(b.mastery, 0));
  else if (choice === 'due') items.sort((a, b) => String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')));
  else if (choice === 'added') items.sort((a, b) => String(a.added_at || '').localeCompare(String(b.added_at || '')));
  else items.sort((a, b) => `${a.subject || ''}\u0000${a.category || ''}\u0000${a.uid || ''}`.localeCompare(`${b.subject || ''}\u0000${b.category || ''}\u0000${b.uid || ''}`, 'zh-CN'));
  await boardPersistItems(items, '排序已保存');
}
async function boardSyncLabel() {
  if (!BOARD_DETAIL) return;
  const defs = (LABELS || []).filter(label => !label.archived);
  if (!defs.length) { uiToast('还没有标记，先在题目上打一个「考前必看」之类的标记', { kind: 'warn' }); return; }
  const current = BOARD_DETAIL.source_labels?.[0] || '';
  const res = await uiDialog({
    title: '按标记同步', okText: '同步到展示板', hint: '把带有该标记、且还不在板里的题目追加到末尾；之后新打的标记不会自动进板，需要时再同步一次。',
    body: `<div class="board-sync-options">${defs.map((label, index) => `<label><input type="radio" name="bd-sync" id="bd-sync-${index}" value="${escapeAttr(label.name)}" ${(label.name === current || (!current && index === 0)) ? 'checked' : ''}>${lblChip(label, { lg: true })}<small>${label.count || 0} 题</small></label>`).join('')}</div>`,
    focus: '[data-ui-ok]',
  });
  if (!res.ok) return;
  const label = defs.find((item, index) => res.values[`bd-sync-${index}`] === true)?.name;
  if (!label) return;
  const uids = getItems().filter(item => !item.suspended && (item.labels || []).includes(label)).map(item => item.uid);
  try {
    const result = uids.length ? await boardPost('/api/board/items/add', { id: BOARD_DETAIL.id, uids }) : { board: { added: 0 } };
    await boardPost('/api/board/update', { id: BOARD_DETAIL.id, source_labels: [label] });
    await boardReloadData();
    uiToast(result.board.added ? `已同步 ${result.board.added} 道「${label}」题目` : `没有带「${label}」的新题目`);
  } catch (error) { uiToast(`同步标记失败：${error.message}`, { kind: 'error' }); }
}
async function boardCleanMissing(kind) {
  if (!BOARD_DETAIL) return;
  const kept = (BOARD_DETAIL.items || []).filter(item => kind === 'suspended' ? !item.suspended : !item.missing);
  await boardPersistItems(kept, kind === 'suspended' ? '已移出停用题' : '已清理缺失条目');
}
async function boardClear() {
  if (!BOARD_DETAIL) return;
  const ok = await uiConfirm(`清空展示板「${BOARD_DETAIL.name}」？`, { hint: '移除全部题目引用；题目本身与纸面记录不受影响。', okText: '清空', danger: true });
  if (!ok) return;
  await boardPersistItems([], '展示板已清空');
}

// ---------- 版面设置 ----------
async function boardApplyPrintField(field, value) {
  if (!BOARD_DETAIL) return;
  if (field !== 'locked' && boardLayoutLocked() && !BOARD_LAYOUT_GRANTED && !(await boardAllowLayoutChange())) {
    boardPopRefresh();
    return;
  }
  if (field !== 'locked' && boardLayoutLocked()) BOARD_LAYOUT_GRANTED = true;
  const print = { ...(BOARD_DETAIL.print || {}) };
  if (field === 'note_ratio') { print[field] = clampNumber(value, 30, 55, 50) / 100; const node = document.querySelector('[data-board-ratio-value]'); if (node) node.textContent = `${Math.round(print[field] * 100)}%`; }
  else if (field === 'gap_lines') print[field] = clampNumber(value, 0, 24, 2);
  else if (field === 'answers') print[field] = value === 'append' ? 'append' : 'none';
  else if (field === 'show_labels' || field === 'show_meta' || field === 'cut_label' || field === 'locked') print[field] = !!value;
  else if (field === 'cut_line') print[field] = CUT_LINES.includes(value) ? value : 'dash';
  else return;                    // 未知字段不写进 print，避免脏一个后端会忽略的键
  BOARD_DETAIL.print = print;
  // 「不画切割线」时「标第 N 题止」没有意义：直接禁用，不留一个点了没反应的勾
  if (field === 'cut_line') BOARD_POP?.node?.querySelectorAll('[data-board-print="cut_label"]')
    .forEach(node => { node.disabled = print.cut_line === 'none'; });
  boardPushRelayout();        // 画面先动（去抖 120ms、不发请求），保存另走 500ms 脏队列
  boardMarkDirty('print');
}

// ---------- 打印 / 导出 / 纸面记录 ----------
async function boardFetchExport(mode, options = {}) {
  const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ board_id: BOARD_DETAIL.id, format: 'board', mode }), signal: options.signal });
  if (!response.ok) { let message = '导出失败'; try { message = (await response.json()).msg || message; } catch (error) {} throw new Error(message); }
  return response.text();
}
function boardEffectiveMode() { return BOARD_PRINT_MODE === 'new' && boardHasPaper() ? 'new' : 'all'; }
async function boardExportCurrent(openPreview = false) {
  if (!BOARD_DETAIL) { uiToast('请先选择一个展示板', { kind: 'warn' }); return; }
  const mode = boardEffectiveMode();
  if (mode === 'new' && !boardPrintedSummary().new_count) { uiToast('没有新增题目需要打印', { kind: 'warn' }); return; }
  // 必须在 await 之前同步开窗：浏览器只允许在用户手势的同步调用栈里 window.open，
  // 等导出 HTML 回来时手势已过期，弹窗会被拦截（板子越大越容易触发）。
  let preview = null;
  if (openPreview) {
    preview = window.open('', '_blank');
    if (!preview) { uiToast('浏览器拦截了预览窗口，请允许弹出窗口后重试', { kind: 'error' }); return; }
    try {
      preview.document.write('<!doctype html><meta charset="utf-8"><title>正在生成打印预览…</title><p style="font:14px system-ui;padding:24px;color:#444">正在生成打印预览…<br><small style="color:#888">题目多、图片大时需要几秒；排版好后「打印」按钮才会亮起。</small></p>');
      preview.document.close();
    } catch (error) {}
    // 预览窗口会把它测好的版面回传（omrs-board-layout），页数以它为准；先停掉后台估算，别和预览抢主线程
  }
  try {
    const html = await boardFetchExport(mode);
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    if (openPreview) {
      // location.replace 之后窗口对象本身不变，BOARD_WINDOWS.get(event.source) 的
      // 「标记为已打印」postMessage 回传照常工作。
      preview.location.replace(url);
      BOARD_WINDOWS.set(preview, { boardId: BOARD_DETAIL.id, mode, updatedAt: BOARD_DETAIL.updated_at || '' });
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } else {
      const link = document.createElement('a');
      link.href = url;
      link.download = `OMRS-BD-${BOARD_DETAIL.name}${mode === 'new' ? '-新增' : ''}-错题集.html`;
      document.body.appendChild(link); link.click(); link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1200);
      uiToast('已下载；打印后回到这里点「标记为已打印」记录纸面');
    }
  } catch (error) {
    if (preview) { try { preview.close(); } catch (closeError) {} }
    uiToast(`展示板导出失败：${error.message}`, { kind: 'error' });
  }
}
function boardPrintPreview() { return boardExportCurrent(true); }

// 隐藏 iframe 里跑同一份导出模板，拿到浏览器实测的版面（页数 / 每题位置 / 续排 cursor）
function boardMeasureLayout(html, options = {}) {
  const timeout = options.timeout || 30000;
  return new Promise((resolve, reject) => {
    const frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:900px;height:1200px;visibility:hidden;pointer-events:none;border:0';
    let settled = false;
    const finish = (error, layout) => { if (settled) return; settled = true; window.removeEventListener('message', onMessage); clearTimeout(timer); frame.remove(); error ? reject(error) : resolve(layout); };
    const onMessage = event => { if (event.source === frame.contentWindow && event.data?.type === 'omrs-board-layout') finish(null, event.data.layout); };
    const timer = setTimeout(() => finish(new Error('版面测量超时')), timeout);
    // 取消时立刻拆掉 iframe，别让作废的排版继续占用主线程
    if (options.signal) options.signal.addEventListener('abort', () => finish(new Error('已取消')), { once: true });
    window.addEventListener('message', onMessage);
    document.body.appendChild(frame);
    frame.srcdoc = html;
  });
}
// 估算文案（纯函数，便于测试）：layout 为浏览器模板回传的 OMRS_LAYOUT
function boardEstimateText(layout, mode, print) {
  const nums = layout.page_numbers || [];
  const range = nums.length ? (nums.length === 1 ? `第 ${nums[0]} 页` : `第 ${nums[0]}–${nums[nums.length - 1]} 页`) : '—';
  const warn = layout.warnings?.length ? ` · <span class="warn">⚠ ${layout.warnings.length} 处切图告警</span>` : '';
  if (mode === 'new') return `本次补印 <b>${layout.rendered_pages}</b> 页（${range}）${layout.partial_page ? `，第 ${layout.partial_page} 页印在原纸上` : ''} · 打印后整板共 <b>${layout.pages}</b> 页${warn}`;
  return `预计 <b>${layout.pages}</b> 页 · A4 纵向 · 左右 10 / 上下 12mm${warn}`;
}
// ---------- 预览驱动的排版（取代原来独立的页数估算链路） ----------
// 原先页数估算、打印预览窗口、「标记为已打印」各自把同一份 0.95MB 导出 HTML 排一遍版。
// 现在常驻预览 iframe 就是那一遍：页数从它的 layout 读，标记纸面优先复用它测出的版面。
function boardSyncPreview(options = {}) {
  if (typeof boardPreviewSetBoard !== 'function') return;
  if (!BOARD_DETAIL || boardView() !== 'paper') return;
  if (!document.getElementById('panel-board')?.classList.contains('active')) return;
  boardBindPreview();
  const stage = document.getElementById('bd-stage');
  if (stage) boardPreviewMount(stage);
  const mode = boardEffectiveMode();
  const fingerprint = {
    signature: boardContentSignature(),
    printedAt: boardPrintedSummary().at || '',
    force: !!options.force,
  };
  boardPreviewSetBoard(BOARD_DETAIL.id, mode, fingerprint).catch(error => {
    const node = document.querySelector('.bd-pager-sum');
    if (node) node.innerHTML = `<span class="warn">无法生成预览：${escapeHtml(error.message)}</span>`;
  });
}
// 几何类改动：只让 iframe 重排，全程不发请求
function boardPushRelayout() {
  if (typeof boardPreviewRelayout !== 'function' || !BOARD_DETAIL) return;
  boardPreviewRelayout(BOARD_DETAIL.print || {}, boardPreviewGaps());
}
// 兼容旧调用点：内容变了就重新拉导出（去抖 500ms），几何变了走 boardPushRelayout
function boardScheduleEstimate() { boardSyncPreview(); }
// 人工兜底：内容签名不覆盖题目正文，正文在别处改过时预览可能还是旧的。
// 正常路径（题目 Modal 保存、反馈提交）都会走 reloadData() → boardReloadData() 自动失效，
// 这个按钮留给「在应用外改了文件」「第三方链路没触发重载」这类情况。
function boardRegenPreview() {
  if (!BOARD_DETAIL) return;
  if (typeof boardPreviewInvalidate === 'function') boardPreviewInvalidate();
  boardSyncPreview({ force: true });
  uiToast('正在按最新正文重新生成纸面…');
}

async function boardRecordPrinted(boardId, mode, layout) {
  const result = await boardPost('/api/board/printed', { id: boardId, mode, layout });
  if (BOARD_CURRENT === boardId) BOARD_DETAIL = result.board;
  BOARD_PRINT_MODE = 'new';
  await boardReloadData();
  const paper = boardPrintedSummary(result.board);
  uiToast(`已记录纸面：共 ${paper.count} 题 / ${paper.pages} 页，下次加题可只打印新增`);
}
async function boardMarkPrinted() {
  if (!BOARD_DETAIL) return;
  const mode = boardEffectiveMode();
  const paper = boardPrintedSummary();
  if (mode === 'new' && !paper.new_count) { uiToast('没有新增题目需要记录', { kind: 'warn' }); return; }
  const ok = await uiConfirm(mode === 'new' ? `已经把新增的 ${paper.new_count} 题打印出来了？` : '已经把整板打印出来了？', {
    hint: mode === 'new' ? '系统会按当前版面重新测量，把新题追加到纸面记录，并推进续排位置。' : (paper.pages ? '会用这次整板的版面替换现有纸面记录（视为换了一叠新纸）。' : '系统会测量整板版面，记住每道题印在第几页、印到哪里。'),
    okText: '标记为已打印',
  });
  if (!ok) return;
  try {
    // 预览已经按同一份导出排好版了，直接用它的 layout；预览不可用（列表视图 / 报错）才回退隐藏 iframe
    let layout = typeof boardPreviewLayout === 'function' ? boardPreviewLayout() : null;
    const usable = layout && layout.board_id === BOARD_DETAIL.id && layout.mode === mode
      && typeof boardPreviewIsReady === 'function' && boardPreviewIsReady();
    if (!usable) {
      uiToast('正在测量版面…');
      layout = await boardMeasureLayout(await boardFetchExport(mode));
    }
    await boardRecordPrinted(BOARD_DETAIL.id, mode, layout);
  } catch (error) { uiToast(`记录纸面失败：${error.message}`, { kind: 'error' }); }
}
async function boardResetPrinted() {
  if (!BOARD_DETAIL) return;
  const ok = await uiConfirm('重置纸面记录？', { hint: '忘掉「哪些题已经在纸上」；之后只能「打印全部」重新开始。', okText: '重置', danger: true });
  if (!ok) return;
  try { const result = await boardPost('/api/board/printed/reset', { id: BOARD_DETAIL.id }); BOARD_DETAIL = result.board; BOARD_PRINT_MODE = 'all'; await boardReloadData(); uiToast('纸面记录已重置'); }
  catch (error) { uiToast(`重置失败：${error.message}`, { kind: 'error' }); }
}
// 打印预览窗口的回传：排版完成 → 直接当作页数估算；点「已打印，记录纸面」→ 确认后记录
if (typeof window !== 'undefined') window.addEventListener('message', async event => {
  const type = event.data?.type;
  if (type !== 'omrs-board-layout' && type !== 'omrs-board-printed') return;
  const pending = BOARD_WINDOWS.get(event.source);
  // 页数以常驻预览为准；打印预览窗口只保留「已打印，记录纸面」这条回传
  if (type === 'omrs-board-layout') return;
  const boardId = pending?.boardId || event.data.boardId;
  const mode = pending?.mode || event.data.mode || 'all';
  if (!boardId || !event.data.layout) return;
  const ok = await uiConfirm('打印预览窗口说已经打印完成，记录纸面？', { hint: mode === 'new' ? '把这次补印的新题追加到纸面记录。' : '用这次整板版面替换纸面记录。', okText: '记录' });
  if (!ok) return;
  try { await boardRecordPrinted(boardId, mode, event.data.layout); if (pending) BOARD_WINDOWS.delete(event.source); }
  catch (error) { uiToast(`记录纸面失败：${error.message}`, { kind: 'error' }); }
});

// ---------- 拖拽排序 ----------
function boardBindDrag() {
  const content = document.getElementById('bd-content');
  if (!content || content.dataset.bound === '1') return;
  content.dataset.bound = '1';
  let dragFrom = -1;
  content.addEventListener('dragstart', event => {
    const row = event.target.closest('[data-board-row]');
    if (!row) return;
    dragFrom = asNumber(row.dataset.boardIndex, -1);
    row.classList.add('dragging');
    try { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', row.dataset.boardIndex); } catch (error) {}
  });
  content.addEventListener('dragend', () => { dragFrom = -1; content.querySelectorAll('.dragging,.drag-over').forEach(node => node.classList.remove('dragging', 'drag-over')); });
  content.addEventListener('dragover', event => {
    const row = event.target.closest('[data-board-row]');
    if (!row || dragFrom < 0) return;
    event.preventDefault();
    content.querySelectorAll('.drag-over').forEach(node => node.classList.remove('drag-over'));
    row.classList.add('drag-over');
  });
  content.addEventListener('drop', async event => {
    const row = event.target.closest('[data-board-row]');
    if (!row || !BOARD_DETAIL || dragFrom < 0) return;
    event.preventDefault();
    const to = asNumber(row.dataset.boardIndex, -1);
    const from = dragFrom;
    dragFrom = -1;
    if (from === to || from < 0 || to < 0) return;
    await boardPersistItems(boardMoveItems(BOARD_DETAIL.items, from, to), '排序已保存');
  });
}

// 左栏树的拖拽：板拖到文件夹行 = 移动，板拖到板行 = 落在那个位置，文件夹行之间拖 = 文件夹排序。
// 不会拖 / 触屏的兜底是板 ⋯ 菜单里的「移到」。
function boardBindTreeDrag() {
  const list = document.getElementById('bd-list');
  if (!list || list.dataset.treeBound === '1') return;
  list.dataset.treeBound = '1';
  let drag = null;                        // {kind:'board'|'folder', id}
  const clear = () => list.querySelectorAll('.drag-over,.dragging').forEach(node => node.classList.remove('drag-over', 'dragging'));
  list.addEventListener('dragstart', event => {
    const board = event.target.closest?.('[data-board-drag]');
    const folder = event.target.closest?.('[data-board-folder-drag]');
    if (board) drag = { kind: 'board', id: board.dataset.boardDrag };
    else if (folder) drag = { kind: 'folder', id: folder.dataset.boardFolderDrag };
    else return;
    (board || folder).classList.add('dragging');
    try { event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/plain', drag.id); } catch (error) {}
  });
  list.addEventListener('dragend', () => { drag = null; clear(); });
  list.addEventListener('dragover', event => {
    if (!drag) return;
    const target = event.target.closest?.(drag.kind === 'folder' ? '[data-board-folder-drag]' : '[data-board-folder-drop],[data-board-drag]');
    if (!target || target.classList.contains('dragging')) return;
    event.preventDefault();
    list.querySelectorAll('.drag-over').forEach(node => node.classList.remove('drag-over'));
    target.classList.add('drag-over');
  });
  list.addEventListener('drop', async event => {
    if (!drag) return;
    const target = event.target.closest?.(drag.kind === 'folder' ? '[data-board-folder-drag]' : '[data-board-folder-drop],[data-board-drag]');
    const moving = drag;
    drag = null;
    clear();
    if (!target) return;
    event.preventDefault();
    if (moving.kind === 'folder') {
      const to = BOARD_FOLDERS.find(item => item.id === target.dataset.boardFolderDrag);
      if (to && to.id !== moving.id) {
        try { await boardPost('/api/board/folder/update', { id: moving.id, order: asNumber(to.order, 0) }); await boardReloadData(); }
        catch (error) { uiToast(`调整顺序失败：${error.message}`, { kind: 'error' }); }
      }
      return;
    }
    if (target.dataset.boardDrag) {
      const onto = BOARD_DATA.find(board => board.id === target.dataset.boardDrag);
      if (onto && onto.id !== moving.id) await boardMoveToFolder(moving.id, onto.folder_id, asNumber(onto.order, 0));
      return;
    }
    const folderId = target.dataset.boardFolderDrop ?? '';
    const source = BOARD_DATA.find(board => board.id === moving.id);
    if (source && source.folder_id !== folderId) await boardMoveToFolder(moving.id, folderId);
  });
}

// ---------- 预览回调 ----------
// board_preview.js 排在本文件之后加载，模块顶层注册时 boardPreviewOn 还不存在，
// 因此推迟到第一次真正要用预览时再注册。
let BOARD_PREVIEW_BOUND = false;
function boardBindPreview() {
  if (BOARD_PREVIEW_BOUND || typeof boardPreviewOn !== 'function') return;
  BOARD_PREVIEW_BOUND = true;
  boardPreviewOn({
    onLayout: () => boardRenderPager(),
    // 点纸面上的题 = 选中它：列表视图切回去时选中态是一致的
    onSelect: message => { if (message?.uid) boardSelect(message.uid); },
    onGap: message => boardApplyGapDrag(message.uid, message.lines),
  });
}

// ---------- 事件委托 ----------
if (typeof document !== 'undefined') {
  // 离开展示板页之前先落盘：捕获阶段跑在 switchTab 之前，避免 500ms 去抖窗口里切走丢改动。
  document.addEventListener('click', event => {
    const tab = event.target.closest?.('.tab');
    if (tab && tab.dataset.tab !== 'board' && BOARD_DIRTY) boardFlushSave();
  }, true);
  // 关页/刷新：fetch 会被中断，用 sendBeacon 把同一份 payload 交给浏览器后台发送。
  if (typeof window !== 'undefined') window.addEventListener('beforeunload', () => {
    if (!BOARD_DIRTY || !BOARD_DETAIL) return;
    const dirty = BOARD_DIRTY;
    BOARD_DIRTY = null;
    clearTimeout(BOARD_SAVE_TIMER);
    const payload = boardSavePayload(BOARD_DETAIL, dirty);
    if (!payload) return;
    try {
      const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
      if (!navigator.sendBeacon?.('/api/board/update', blob)) boardPost('/api/board/update', payload);
    } catch (error) { try { boardPost('/api/board/update', payload); } catch (inner) {} }
  });
  document.addEventListener('click', event => {
    const menuToggle = event.target.closest?.('[data-board-menu-toggle]');
    if (menuToggle) {
      event.stopPropagation();
      const id = menuToggle.dataset.boardMenuToggle;
      document.querySelectorAll('[data-board-menu]').forEach(node => node.classList.toggle('open', node.dataset.boardMenu === id && !node.classList.contains('open')));
      return;
    }
    const fold = event.target.closest?.('[data-board-fold]');
    if (fold) { event.stopPropagation(); boardFolderToggle(fold.dataset.boardFold); boardRender(); return; }
    const sortToggle = event.target.closest?.('[data-board-sort-toggle]');
    if (sortToggle) { event.stopPropagation(); sortToggle.parentElement?.querySelector('[data-board-sort-menu]')?.classList.toggle('open'); return; }
    const sort = event.target.closest?.('[data-board-sort]');
    if (sort) { event.stopPropagation(); document.querySelectorAll('[data-board-sort-menu].open').forEach(node => node.classList.remove('open')); boardSort(sort.dataset.boardSort); return; }
    if (!event.target.closest?.('[data-board-menu]')) document.querySelectorAll('[data-board-menu].open').forEach(node => node.classList.remove('open'));
    if (!event.target.closest?.('[data-board-sort-menu]')) document.querySelectorAll('[data-board-sort-menu].open').forEach(node => node.classList.remove('open'));
    const popClose = event.target.closest?.('[data-board-pop-close]');
    if (popClose) { event.stopPropagation(); boardPopClose(); return; }
    const popToggle = event.target.closest?.('[data-board-pop]');
    if (popToggle) { event.stopPropagation(); boardPopOpen(popToggle.dataset.boardPop, popToggle); return; }
    const action = event.target.closest?.('[data-board-action]');
    if (action) {
      event.stopPropagation();
      const type = action.dataset.boardAction;
      const id = action.dataset.boardId || BOARD_CURRENT;
      const folderId = action.dataset.boardFolderId || '';
      if (type === 'create') boardCreate();
      else if (type === 'folder-create') boardFolderCreate();
      else if (type === 'folder-rename') boardFolderRename(folderId);
      else if (type === 'folder-new-board') boardCreate(null, folderId);
      else if (type === 'folder-up') boardFolderReorder(folderId, -1);
      else if (type === 'folder-down') boardFolderReorder(folderId, 1);
      else if (type === 'folder-delete') boardFolderDelete(folderId);
      else if (type === 'move-to') boardMoveToFolder(action.dataset.boardId, action.dataset.boardFolder || '');
      else if (type === 'move-new') boardFolderCreate(action.dataset.boardId);
      else if (type === 'rename') boardRename(id);
      else if (type === 'note') boardEditNote(id);
      else if (type === 'duplicate') boardDuplicate(id);
      else if (type === 'delete') boardDelete(id);
      else if (type === 'export-board') boardLoad(id, true).then(() => boardExportCurrent(false));
      else if (type === 'add') boardAddPrompt();
      else if (type === 'remove-item') boardRemoveItem(action.dataset.boardUid);
      else if (type === 'preview-item') viewQ(action.dataset.boardUid, (BOARD_DETAIL?.items || []).filter(item => !item.missing).map(item => item.uid));
      else if (type === 'sync-label') boardSyncLabel();
      else if (type === 'clean-missing') boardCleanMissing('missing');
      else if (type === 'clean-suspended') boardCleanMissing('suspended');
      else if (type === 'clear') boardClear();
      else if (type === 'preview') boardPrintPreview();
      else if (type === 'export') boardExportCurrent(false);
      else if (type === 'mark-printed') boardMarkPrinted();
      else if (type === 'reset-printed') boardResetPrinted();
      else if (type === 'inspect-clear') boardSelect('');
      else if (type === 'inspect-locate') boardPreviewGoto(BOARD_SELECTED_UID);
      else if (type === 'inspect-open') { const item = boardCurrentItem(BOARD_SELECTED_UID); if (item && !item.missing) viewQ(item.uid, (BOARD_DETAIL?.items || []).filter(x => !x.missing).map(x => x.uid)); }
      else if (type === 'inspect-inherit') boardSetItemGap(BOARD_SELECTED_UID, null);
      else if (type === 'inspect-regen') boardRegenPreview();
      else if (type === 'gallery-locate') { const uid = action.dataset.boardUid; boardSelect(uid); boardSetView('paper'); setTimeout(() => boardPreviewGoto(uid), 60); }
      return;
    }
    const modeButton = event.target.closest?.('[data-board-mode]');
    if (modeButton && BOARD_DETAIL && !modeButton.disabled) {
      BOARD_PRINT_MODE = modeButton.dataset.boardMode === 'new' ? 'new' : 'all';
      boardPopRefresh();                                        // 模式说明与按钮文案随之变化
      boardScheduleEstimate();
      return;
    }
    const viewButton = event.target.closest?.('[data-board-views] button');
    if (viewButton && !viewButton.disabled) { boardSetView(viewButton.dataset.boardView); return; }
    const pageButton = event.target.closest?.('[data-board-page]');
    if (pageButton && !pageButton.disabled) {
      const action = pageButton.dataset.boardPage;
      if (action === 'prev') boardPreviewStep(-1);
      else if (action === 'next') boardPreviewStep(1);
      else if (action === 'new') { const first = (BOARD_DETAIL?.items || []).find(item => !item.missing && !item.suspended && !item.printed); if (first) boardPreviewGoto(first.uid); }
      return;
    }
    const zoom = event.target.closest?.('[data-board-zoom]');
    if (zoom) {
      zoom.closest('[data-board-zoom]')?.parentNode?.querySelectorAll('button').forEach(node => node.classList.toggle('on', node === zoom));
      boardPreviewScale(zoom.dataset.boardZoom === 'fit' ? 'fit' : 1);
      return;
    }
    const seg = event.target.closest?.('[data-board-seg] button');
    if (seg && BOARD_DETAIL) {
      const group = seg.closest('[data-board-seg]');
      group.querySelectorAll('button').forEach(node => node.classList.toggle('on', node === seg));
      boardApplyPrintField(group.dataset.boardSeg, seg.dataset.value);
      return;
    }
    const select = event.target.closest?.('[data-board-select]');
    if (select && !event.target.closest('[data-board-menu],[data-board-menu-toggle]')) { boardLoad(select.dataset.boardSelect); return; }
    const row = event.target.closest?.('[data-board-row]');
    if (row && !event.target.closest('input,button,label,[data-lbl-target]')) boardSelect(row.dataset.boardRow);
  });
  document.addEventListener('dblclick', event => {
    if (event.target.closest?.('[data-board-rename-target]')) boardInlineRename();
    const row = event.target.closest?.('[data-board-row]');
    if (row && !event.target.closest('input,button,label,[data-lbl-target]')) { const item = boardCurrentItem(row.dataset.boardRow); if (item && !item.missing) viewQ(item.uid, (BOARD_DETAIL?.items || []).filter(i => !i.missing).map(i => i.uid)); }
  });
  document.addEventListener('input', event => {
    const gap = event.target.closest?.('[data-board-gap]');
    if (gap && BOARD_DETAIL) {
      if (boardLayoutLocked()) return;
      const raw = String(gap.value ?? '').trim();
      void boardSetItemGap(gap.dataset.boardGap, raw === '' ? null : clampNumber(raw, 0, 48, 0), { keepFocus: true });
      return;
    }
    const inspectGap = event.target.closest?.('[data-board-inspect-gap]');
    if (inspectGap && BOARD_DETAIL) {
      if (boardLayoutLocked()) return;
      const raw = String(inspectGap.value ?? '').trim();
      void boardSetItemGap(inspectGap.dataset.boardInspectGap, raw === '' ? null : clampNumber(raw, 0, 48, 0), { keepFocus: true });
      return;
    }
    const jump = event.target.closest?.('[data-board-page-input]');
    if (jump) { boardPreviewGoto(Number(jump.value) || 1); return; }
    const print = event.target.closest?.('[data-board-print]');
    if (print && BOARD_DETAIL) {
      if (boardLayoutLocked() && (print.type === 'range' || print.type === 'number')) return;
      void boardApplyPrintField(print.dataset.boardPrint, print.type === 'checkbox' ? print.checked : print.value);
    }
  });
  document.addEventListener('change', event => {
    const gap = event.target.closest?.('[data-board-gap],[data-board-inspect-gap]');
    if (gap && BOARD_DETAIL && boardLayoutLocked()) {
      const uid = gap.dataset.boardGap || gap.dataset.boardInspectGap;
      const raw = String(gap.value ?? '').trim();
      void boardSetItemGap(uid, raw === '' ? null : clampNumber(raw, 0, 48, 0), { keepFocus: true });
      return;
    }
    const print = event.target.closest?.('[data-board-print]');
    if (print && BOARD_DETAIL && (print.tagName === 'SELECT' || print.type === 'checkbox' || print.type === 'range' || print.type === 'number')) {
      void boardApplyPrintField(print.dataset.boardPrint, print.type === 'checkbox' ? print.checked : print.value);
    }
  });
  document.addEventListener('keydown', event => {
    if (!document.getElementById('panel-board')?.classList.contains('active')) return;
    if (document.querySelector('.modal-overlay.open') || (typeof LABEL_PICKER !== 'undefined' && LABEL_PICKER)) return;
    if (event.target.closest?.('input,textarea,select,[contenteditable]')) return;
    if (event.altKey) return;
    const key = String(event.key || '').toLowerCase();
    const withMod = event.ctrlKey || event.metaKey;
    if (withMod) {
      if ((key === 'arrowup' || key === 'arrowdown') && BOARD_DETAIL) {
        const index = boardSelectedIndex();
        const to = index + (key === 'arrowup' ? -1 : 1);
        if (index >= 0 && to >= 0 && to < BOARD_DETAIL.items.length) { event.preventDefault(); boardPersistItems(boardMoveItems(BOARD_DETAIL.items, index, to), '排序已保存'); }
      }
      return;
    }
    if ((key === 'arrowleft' || key === 'arrowright') && boardView() === 'paper') { event.preventDefault(); boardPreviewStep(key === 'arrowleft' ? -1 : 1); return; }
    if (key === 'n') { event.preventDefault(); boardCreate(); }
    else if (key === 'a' && BOARD_DETAIL) { event.preventDefault(); boardAddPrompt(); }
    else if (key === 'p' && BOARD_DETAIL) { event.preventDefault(); boardPrintPreview(); }
    else if ((key === 'arrowup' || key === 'arrowdown') && BOARD_DETAIL?.items?.length) {
      event.preventDefault();
      const index = boardSelectedIndex();
      const next = index < 0 ? 0 : Math.max(0, Math.min(BOARD_DETAIL.items.length - 1, index + (key === 'arrowup' ? -1 : 1)));
      boardSelect(BOARD_DETAIL.items[next].uid);
      if (boardView() === 'paper') boardPreviewGoto(BOARD_SELECTED_UID);
      document.querySelector(`[data-board-row="${CSS.escape(BOARD_SELECTED_UID)}"]`)?.scrollIntoView?.({ block: 'nearest' });
    } else if (key === 'enter' && BOARD_DETAIL) {
      const current = BOARD_DETAIL.items?.[boardSelectedIndex()];
      if (current && !current.missing) viewQ(current.uid, BOARD_DETAIL.items.filter(item => !item.missing).map(item => item.uid));
    } else if ((key === 'delete' || key === 'backspace') && BOARD_DETAIL) {
      const current = BOARD_DETAIL.items?.[boardSelectedIndex()];
      if (current) { event.preventDefault(); boardRemoveItem(current.uid); }
    }
  });
}

if (typeof module !== 'undefined') module.exports = {
  boardMoveItems, boardItemsPayload, boardUniqueUids, boardEstimateText, boardColumnWidth, boardEffectiveGap,
  boardDirtyMerge, boardSavePayload, boardPagerHtml, boardGapCm,
};
