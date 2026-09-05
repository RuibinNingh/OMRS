// === assets/board.js — 展示板：板 CRUD、条目增删排序、版面设置、打印（全部 / 仅新增）与纸面记录 ===
// 依赖 core.js（api / uiToast / uiPrompt / uiConfirm / filterItems）、labels.js（lblChips / LABELS）、
// questions.js（viewQ / QUESTION_CACHE）；必须排在 export.js 之后。
// 打印链路：/api/export {format:'board', mode} → 自包含 HTML（board.js 模板在浏览器里分页）
//   → 打印；「标记为已打印」时把同一份 HTML 放进隐藏 iframe 测量版面 → POST /api/board/printed 记录纸面。
let BOARD_DATA = [];
let BOARD_CURRENT = '';
let BOARD_DETAIL = null;
let BOARD_SAVE_TIMER = null;
let BOARD_SELECTED_UID = '';
let BOARD_PRINT_MODE = 'all';                 // 'all' | 'new'
let BOARD_EST_TIMER = null;
let BOARD_EST_TOKEN = 0;
const BOARD_LAST_KEY = 'omrs-board-last';
const BOARD_WINDOWS = new Map();              // 打印预览窗口 -> {boardId, mode}

// ---------- 小工具 ----------
function boardAvailableBoards() { return Array.isArray(BOARD_DATA) ? BOARD_DATA : []; }
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
function boardItemsPayload(items) {
  return (items || []).map(item => ({
    question_id: item.question_id || '', uid: item.uid || '', added_at: item.added_at || '',
    extra_gap_lines: clampNumber(item.extra_gap_lines, 0, 24, 0), pin: !!item.pin,
  }));
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
async function boardReloadData() {
  if (!document.getElementById('bd-list')) return;
  try {
    const result = await api('/api/boards');
    BOARD_DATA = result.boards || [];
    const preferred = BOARD_CURRENT || boardLastId();
    const selected = BOARD_DATA.find(board => board.id === preferred) || BOARD_DATA[0];
    if (selected) {
      boardRemember(selected.id);
      await boardLoad(selected.id, false);
    } else {
      BOARD_DETAIL = null;
      BOARD_CURRENT = '';
    }
  } catch (error) {
    BOARD_DATA = [];
    BOARD_DETAIL = null;
  }
  boardRender();
}
async function boardLoad(id, render = true) {
  if (!id) return;
  try {
    const result = await api(`/api/board?id=${encodeURIComponent(id)}`);
    BOARD_DETAIL = result.board || null;
    if (!BOARD_DETAIL?.items?.some(item => item.uid === BOARD_SELECTED_UID)) BOARD_SELECTED_UID = '';
    boardRemember(id);
    if (BOARD_PRINT_MODE === 'new' && !boardHasPaper()) BOARD_PRINT_MODE = 'all';
    if (render) boardRender();
  } catch (error) {
    uiToast(`读取展示板失败：${error.message}`, { kind: 'error' });
  }
}

// ---------- 渲染：板列表 ----------
function boardListHtml() {
  if (!BOARD_DATA.length) {
    return `<div class="bd-empty"><div class="bd-empty-icon">▤</div><strong>还没有展示板</strong>
      <p>把考前必看的题目集中到一个板里，随时加题、重排，打印成左题右空的活页纸；之后新增的题还能只补印一页。</p>
      <button class="btn sm primary" type="button" data-board-action="create">新建第一个展示板</button></div>`;
  }
  return `<div class="bd-list-head"><div class="card-title">展示板<small>${BOARD_DATA.length}</small></div><button class="btn sm primary" type="button" data-board-action="create" title="新建板（N）">＋ 新建</button></div>
    <div class="bd-board-items">${BOARD_DATA.map(board => {
      const paper = board.printed_summary || {};
      const bits = [`${board.count} 题`];
      if (paper.pages) bits.push(`<span class="pt">已印 ${paper.pages} 页</span>${paper.new_count ? ` · 新增 ${paper.new_count}` : ''}`);
      if (board.missing) bits.push(`缺失 ${board.missing}`);
      if (board.suspended) bits.push(`停用 ${board.suspended}`);
      bits.push(boardFormatTime(board.updated_at));
      return `<div class="bd-board-item ${board.id === BOARD_CURRENT ? 'on' : ''}" data-board-select="${escapeAttr(board.id)}" title="${escapeAttr(board.note || board.name)}">
        <div class="bd-board-name">${escapeHtml(board.name)}</div>
        <div class="bd-board-actions"><button type="button" class="btn sm ghost" data-board-menu-toggle="${escapeAttr(board.id)}" aria-label="展示板操作">⋯</button>
          <div class="bd-board-menu" data-board-menu="${escapeAttr(board.id)}">
            <button type="button" data-board-action="rename" data-board-id="${escapeAttr(board.id)}">重命名</button>
            <button type="button" data-board-action="note" data-board-id="${escapeAttr(board.id)}">备注…</button>
            <button type="button" data-board-action="duplicate" data-board-id="${escapeAttr(board.id)}">复制</button>
            <button type="button" data-board-action="export-board" data-board-id="${escapeAttr(board.id)}">导出 HTML</button>
            <button type="button" class="danger" data-board-action="delete" data-board-id="${escapeAttr(board.id)}">删除</button>
          </div></div>
        <div class="bd-board-meta">${bits.join(' · ')}</div>
      </div>`;
    }).join('')}</div>
    <div class="hint bd-list-note">板里存的是题目引用：题目改了，重印即最新。纸面标题固定为「错题集」，板名只在系统内使用。</div>`;
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
  const meta = item.missing
    ? '题目已删除或无法解析；导出时跳过，可清理'
    : `${escapeHtml(item.subject || '')} · ${escapeHtml(item.category || '')} · 难度 ${escapeHtml(item.difficulty ?? '')} · 熟练度 ${typeof masteryBarHtml === 'function' ? masteryBarHtml(item, 52) : `${(asNumber(item.mastery, 0) * 100).toFixed(0)}%`}${due ? ` · ${due}` : ''}`;
  return `<div class="bd-row ${item.missing ? 'missing' : ''} ${item.suspended ? 'suspended' : ''} ${BOARD_SELECTED_UID === item.uid ? 'is-selected' : ''}" draggable="true" tabindex="0" data-board-row="${escapeAttr(item.uid)}" data-board-index="${index}">
    <span class="bd-grip" title="拖拽排序（Ctrl+↑/↓ 也可）">⠿</span><span class="bd-no">${index + 1}</span>
    <div class="bd-main"><div class="bd-row-head"><strong>${escapeHtml(item.uid || item.question_id || '未知题目')}</strong>${badges.join('')}<span class="bd-row-labels" data-lbl-target="${escapeAttr(item.uid)}">${labels}</span></div>
      <div class="bd-row-meta">${meta}</div></div>
    <div class="bd-acts"><label class="bd-gap" title="这道题右侧额外多留几行空白（每行 18px）">留白 +<input type="number" class="input" min="0" max="24" value="${clampNumber(item.extra_gap_lines, 0, 24, 0)}" data-board-gap="${escapeAttr(item.uid)}">行</label>
      <button type="button" class="btn sm ghost" data-board-action="preview-item" data-board-uid="${escapeAttr(item.uid)}" ${item.missing ? 'disabled' : ''}>预览</button>
      <button type="button" class="btn sm ghost" data-board-action="remove-item" data-board-uid="${escapeAttr(item.uid)}" title="从板中移除（Delete）">✕</button></div>
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
  return `<div class="bd-toolbar"><div class="bd-title-wrap"><div class="bd-title" data-board-rename-target title="双击重命名">${escapeHtml(BOARD_DETAIL.name)}</div><div class="bd-sub">${items.length} 题${subText ? ` · ${subText}` : ''}${paperText}${BOARD_DETAIL.note ? ` · ${escapeHtml(BOARD_DETAIL.note)}` : ''}</div></div>
    <button class="btn sm primary" type="button" data-board-action="add" title="添加题目（A）">＋ 添加题目</button><button class="btn sm" type="button" data-board-action="sync-label">按标记同步</button>
    <span class="bd-sort-wrap"><button class="btn sm" type="button" data-board-sort-toggle>排序 ▾</button><div class="bd-sort-menu" data-board-sort-menu><button type="button" data-board-sort="subject">按科目 / 分类</button><button type="button" data-board-sort="mastery">按熟练度 ↑</button><button type="button" data-board-sort="due">按到期</button><button type="button" data-board-sort="added">按加入时间</button><button type="button" data-board-sort="reverse">反转顺序</button></div></span>
    <button class="btn sm ghost" type="button" data-board-action="clear" ${items.length ? '' : 'disabled'}>清空</button></div>
    ${hasPaper ? '<div class="hint" style="margin:-4px 0 8px">已打印的题目在纸上的位置已固定；这里重排只影响下次「打印全部」的顺序，「仅打印新增」按纸面顺序接着排。</div>' : ''}
    <div class="bd-rows" data-board-rows>${items.length ? items.map((item, index) => boardRowHtml(item, index, hasPaper)).join('') : '<div class="bd-empty"><div class="bd-empty-icon">＋</div><strong>板里还没有题目</strong>点「添加题目」筛选加入，或在题库勾选后批量加入；题目 Modal、反馈页判错后也有「加入展示板」。</div>'}</div>
    ${warns.join('')}`;
}

// ---------- 渲染：版面与打印 ----------
function boardSettingsHtml() {
  if (!BOARD_DETAIL) return '<div class="empty-inline">选择展示板后设置版面与打印。</div>';
  const print = BOARD_DETAIL.print || {};
  const paper = boardPrintedSummary();
  const hasPaper = paper.pages > 0;
  const ratio = Math.round(asNumber(print.note_ratio, .42) * 100);
  const mode = BOARD_PRINT_MODE === 'new' && hasPaper ? 'new' : 'all';
  const binding = clampNumber(print.binding_mm, 10, 40, 22);
  const geomLocked = hasPaper ? '<span class="hint" title="纸面几何以已打印的纸为准">（仅新增时沿用纸面几何）</span>' : '';
  return `<div class="bd-section-title">版面 ${geomLocked}</div>
    <div class="bd-field"><label>右侧留白占比 <b data-board-ratio-value>${ratio}%</b></label><input type="range" min="30" max="55" step="2" value="${ratio}" data-board-print="note_ratio" title="右侧空白区占内容区宽度的比例"><div class="hint">题栏约 ${Math.round((793.7 - binding * 3.7795 - 37.8 - 24) * (1 - ratio / 100))}px；题面长的科目调小，纯公式题调大</div></div>
    <div class="bd-field-row">
      <div class="bd-field"><label>题间留白（行）</label><input class="input" type="number" min="0" max="24" value="${clampNumber(print.gap_lines, 0, 24, 6)}" data-board-print="gap_lines" title="每题之后空几行（每行 18px），单题可在行内再加"></div>
      <div class="bd-field"><label>装订边</label><select class="input" data-board-print="binding_mm">${[18, 20, 22, 25, 30].map(v => `<option value="${v}" ${binding === v ? 'selected' : ''}>${v} mm</option>`).join('')}${[18, 20, 22, 25, 30].includes(binding) ? '' : `<option value="${binding}" selected>${binding} mm</option>`}</select></div>
    </div>
    <div class="bd-field"><label>题间留白行数</label><input type="number" class="input" min="0" max="24" step="1" value="${print.gap_lines || 0}" data-board-field="gap_lines" style="max-width:100px"></div>
    <div class="bd-field"><label>答案</label><div class="seg" data-board-seg="answers"><button type="button" class="${print.answers === 'append' ? '' : 'on'}" data-value="none">不含</button><button type="button" class="${print.answers === 'append' ? 'on' : ''}" data-value="append">末页附答案</button></div></div>
    <div class="bd-field"><label>题头显示</label><div class="bd-checks"><label><input type="checkbox" data-board-print="show_labels" ${print.show_labels !== false ? 'checked' : ''}> 标记</label><label><input type="checkbox" data-board-print="show_meta" ${print.show_meta !== false ? 'checked' : ''}> 科目 · 分类 · 难度</label></div></div>
    <div class="bd-est" data-board-est>预计页数计算中…</div>
    <div class="bd-print">
      <div class="bd-section-title">打印</div>
      <div class="bd-modes">
        <label class="${mode === 'all' ? 'on' : ''}"><input type="radio" name="bd-print-mode" value="all" ${mode === 'all' ? 'checked' : ''}><span>打印全部<small>整板重新排版，用新纸从第 1 页打起${hasPaper ? '；确认后会替换现有纸面记录' : ''}</small></span></label>
        <label class="${mode === 'new' ? 'on' : ''} ${hasPaper ? '' : 'disabled'}"><input type="radio" name="bd-print-mode" value="new" ${mode === 'new' ? 'checked' : ''} ${hasPaper ? '' : 'disabled'}><span>仅打印新增${hasPaper ? `（${paper.new_count} 题）` : ''}<small>${hasPaper ? `新题接在第 ${paper.cursor?.page || paper.pages} 页的空白处继续排；把那张原纸放回打印机，已打印区域留白` : '先「打印全部」并标记为已打印，之后才能只补印新题'}</small></span></label>
      </div>
      <div class="bd-settings-actions"><button class="btn primary" type="button" data-board-action="preview" title="打印预览（P）">🖨 打印预览</button><button class="btn" type="button" data-board-action="export">下载 HTML</button></div>
      <div class="bd-paper" style="margin-top:12px">${hasPaper
        ? `<div>纸面记录：已印 <b>${paper.count}</b> 题 · <b>${paper.pages}</b> 页${paper.answer_pages?.length ? `（含答案页 ${paper.answer_pages.join('、')}）` : ''} · ${boardFormatTime(paper.at)}</div><div>续排位置：第 <b>${paper.cursor?.page || paper.pages}</b> 页，留白 ${Math.round(asNumber(paper.print?.note_ratio, .42) * 100)}% / 装订 ${asNumber(paper.print?.binding_mm, 22)}mm${paper.changed_count ? ` · <span class="warn">${paper.changed_count} 题已改动</span>` : ''}</div>`
        : '<div>还没有纸面记录。打印后点「标记为已打印」，系统会记住每道题印在第几页、印到哪里，之后加题只需补印新的那一页。</div>'}
        <div class="bd-paper-acts"><button class="btn sm" type="button" data-board-action="mark-printed">✓ 标记为已打印</button>${hasPaper ? '<button class="btn sm ghost" type="button" data-board-action="reset-printed">重置纸面记录</button>' : ''}</div>
      </div>
    </div>`;
}
function boardRender() {
  const list = document.getElementById('bd-list');
  const content = document.getElementById('bd-content');
  const settings = document.getElementById('bd-settings');
  if (list) list.innerHTML = boardListHtml();
  if (content) content.innerHTML = boardContentHtml();
  if (settings) settings.innerHTML = boardSettingsHtml();
  boardBindDrag();
  boardScheduleEstimate();
}

// ---------- 板 CRUD ----------
async function boardCreate(initialUids = null) {
  const name = await uiPrompt('新建展示板', '', { placeholder: '如：考前速览·三角函数', hint: '板名只在系统内使用，纸面标题固定为「错题集」。' });
  if (!name) return null;
  try {
    const result = await boardPost('/api/board/create', { name, uids: initialUids || [] });
    boardRemember(result.board.id);
    BOARD_DETAIL = result.board;
    await boardReloadData();
    if (typeof switchTab === 'function' && document.getElementById('panel-board')?.classList.contains('active')) boardRender();
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
  try {
    const result = await boardPost('/api/board/items/add', { id: boardId, uids: clean });
    const board = result.board;
    boardRemember(board.id);
    if (BOARD_CURRENT === board.id) BOARD_DETAIL = board;
    await boardReloadData();
    if (options.goto && typeof switchTab === 'function') switchTab('board');
    const added = Number(result.board.added ?? clean.length);
    const actions = [];
    if (added) actions.push({ label: '撤销', onClick: () => boardPost('/api/board/items/remove', { id: board.id, uids: clean }).then(boardReloadData).then(() => uiToast('已撤销加入')) });
    if (BOARD_DATA.length > 1) actions.push({ label: '换个板…', onClick: () => boardChooseAndAdd(clean, { exclude: board.id, moveFrom: board.id }) });
    if (!options.silent) uiToast(added ? `已加入《${board.name}》（现共 ${board.items.length} 题）` : `这些题已经在《${board.name}》里了`, { actions, kind: added ? 'ok' : 'warn' });
    return board;
  } catch (error) { uiToast(`加入展示板失败：${error.message}`, { kind: 'error' }); return null; }
}
// 一键加入最近使用的板；没有板时先建一个
async function boardQuickAdd(uid) {
  const uids = boardUniqueUids(Array.isArray(uid) ? uid : [uid]);
  if (!uids.length) return;
  if (!BOARD_DATA.length) { try { BOARD_DATA = (await api('/api/boards')).boards || []; } catch (error) {} }
  let id = boardLastId();
  if (!BOARD_DATA.some(board => board.id === id)) id = BOARD_DATA[0]?.id || '';
  if (!id) { await boardCreate(uids); return; }
  await boardAddToBoard(id, uids);
}
// 选板对话框（题库批量条 / toast「换个板」）
async function boardChooseAndAdd(uids, options = {}) {
  const clean = boardUniqueUids(uids);
  if (!clean.length) return;
  if (!BOARD_DATA.length) { try { BOARD_DATA = (await api('/api/boards')).boards || []; } catch (error) {} }
  const candidates = BOARD_DATA.filter(board => board.id !== options.exclude);
  if (!candidates.length) { await boardCreate(clean); return; }
  const last = boardLastId();
  const res = await uiDialog({
    title: `把 ${clean.length} 道题加入展示板`, okText: '加入',
    body: `<div class="qb-board-options">${candidates.map((board, index) => `<label><input type="radio" name="bd-choose" id="bd-choose-${index}" value="${escapeAttr(board.id)}" ${(board.id === last || (index === 0 && !candidates.some(b => b.id === last))) ? 'checked' : ''}><span>${escapeHtml(board.name)}<small>${board.count} 题${board.printed_summary?.pages ? ` · 已印 ${board.printed_summary.pages} 页` : ''}</small></span></label>`).join('')}<label><input type="radio" name="bd-choose" id="bd-choose-new" value="__new__"><span>＋ 新建一个板…</span></label></div>`,
    focus: '[data-ui-ok]',
  });
  if (!res.ok) return;
  const picked = candidates.find((board, index) => res.values[`bd-choose-${index}`] === true)?.id || (res.values['bd-choose-new'] === true ? '__new__' : '');
  if (!picked) return;
  if (options.moveFrom) { try { await boardPost('/api/board/items/remove', { id: options.moveFrom, uids: clean }); } catch (error) {} }
  if (picked === '__new__') { await boardCreate(clean); return; }
  await boardAddToBoard(picked, clean);
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
    <div class="board-add-labels"><span>标记：</span>${(LABELS || []).filter(label => !label.archived).map(label => `<button type="button" class="label-filter-chip" data-bdadd-label="${escapeAttr(label.name)}">${lblChip(label)}</button>`).join('') || '<span class="hint">暂无标记</span>'}</div>
    <div class="board-add-list" data-bdadd-list></div>
    <div class="board-add-foot"><span class="hint" data-bdadd-count>已选 0 题</span><button class="btn sm ghost" type="button" data-bdadd-all>全选筛选结果</button><span class="grow"></span><button class="btn" type="button" data-bdadd-close>取消</button><button class="btn primary" type="button" data-bdadd-confirm>加入展示板</button></div>
  </div>`;
  document.body.appendChild(modal);
  const list = modal.querySelector('[data-bdadd-list]');
  const count = modal.querySelector('[data-bdadd-count]');
  let visible = [];
  const render = () => {
    visible = filterItems(allItems, boardAddFilterState(modal));
    list.innerHTML = visible.length ? visible.map(item => `<label class="board-add-item ${existing.has(item.uid) ? 'in' : ''}">
      <input type="checkbox" data-bdadd-uid="${escapeAttr(item.uid)}" ${existing.has(item.uid) ? 'disabled checked' : selected.has(item.uid) ? 'checked' : ''}>
      <span><strong>${escapeHtml(item.uid)}</strong>${existing.has(item.uid) ? ' <span class="bd-badge muted">已在板中</span>' : ''}<small>${escapeHtml(item.subject || '')} · ${escapeHtml(item.category || '')} · 难度 ${escapeHtml(item.difficulty)} · 熟练度 ${(asNumber(item.mastery, 0) * 100).toFixed(0)}%</small></span>
      <span class="board-add-labels-cell">${typeof lblChips === 'function' ? lblChips(item.labels || [], { max: 3 }) : ''}</span></label>`).join('') : '<div class="empty-inline">没有匹配的题目。</div>';
    count.textContent = `已选 ${selected.size} 题`;
  };
  modal.querySelectorAll('[data-bdadd]').forEach(node => node.addEventListener(node.tagName === 'INPUT' ? 'input' : 'change', render));
  modal.addEventListener('change', event => {
    const box = event.target.closest('[data-bdadd-uid]');
    if (!box || box.disabled) return;
    if (box.checked) selected.add(box.dataset.bdaddUid); else selected.delete(box.dataset.bdaddUid);
    count.textContent = `已选 ${selected.size} 题`;
  });
  modal.addEventListener('click', async event => {
    const label = event.target.closest('[data-bdadd-label]');
    if (label) { label.classList.toggle('on'); render(); return; }
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
  try {
    const boardId = BOARD_DETAIL.id;
    const result = await boardPost('/api/board/items/remove', { id: boardId, uids: [uid] });
    BOARD_DETAIL = result.board;
    await boardReloadData();
    uiToast(`已移除 ${uid}${item?.printed ? '（纸上仍有这道题，纸面记录保留其占位）' : ''}`, { actions: [{ label: '撤销', onClick: () => boardAddToBoard(boardId, [uid], { silent: true }) }] });
  } catch (error) { uiToast(`移除失败：${error.message}`, { kind: 'error' }); }
}
async function boardPersistItems(items, message = '') {
  if (!BOARD_DETAIL) return;
  const result = await boardPost('/api/board/update', { id: BOARD_DETAIL.id, items: boardItemsPayload(items) });
  BOARD_DETAIL = result.board;
  await boardReloadData();
  if (message) uiToast(message);
}
function boardSchedulePersist() {
  clearTimeout(BOARD_SAVE_TIMER);
  BOARD_SAVE_TIMER = setTimeout(() => {
    boardPost('/api/board/update', { id: BOARD_DETAIL.id, items: boardItemsPayload(BOARD_DETAIL?.items || []) })
      .then(result => { BOARD_DETAIL = result.board; boardScheduleEstimate(); })
      .catch(error => uiToast(`保存展示板失败：${error.message}`, { kind: 'error' }));
  }, 500);
}
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
function boardApplyPrintField(field, value) {
  if (!BOARD_DETAIL) return;
  const print = { ...(BOARD_DETAIL.print || {}) };
  if (field === 'note_ratio') { print[field] = clampNumber(value, 30, 55, 42) / 100; const node = document.querySelector('[data-board-ratio-value]'); if (node) node.textContent = `${Math.round(print[field] * 100)}%`; }
  else if (field === 'gap_lines') print[field] = clampNumber(value, 0, 24, 6);
  else if (field === 'binding_mm') print[field] = clampNumber(value, 10, 40, 22);
  else if (field === 'gap_lines') print[field] = Math.max(0, Math.min(24, parseInt(value, 10) || 0));
  else if (field === 'answers') print[field] = value === 'append' ? 'append' : 'none';
  else if (field === 'show_labels' || field === 'show_meta') print[field] = !!value;
  BOARD_DETAIL.print = print;
  clearTimeout(BOARD_SAVE_TIMER);
  BOARD_SAVE_TIMER = setTimeout(async () => {
    try { const result = await boardPost('/api/board/update', { id: BOARD_DETAIL.id, print }); BOARD_DETAIL = result.board; boardScheduleEstimate(); }
    catch (error) { uiToast(`版面保存失败：${error.message}`, { kind: 'error' }); }
  }, 500);
}

// ---------- 打印 / 导出 / 纸面记录 ----------
async function boardFetchExport(mode) {
  const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ board_id: BOARD_DETAIL.id, format: 'board', mode }) });
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
      preview.document.write('<!doctype html><meta charset="utf-8"><title>正在生成打印预览…</title><p style="font:14px system-ui;padding:24px;color:#444">正在生成打印预览…</p>');
      preview.document.close();
    } catch (error) {}
  }
  try {
    const html = await boardFetchExport(mode);
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    if (openPreview) {
      // location.replace 之后窗口对象本身不变，BOARD_WINDOWS.get(event.source) 的
      // 「标记为已打印」postMessage 回传照常工作。
      preview.location.replace(url);
      BOARD_WINDOWS.set(preview, { boardId: BOARD_DETAIL.id, mode });
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
function boardMeasureLayout(html, timeout = 30000) {
  return new Promise((resolve, reject) => {
    const frame = document.createElement('iframe');
    frame.setAttribute('aria-hidden', 'true');
    frame.style.cssText = 'position:fixed;left:-10000px;top:0;width:900px;height:1200px;visibility:hidden;pointer-events:none;border:0';
    let settled = false;
    const finish = (error, layout) => { if (settled) return; settled = true; window.removeEventListener('message', onMessage); clearTimeout(timer); frame.remove(); error ? reject(error) : resolve(layout); };
    const onMessage = event => { if (event.source === frame.contentWindow && event.data?.type === 'omrs-board-layout') finish(null, event.data.layout); };
    const timer = setTimeout(() => finish(new Error('版面测量超时')), timeout);
    window.addEventListener('message', onMessage);
    document.body.appendChild(frame);
    frame.srcdoc = html;
  });
}
async function boardEstimatePages() {
  if (!BOARD_DETAIL) return;
  const node = document.querySelector('[data-board-est]');
  if (!node) return;
  const mode = boardEffectiveMode();
  const token = ++BOARD_EST_TOKEN;
  const active = (BOARD_DETAIL.items || []).filter(item => !item.missing && !item.suspended);
  if (!active.length) { node.innerHTML = '板里没有可打印的题目。'; return; }
  if (mode === 'new' && !boardPrintedSummary().new_count) { node.innerHTML = '没有新增题目；切到「打印全部」可重印整板。'; return; }
  node.innerHTML = '预计页数计算中…';
  try {
    const layout = await boardMeasureLayout(await boardFetchExport(mode));
    if (token !== BOARD_EST_TOKEN) return;
    const nums = layout.page_numbers || [];
    const range = nums.length ? (nums.length === 1 ? `第 ${nums[0]} 页` : `第 ${nums[0]}–${nums[nums.length - 1]} 页`) : '—';
    node.innerHTML = mode === 'new'
      ? `本次补印 <b>${layout.rendered_pages}</b> 页（${range}）${layout.partial_page ? `，其中第 ${layout.partial_page} 页印在原纸上` : ''} · 打印后整板共 <b>${layout.pages}</b> 页${layout.warnings?.length ? ` · ⚠ ${layout.warnings.length} 处切图告警` : ''}`
      : `预计 <b>${layout.pages}</b> 页 · A4 纵向 · 左 ${asNumber(BOARD_DETAIL.print?.binding_mm, 22)} / 右 10 / 上下 12mm${layout.warnings?.length ? ` · ⚠ ${layout.warnings.length} 处切图告警` : ''}<br>打印时选 A4、缩放 100%，不要勾「适合页面」`;
  } catch (error) {
    if (token === BOARD_EST_TOKEN) node.innerHTML = `无法估算页数：${escapeHtml(error.message)}`;
  }
}
function boardScheduleEstimate() {
  clearTimeout(BOARD_EST_TIMER);
  if (!document.getElementById('panel-board')?.classList.contains('active')) return;
  BOARD_EST_TIMER = setTimeout(boardEstimatePages, 600);
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
    const layout = await boardMeasureLayout(await boardFetchExport(mode));
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
// 打印预览窗口里点「已打印，记录纸面」→ 收到版面 → 记录
if (typeof window !== 'undefined') window.addEventListener('message', async event => {
  if (event.data?.type !== 'omrs-board-printed') return;
  const pending = BOARD_WINDOWS.get(event.source);
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

// ---------- 事件委托 ----------
if (typeof document !== 'undefined') {
  document.addEventListener('click', event => {
    const menuToggle = event.target.closest?.('[data-board-menu-toggle]');
    if (menuToggle) {
      event.stopPropagation();
      const id = menuToggle.dataset.boardMenuToggle;
      document.querySelectorAll('[data-board-menu]').forEach(node => node.classList.toggle('open', node.dataset.boardMenu === id && !node.classList.contains('open')));
      return;
    }
    const sortToggle = event.target.closest?.('[data-board-sort-toggle]');
    if (sortToggle) { event.stopPropagation(); sortToggle.parentElement?.querySelector('[data-board-sort-menu]')?.classList.toggle('open'); return; }
    const sort = event.target.closest?.('[data-board-sort]');
    if (sort) { event.stopPropagation(); document.querySelectorAll('[data-board-sort-menu].open').forEach(node => node.classList.remove('open')); boardSort(sort.dataset.boardSort); return; }
    if (!event.target.closest?.('[data-board-menu]')) document.querySelectorAll('[data-board-menu].open').forEach(node => node.classList.remove('open'));
    if (!event.target.closest?.('[data-board-sort-menu]')) document.querySelectorAll('[data-board-sort-menu].open').forEach(node => node.classList.remove('open'));
    const action = event.target.closest?.('[data-board-action]');
    if (action) {
      event.stopPropagation();
      const type = action.dataset.boardAction;
      const id = action.dataset.boardId || BOARD_CURRENT;
      if (type === 'create') boardCreate();
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
    if (row && !event.target.closest('input,button,label,[data-lbl-target]')) {
      BOARD_SELECTED_UID = row.dataset.boardRow;
      document.querySelectorAll('[data-board-row]').forEach(node => node.classList.toggle('is-selected', node === row));
    }
  });
  document.addEventListener('dblclick', event => {
    if (event.target.closest?.('[data-board-rename-target]')) boardInlineRename();
    const row = event.target.closest?.('[data-board-row]');
    if (row && !event.target.closest('input,button,label,[data-lbl-target]')) { const item = boardCurrentItem(row.dataset.boardRow); if (item && !item.missing) viewQ(item.uid, (BOARD_DETAIL?.items || []).filter(i => !i.missing).map(i => i.uid)); }
  });
  document.addEventListener('input', event => {
    const gap = event.target.closest?.('[data-board-gap]');
    if (gap && BOARD_DETAIL) { const item = boardCurrentItem(gap.dataset.boardGap); if (item) { item.extra_gap_lines = clampNumber(gap.value, 0, 24, 0); boardSchedulePersist(); } return; }
    const print = event.target.closest?.('[data-board-print]');
    if (print && BOARD_DETAIL) boardApplyPrintField(print.dataset.boardPrint, print.type === 'checkbox' ? print.checked : print.value);
  });
  document.addEventListener('change', event => {
    const mode = event.target.closest?.('input[name="bd-print-mode"]');
    if (mode) { BOARD_PRINT_MODE = mode.value === 'new' ? 'new' : 'all'; document.querySelectorAll('.bd-modes label').forEach(node => node.classList.toggle('on', node.contains(mode))); boardScheduleEstimate(); }
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
    if (key === 'n') { event.preventDefault(); boardCreate(); }
    else if (key === 'a' && BOARD_DETAIL) { event.preventDefault(); boardAddPrompt(); }
    else if (key === 'p' && BOARD_DETAIL) { event.preventDefault(); boardPrintPreview(); }
    else if ((key === 'arrowup' || key === 'arrowdown') && BOARD_DETAIL?.items?.length) {
      event.preventDefault();
      const index = boardSelectedIndex();
      const next = index < 0 ? 0 : Math.max(0, Math.min(BOARD_DETAIL.items.length - 1, index + (key === 'arrowup' ? -1 : 1)));
      BOARD_SELECTED_UID = BOARD_DETAIL.items[next].uid;
      document.querySelectorAll('[data-board-row]').forEach(node => node.classList.toggle('is-selected', node.dataset.boardRow === BOARD_SELECTED_UID));
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

if (typeof module !== 'undefined') module.exports = { boardMoveItems, boardItemsPayload, boardUniqueUids };
