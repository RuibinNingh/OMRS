// === assets/board.js — 展示板 CRUD、排序、版面设置与打印预览 ===
let BOARD_DATA = [];
let BOARD_CURRENT = '';
let BOARD_DETAIL = null;
let BOARD_SAVE_TIMER = null;
let BOARD_SELECTED_UID = '';
let BOARD_ADD_MODAL = null;
const BOARD_PRINT_WINDOWS = new Map();

function boardAvailableBoards() {
  return Array.isArray(BOARD_DATA) ? BOARD_DATA : [];
}

function boardLastId() {
  try { return localStorage.getItem('omrs-board-last') || ''; } catch (error) { return ''; }
}

function boardRemember(id) {
  BOARD_CURRENT = id || '';
  try { if (id) localStorage.setItem('omrs-board-last', id); } catch (error) {}
}

function boardCurrentItem(uid) {
  return (BOARD_DETAIL?.items || []).find(item => item.uid === uid || item.question_id === uid) || null;
}

function boardSelectUid(uid) {
  BOARD_SELECTED_UID = String(uid || '');
  boardRender();
}

function boardSelectedIndex() {
  return (BOARD_DETAIL?.items || []).findIndex(item => item.uid === BOARD_SELECTED_UID);
}

function boardMoveItems(items, from, to) {
  const result = [...(items || [])];
  if (from < 0 || from >= result.length || to < 0 || to >= result.length || from === to) return result;
  const [item] = result.splice(from, 1);
  result.splice(to, 0, item);
  return result;
}

function boardItemsPayload(items) {
  return (items || []).map(item => ({
    question_id: item.question_id || '',
    uid: item.uid || '',
    added_at: item.added_at || '',
    extra_gap_lines: clampNumber(item.extra_gap_lines, 0, 24, 0),
    pin: !!item.pin,
  }));
}

function boardUniqueUids(uids) {
  return [...new Set((uids || []).map(uid => String(uid || '').trim()).filter(Boolean))];
}

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
      boardRender();
    }
  } catch (error) {
    BOARD_DATA = [];
    BOARD_DETAIL = null;
    boardRender();
  }
}

async function boardLoad(id, render = true) {
  if (!id) return;
  try {
    const result = await api(`/api/board?id=${encodeURIComponent(id)}`);
    BOARD_DETAIL = result.board || null;
    if (!BOARD_DETAIL?.items?.some(item => item.uid === BOARD_SELECTED_UID)) {
      BOARD_SELECTED_UID = BOARD_DETAIL?.items?.[0]?.uid || '';
    }
    boardRemember(id);
    if (render) boardRender();
  } catch (error) {
    alert(`读取展示板失败：${error.message}`);
  }
}

function boardListHtml() {
  if (!BOARD_DATA.length) {
    return `<div class="bd-empty">
      <div class="bd-empty-icon">▤</div><strong>还没有展示板</strong>
      <p>把考前必看的题目集中起来，反复重排并打印成左题右空的活页纸。</p>
      <button class="btn sm primary" data-board-action="create">新建第一个展示板</button>
    </div>`;
  }
  return `<div class="bd-list-head"><div class="card-title">展示板 <span class="hint">${BOARD_DATA.length}</span></div>
    <button class="btn sm primary" data-board-action="create">＋ 新建</button></div>
    <div class="bd-board-items">${BOARD_DATA.map(board => `<div class="bd-board-item ${board.id === BOARD_CURRENT ? 'on' : ''}" data-board-select="${escapeAttr(board.id)}">
      <div class="bd-board-name">${escapeHtml(board.name)}</div>
      <div class="bd-board-meta">${board.count} 题 · ${board.missing ? `缺失 ${board.missing} · ` : ''}${board.suspended ? `停用 ${board.suspended} · ` : ''}${escapeHtml((board.updated_at || '').replace('T', ' ').slice(0, 16))}</div>
      <div class="bd-board-actions"><button type="button" class="btn sm ghost" data-board-menu-toggle="${escapeAttr(board.id)}" aria-label="展示板操作">⋯</button>
        <div class="bd-board-menu" data-board-menu="${escapeAttr(board.id)}">
          <button type="button" data-board-action="rename" data-board-id="${escapeAttr(board.id)}">重命名</button>
          <button type="button" data-board-action="duplicate" data-board-id="${escapeAttr(board.id)}">复制</button>
          <button type="button" data-board-action="export-board" data-board-id="${escapeAttr(board.id)}">导出 HTML</button>
          <button type="button" class="danger" data-board-action="delete" data-board-id="${escapeAttr(board.id)}">删除</button>
        </div>
      </div>
    </div>`).join('')}</div>
    <div class="hint bd-list-note">板存的是题目引用；题目修改后重新打印即可得到最新内容。板名只在系统内使用，纸面标题固定为「错题集」。</div>`;
}

function boardRowHtml(item, index) {
  const labels = typeof lblChips === 'function' ? lblChips(item.labels || [], { lg: true }) : '';
  const state = item.missing ? '<span class="tag suspended">缺失</span>' : item.suspended ? '<span class="tag suspended">停用</span>' : '';
  const meta = item.missing ? '题目文件已删除或无法解析' : `${item.subject || ''} · ${item.category || ''} · 熟练度 ${(asNumber(item.mastery, 0) * 100).toFixed(0)}%`;
  return `<div class="bd-row ${item.missing ? 'missing' : ''} ${item.suspended ? 'suspended' : ''} ${BOARD_SELECTED_UID === item.uid ? 'is-selected' : ''}" draggable="true" tabindex="0" data-board-row="${escapeAttr(item.uid)}" data-board-index="${index}">
    <span class="bd-grip" title="拖拽排序">⠿</span><span class="bd-no">${index + 1}</span>
    <div class="bd-main"><div class="bd-row-head"><strong>${escapeHtml(item.uid || item.question_id || '未知题目')}</strong>${state}<span class="bd-row-labels" data-lbl-target="${escapeAttr(item.uid)}">${labels}</span></div>
      <div class="bd-row-meta">${escapeHtml(meta)}${item.due_date ? ` · ${escapeHtml(item.due_date)}` : ''}</div></div>
    <div class="bd-acts"><label class="bd-gap">＋ <input type="number" min="0" max="24" value="${clampNumber(item.extra_gap_lines, 0, 24, 0)}" data-board-gap="${escapeAttr(item.uid)}"> 行</label>
      <button type="button" class="btn sm" data-board-action="preview-item" data-board-uid="${escapeAttr(item.uid)}">预览</button>
      <button type="button" class="btn sm ghost" data-board-action="remove-item" data-board-uid="${escapeAttr(item.uid)}">✕</button></div>
  </div>`;
}

function boardContentHtml() {
  if (!BOARD_DETAIL) return '<div class="empty-inline">请选择或新建一个展示板。</div>';
  const items = BOARD_DETAIL.items || [];
  const missing = items.filter(item => item.missing).length;
  const suspended = items.filter(item => item.suspended).length;
  return `<div class="bd-toolbar"><div><div class="bd-title">${escapeHtml(BOARD_DETAIL.name)}</div><div class="hint">${items.length} 题${BOARD_DETAIL.last_printed_page ? ` · 已打印到第 ${BOARD_DETAIL.last_printed_page} 页` : ''}</div></div><span class="grow"></span>
    <button class="btn sm primary" data-board-action="add">＋ 添加题目</button><button class="btn sm" data-board-action="sync-label">按标记同步</button>
    <span class="bd-sort-wrap"><button class="btn sm" data-board-sort-toggle>排序 ▾</button>${boardSortMenuHtml()}</span><button class="btn sm" data-board-action="clear">清空</button></div>
    <div class="bd-rows">${items.length ? items.map(boardRowHtml).join('') : '<div class="empty-inline">板里还没有题目。点击「添加题目」或从题库批量加入。</div>'}</div>
    ${missing ? `<div class="bd-warn danger">⚠ ${missing} 道题已缺失，${suspended ? `另有 ${suspended} 道停用题，` : ''}导出时都会跳过。<button class="btn sm" data-board-action="clean-missing">清理缺失 / 停用</button></div>` : suspended ? `<div class="bd-warn">⚠ ${suspended} 道题已停用，导出时会跳过。<button class="btn sm" data-board-action="clean-missing">一键清理</button></div>` : ''}`;
}

function boardSettingsHtml() {
  if (!BOARD_DETAIL) return '<div class="empty-inline">选择展示板后设置版面。</div>';
  const print = BOARD_DETAIL.print || {};
  const nextPage = Math.max(1, asNumber(BOARD_DETAIL.last_printed_page, 0) + 1);
  return `<div class="card-title">版面</div>
    <div class="bd-field"><label>留白占比 <b data-board-ratio-value>${Math.round(asNumber(print.note_ratio, .42) * 100)}%</b></label><input type="range" min=".30" max=".55" step=".02" value="${asNumber(print.note_ratio, .42)}" data-board-print="note_ratio"></div>
    <div class="bd-field"><label>题间距 <b>行</b></label><input class="input" type="number" min="0" max="24" value="${asNumber(print.gap_lines, 6)}" data-board-print="gap_lines"><div class="hint">默认 6 行；它就是题目之间的写字空间。</div></div>
    <div class="bd-field"><label>装订边</label><select class="input" data-board-print="binding_mm"><option value="18" ${+print.binding_mm === 18 ? 'selected' : ''}>18mm</option><option value="22" ${+print.binding_mm === 22 ? 'selected' : ''}>22mm</option><option value="25" ${+print.binding_mm === 25 ? 'selected' : ''}>25mm</option></select></div>
    <div class="bd-field"><label>孔位标记</label><select class="input" data-board-print="binding_marks"><option value="none" ${print.binding_marks === 'none' ? 'selected' : ''}>不显示</option><option value="3hole" ${print.binding_marks === '3hole' ? 'selected' : ''}>3 孔</option><option value="26hole" ${print.binding_marks === '26hole' ? 'selected' : ''}>26 孔</option></select><div class="hint">只画在左侧装订边内，便于对齐打孔机。</div></div>
    <div class="bd-field"><label>答案</label><div class="seg"><button type="button" class="${print.answers === 'append' ? '' : 'on'}" data-board-answer="none">不含</button><button type="button" class="${print.answers === 'append' ? 'on' : ''}" data-board-answer="append">末页附答案</button></div></div>
    <div class="bd-field"><label>打印范围</label><div class="seg bd-range-seg"><button type="button" class="on" data-board-range="next">第 ${nextPage} 页起</button><button type="button" data-board-range="all">全部</button><button type="button" data-board-range="custom">自定义</button></div><div class="bd-range-custom" hidden><input class="input" type="number" min="1" value="${nextPage}" data-board-range-start> – <input class="input" type="number" min="1" value="${nextPage}" data-board-range-end> 页</div><div class="hint">板内页码是绝对页码；重排整板后，已打印页可能需要重打。</div></div>
    <div class="bd-est" data-board-est>打印预览会按整板分页，右栏保持纯空白。</div>
    <div class="bd-settings-actions"><button class="btn primary" data-board-action="preview">🖨 打印预览</button><button class="btn" data-board-action="export">导出 HTML</button><button class="btn sm ghost" data-board-action="clear-highwater">清零已打印页码</button></div>`;
}

function boardRender() {
  const list = document.getElementById('bd-list');
  const content = document.getElementById('bd-content');
  const settings = document.getElementById('bd-settings');
  if (list) list.innerHTML = boardListHtml();
  if (content) content.innerHTML = boardContentHtml();
  if (settings) settings.innerHTML = boardSettingsHtml();
  boardBindDrag();
}

async function boardCreate() {
  const name = prompt('展示板名称', '考前必看');
  if (!name || !name.trim()) return;
  try {
    const result = await api('/api/board/create', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: name.trim() }) });
    boardRemember(result.board.id);
    await boardReloadData();
  } catch (error) { alert(`新建展示板失败：${error.message}`); }
}

async function boardRename(id) {
  const board = BOARD_DATA.find(item => item.id === id) || BOARD_DETAIL;
  if (!board) return;
  const name = prompt('展示板名称', board.name);
  if (name === null || !name.trim()) return;
  try {
    await api('/api/board/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, name: name.trim() }) });
    await boardReloadData();
  } catch (error) { alert(`重命名失败：${error.message}`); }
}

async function boardDuplicate(id) {
  const board = BOARD_DATA.find(item => item.id === id) || BOARD_DETAIL;
  if (!board) return;
  const name = prompt('复制为', `${board.name} 副本`);
  if (!name || !name.trim()) return;
  try {
    const result = await api('/api/board/duplicate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, name: name.trim() }) });
    boardRemember(result.board.id);
    await boardReloadData();
  } catch (error) { alert(`复制失败：${error.message}`); }
}

async function boardDelete(id) {
  const board = BOARD_DATA.find(item => item.id === id) || BOARD_DETAIL;
  if (!board || !confirm(`删除展示板「${board.name}」？题目本身不会被删除。`)) return;
  try {
    await api('/api/board/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id }) });
    if (BOARD_CURRENT === id) { BOARD_CURRENT = ''; BOARD_DETAIL = null; }
    await boardReloadData();
  } catch (error) { alert(`删除展示板失败：${error.message}`); }
}

async function boardAddUids(uids) {
  const clean = boardUniqueUids(uids);
  if (!clean.length) return;
  if (!BOARD_DETAIL) {
    await boardReloadData();
    if (!BOARD_DETAIL) { await boardCreate(); }
  }
  if (!BOARD_DETAIL) return;
  try {
    const result = await api('/api/board/items/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: BOARD_DETAIL.id, uids: clean }) });
    BOARD_DETAIL = result.board;
    const boardName = BOARD_DETAIL.name;
    await boardReloadData();
    if (typeof switchTab === 'function') switchTab('board');
    if (typeof showBoardToast === 'function') showBoardToast(`已加入《${boardName}》`);
  } catch (error) { alert(`加入展示板失败：${error.message}`); }
}

async function qbChooseBoardForUids(uids) {
  const clean = [...new Set((uids || []).map(uid => String(uid || '').trim()).filter(Boolean))];
  if (!clean.length || typeof document === 'undefined') return;
  if (!boardAvailableBoards().length) {
    await boardReloadData();
  }
  if (!boardAvailableBoards().length) {
    await boardCreate();
    if (!boardAvailableBoards().length && !BOARD_CURRENT) return;
  }
  const modal = document.createElement('div');
  modal.className = 'modal-overlay open';
  modal.innerHTML = `<div class="modal qb-board-modal">
    <div class="modal-close" data-qb-board-close>✕</div>
    <h2>加入展示板</h2>
    <p class="hint">已选 ${clean.length} 道题，请选择目标展示板。</p>
    <div class="qb-board-options">${boardAvailableBoards().map(board => `<label><input type="radio" name="qb-board" value="${escapeAttr(board.id)}" ${board.id === boardLastId() ? 'checked' : ''}> <span>${escapeHtml(board.name)} <small>${board.count} 题</small></span></label>`).join('')}</div>
    <div class="qb-view-modal-foot"><button type="button" class="btn" data-qb-board-close>取消</button><button type="button" class="btn primary" data-qb-board-confirm>加入展示板</button></div>
  </div>`;
  document.body.appendChild(modal);
  const close = () => modal.remove();
  modal.addEventListener('click', async event => {
    if (event.target === modal || event.target.closest('[data-qb-board-close]')) {
      close();
      return;
    }
    if (!event.target.closest('[data-qb-board-confirm]')) return;
    const id = modal.querySelector('input[name="qb-board"]:checked')?.value;
    if (!id) {
      alert('请选择展示板');
      return;
    }
    close();
    await boardLoad(id, false);
    await boardAddUids(clean);
  });
}

async function boardQuickAdd(uid) {
  let id = boardLastId();
  if (!BOARD_DATA.length) await boardReloadData();
  if (!BOARD_DATA.some(board => board.id === id)) id = BOARD_DATA[0]?.id || '';
  if (!id) { await boardCreate(); id = BOARD_CURRENT; }
  if (!id) return;
  await boardLoad(id, false);
  await boardAddUids([uid]);
}

function boardAddSelectOptions(values, placeholder) {
  return `<option value="">${escapeHtml(placeholder)}</option>${values.map(value => `<option value="${escapeAttr(value)}">${escapeHtml(value)}</option>`).join('')}`;
}

function boardAddFilterState(modal) {
  const value = selector => modal.querySelector(selector)?.value || '';
  const selectedLabels = [...modal.querySelectorAll('[data-board-add-label].on')]
    .map(node => node.dataset.boardAddLabel);
  const masteryMin = value('[data-board-add-filter="mastery-min"]');
  const masteryMax = value('[data-board-add-filter="mastery-max"]');
  return {
    text: value('[data-board-add-filter="search"]').trim().toLowerCase(),
    subject: value('[data-board-add-filter="subject"]'),
    category: value('[data-board-add-filter="category"]'),
    tag: value('[data-board-add-filter="tag"]'),
    knowledgeTag: value('[data-board-add-filter="knowledge"]'),
    labels: selectedLabels,
    labelMode: value('[data-board-add-filter="label-mode"]') || 'any',
    difficultyMin: asNumber(value('[data-board-add-filter="difficulty-min"]'), 0),
    difficultyMax: asNumber(value('[data-board-add-filter="difficulty-max"]'), 10) || 10,
    masteryMin: masteryMin === '' ? null : clampNumber(masteryMin, 0, 100, 0) / 100,
    masteryMax: masteryMax === '' ? null : clampNumber(masteryMax, 0, 100, 100) / 100,
    dueFilter: value('[data-board-add-filter="due"]'),
    suspended: value('[data-board-add-filter="suspended"]'),
    sort: 'mastery-asc',
  };
}

function boardAddLabelButtons(items) {
  const names = new Set((items || []).flatMap(item => item.labels || []));
  const defs = (LABELS || []).filter(label => !label.archived);
  names.forEach(name => {
    if (!defs.some(label => label.name === name)) defs.push({ name, color: '#64748b' });
  });
  return defs.map(label => `<button type="button" class="label-filter-chip" data-board-add-label="${escapeAttr(label.name)}">${lblChip(label)}</button>`).join('')
    || '<span class="hint">暂无标记</span>';
}

async function boardAddPrompt() {
  if (!BOARD_DETAIL) return;
  boardCloseAddModal();
  const allItems = getItems();
  const subjects = [...new Set(allItems.map(item => item.subject).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const categories = [...new Set(allItems.map(item => item.category).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const knowledge = [...new Set(allItems.flatMap(item => item.knowledge_tags || []).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const modal = document.createElement('div');
  modal.className = 'modal-overlay open';
  modal.id = 'board-add-modal';
  modal.innerHTML = `<div class="modal board-add-modal">
    <div class="modal-close" data-board-add-close>✕</div>
    <h2>添加题目到「${escapeHtml(BOARD_DETAIL.name)}」</h2>
    <div class="hint" style="margin-bottom:10px">筛选或勾选题目；已在本板的题目会自动跳过。</div>
    <div class="board-add-filters">
      <input class="input" data-board-add-filter="search" placeholder="搜索 UID / 科目 / 分类 / 状态 / 知识点 / 标记…">
      <select class="input" data-board-add-filter="subject">${boardAddSelectOptions(subjects, '全部科目')}</select>
      <select class="input" data-board-add-filter="category">${boardAddSelectOptions(categories, '全部分类')}</select>
      <select class="input" data-board-add-filter="tag"><option value="">全部状态</option><option value="待攻克">待攻克</option><option value="已击杀">已击杀</option><option value="易错">易错坑</option></select>
      <select class="input" data-board-add-filter="knowledge">${boardAddSelectOptions(knowledge, '全部知识点')}</select>
      <div class="board-add-label-filter"><span class="hint">标记</span><div>${boardAddLabelButtons(allItems)}</div></div>
      <select class="input" data-board-add-filter="label-mode"><option value="any">标记任一</option><option value="all">标记全部</option></select>
      <input type="number" class="input" min="1" max="10" data-board-add-filter="difficulty-min" placeholder="难度≥">
      <input type="number" class="input" min="1" max="10" data-board-add-filter="difficulty-max" placeholder="难度≤">
      <input type="number" class="input" min="0" max="100" data-board-add-filter="mastery-min" placeholder="熟练度≥%">
      <input type="number" class="input" min="0" max="100" data-board-add-filter="mastery-max" placeholder="熟练度≤%">
      <select class="input" data-board-add-filter="due"><option value="">全部到期状态</option><option value="overdue">已逾期</option><option value="today">今日到期</option><option value="3days">3天内到期</option><option value="7days">7天内到期</option><option value="future">未到期</option></select>
      <select class="input" data-board-add-filter="suspended"><option value="">活动题目</option><option value="suspended">仅停用题目</option><option value="all">含停用全部</option></select>
    </div>
    <div class="board-add-list" data-board-add-list></div>
    <div class="board-add-foot"><span class="hint" data-board-add-count>已选 0 题</span><span class="grow"></span><button class="btn" data-board-add-close>取消</button><button class="btn primary" data-board-add-confirm>加入展示板</button></div>
  </div>`;
  document.body.appendChild(modal);
  BOARD_ADD_MODAL = modal;
  const selected = new Set();
  const existing = new Set((BOARD_DETAIL.items || []).map(item => item.uid));
  const filters = modal.querySelectorAll('[data-board-add-filter]');
  const list = modal.querySelector('[data-board-add-list]');
  const count = modal.querySelector('[data-board-add-count]');
  const render = () => {
    const state = boardAddFilterState(modal);
    const items = filterItems(allItems, state).filter(item => !existing.has(item.uid));
    list.innerHTML = items.length ? items.map(item => `<label class="board-add-item">
      <input type="checkbox" data-board-add-uid="${escapeAttr(item.uid)}" ${selected.has(item.uid) ? 'checked' : ''}>
      <span><strong>${escapeHtml(item.uid)}</strong><small>${escapeHtml(item.subject || '')} · ${escapeHtml(item.category || '')}</small></span>
      <span class="board-add-labels">${typeof lblChips === 'function' ? lblChips(item.labels || []) : ''}</span>
    </label>`).join('') : '<div class="empty-inline">没有可添加的题目。</div>';
    count.textContent = `已选 ${selected.size} 题`;
  };
  filters.forEach(node => node.addEventListener(node.tagName === 'INPUT' && node.type === 'number' ? 'input' : 'change', render));
  modal.addEventListener('change', event => {
    const checkbox = event.target.closest('[data-board-add-uid]');
    if (!checkbox) return;
    if (checkbox.checked) selected.add(checkbox.dataset.boardAddUid);
    else selected.delete(checkbox.dataset.boardAddUid);
    count.textContent = `已选 ${selected.size} 题`;
  });
  modal.addEventListener('click', event => {
    const label = event.target.closest('[data-board-add-label]');
    if (!label) return;
    label.classList.toggle('on');
    render();
  });
  modal.addEventListener('click', async event => {
    if (event.target === modal || event.target.closest('[data-board-add-close]')) {
      boardCloseAddModal();
      return;
    }
    if (!event.target.closest('[data-board-add-confirm]')) return;
    const uids = [...selected];
    boardCloseAddModal();
    await boardAddUids(uids);
  });
  render();
  modal.querySelector('[data-board-add-filter="search"]')?.focus();
}

function boardCloseAddModal() {
  BOARD_ADD_MODAL?.remove();
  BOARD_ADD_MODAL = null;
}

async function boardRemoveItem(uid) {
  if (!BOARD_DETAIL) return;
  try {
    const result = await api('/api/board/items/remove', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: BOARD_DETAIL.id, uids: [uid] }) });
    BOARD_DETAIL = result.board;
    await boardReloadData();
  } catch (error) { alert(`移除失败：${error.message}`); }
}

async function boardPersistItems(items, message = '', reorderFrom = null) {
  if (!BOARD_DETAIL) return;
  const result = await api('/api/board/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: BOARD_DETAIL.id, items: boardItemsPayload(items) }) });
  BOARD_DETAIL = result.board;
  await boardReloadData();
  if (message && typeof showBoardToast === 'function') showBoardToast(message);
  if (reorderFrom != null && BOARD_DETAIL.last_printed_page > 0 && typeof showBoardToast === 'function') {
    showBoardToast(`重排后第 ${Math.max(1, reorderFrom + 1)} 页起页码可能变化，建议重打后续页面`);
  }
}

function boardSchedulePersist() {
  clearTimeout(BOARD_SAVE_TIMER);
  BOARD_SAVE_TIMER = setTimeout(() => {
    boardPersistItems(BOARD_DETAIL?.items || []).catch(error => alert(`保存展示板失败：${error.message}`));
  }, 500);
}

async function boardSort() {
  if (!BOARD_DETAIL) return;
  boardCloseSortMenus();
  const choice = BOARD_SORT_CHOICE;
  BOARD_SORT_CHOICE = '';
  if (!choice) return;
  const items = [...(BOARD_DETAIL.items || [])];
  if (choice === 'reverse') items.reverse();
  else if (choice === 'mastery') items.sort((a, b) => asNumber(a.mastery, 0) - asNumber(b.mastery, 0));
  else if (choice === 'due') items.sort((a, b) => String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')));
  else if (choice === 'added') items.sort((a, b) => String(a.added_at || '').localeCompare(String(b.added_at || '')));
  else items.sort((a, b) => `${a.subject || ''}${a.category || ''}${a.uid || ''}`.localeCompare(`${b.subject || ''}${b.category || ''}${b.uid || ''}`, 'zh-CN'));
  await boardPersistItems(items, '排序已保存', 0);
}

let BOARD_SORT_CHOICE = '';

function boardCloseSortMenus() {
  document.querySelectorAll('[data-board-sort-menu].open').forEach(node => node.classList.remove('open'));
}

function boardSortMenuHtml() {
  return `<div class="bd-sort-menu" data-board-sort-menu>
    <button type="button" data-board-sort="subject">按科目</button>
    <button type="button" data-board-sort="mastery">按熟练度升</button>
    <button type="button" data-board-sort="due">按到期</button>
    <button type="button" data-board-sort="added">按加入时间</button>
    <button type="button" data-board-sort="reverse">反转</button>
  </div>`;
}

async function boardSyncLabel() {
  if (!BOARD_DETAIL) return;
  const modal = document.createElement('div');
  modal.className = 'modal-overlay open';
  modal.innerHTML = `<div class="modal board-sync-modal">
    <div class="modal-close" data-board-sync-close>✕</div>
    <h2>按标记同步</h2>
    <p class="hint">把拥有该标记的题目追加到当前展示板，板内已有题目会自动去重。</p>
    <div class="board-sync-options">${(LABELS || []).filter(label => !label.archived).map(label => `<label><input type="radio" name="board-sync-label" value="${escapeAttr(label.name)}" ${BOARD_DETAIL.source_labels?.[0] === label.name ? 'checked' : ''}> ${lblChip(label)}</label>`).join('') || '<div class="empty-inline">暂无标记，请先创建一个标记。</div>'}</div>
    <div class="qb-view-modal-foot"><button class="btn" data-board-sync-close>取消</button><button class="btn primary" data-board-sync-confirm>同步到展示板</button></div>
  </div>`;
  document.body.appendChild(modal);
  const close = () => modal.remove();
  modal.addEventListener('click', async event => {
    if (event.target === modal || event.target.closest('[data-board-sync-close]')) { close(); return; }
    if (!event.target.closest('[data-board-sync-confirm]')) return;
    const label = modal.querySelector('input[name="board-sync-label"]:checked')?.value || '';
    if (!label) { alert('请选择标记'); return; }
    const uids = getItems().filter(item => (item.labels || []).includes(label)).map(item => item.uid);
    try {
      const result = await api('/api/board/items/add', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: BOARD_DETAIL.id, uids }) });
      BOARD_DETAIL = result.board;
      await api('/api/board/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: BOARD_DETAIL.id, source_labels: [label] }) });
      close();
      await boardReloadData();
      showBoardToast(uids.length ? `已同步 ${uids.length} 道题` : '没有带该标记的新题目');
    } catch (error) { alert(`同步标记失败：${error.message}`); }
  });
}

async function boardCleanMissing() {
  if (!BOARD_DETAIL) return;
  const kept = (BOARD_DETAIL.items || []).filter(item => !item.missing && !item.suspended);
  await boardPersistItems(kept, '已清理缺失 / 停用题');
}

async function boardClear() {
  if (!BOARD_DETAIL || !confirm(`清空展示板「${BOARD_DETAIL.name}」？`)) return;
  await boardPersistItems([], '展示板已清空');
}

function boardRange() {
  const mode = document.querySelector('[data-board-range].on')?.dataset.boardRange || 'next';
  const next = Math.max(1, asNumber(BOARD_DETAIL?.last_printed_page, 0) + 1);
  if (mode === 'all') return { start: 1, end: null };
  if (mode === 'custom') return {
    start: Math.max(1, asNumber(document.querySelector('[data-board-range-start]')?.value, next)),
    end: Math.max(1, asNumber(document.querySelector('[data-board-range-end]')?.value, next)),
  };
  return { start: next, end: null };
}

async function boardExportCurrent(openPreview = false) {
  if (!BOARD_DETAIL) return;
  const range = boardRange();
  if (range.end != null && range.start > range.end) {
    showBoardToast('打印范围无效：起始页不能大于结束页');
    return;
  }
  try {
    const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      board_id: BOARD_DETAIL.id, format: 'board', page_start: range.start, page_end: range.end,
    }) });
    if (!response.ok) throw new Error('导出失败');
    const blob = await response.blob();
    const html = await blob.text();
    const doc = typeof DOMParser === 'function' ? new DOMParser().parseFromString(html, 'text/html') : null;
    const metaValue = name => doc?.querySelector(`meta[name="${name}"]`)?.content || '';
    // `omrs-page-count` is rewritten by board.js after the browser finishes
    // real pagination.  Before opening the blob, use the server estimate only
    // as a guard; the printed absolute end page comes from the confirmation
    // message emitted by the export document.
    const pageCount = Math.max(
      0,
      Number(metaValue('omrs-page-count'))
        || Number(metaValue('omrs-estimated-page-count'))
        || 0,
    );
    if (!pageCount) throw new Error('导出结果没有可打印页面');
    const absoluteEnd = Math.max(
      range.start,
      Number(metaValue('omrs-page-end')) || range.start + pageCount - 1,
    );
    if (openPreview) {
      const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
      const preview = window.open(url, '_blank');
      if (!preview) throw new Error('浏览器阻止了预览窗口，请允许弹出窗口后重试');
      BOARD_PRINT_WINDOWS.set(preview, {
        boardId: BOARD_DETAIL.id,
        pageStart: range.start,
        requestedEnd: range.end,
      });
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } else {
      const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `OMRS-board-${BOARD_DETAIL.name}.html`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1200);
    }
  } catch (error) { alert(`展示板导出失败：${error.message}`); }
}

if (typeof window !== 'undefined') window.addEventListener('message', async event => {
  if (event.data?.type !== 'omrs-board-printed') return;
  const pending = BOARD_PRINT_WINDOWS.get(event.source);
  if (!pending || event.data.boardId !== pending.boardId) return;
  const pageEnd = Number(event.data.pageEnd);
  if (!Number.isInteger(pageEnd) || pageEnd < pending.pageStart) return;
  if (pending.requestedEnd != null && pageEnd > pending.requestedEnd) return;
  BOARD_PRINT_WINDOWS.delete(event.source);
  try {
    await api('/api/board/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: pending.boardId,
        last_printed_page: Math.max(0, asNumber(BOARD_DETAIL?.last_printed_page, 0), pageEnd),
      }),
    });
    if (BOARD_CURRENT === pending.boardId) await boardReloadData();
    showBoardToast(`已确认打印，展示板推进到第 ${pageEnd} 页`);
  } catch (error) {
    showBoardToast(`打印确认保存失败：${error.message}`);
  }
});

function boardPrintPreview() { return boardExportCurrent(true); }
function showBoardToast(message) {
  let node = document.getElementById('board-toast');
  if (!node) { node = document.createElement('div'); node.id = 'board-toast'; node.className = 'bd-toast'; document.body.appendChild(node); }
  node.textContent = message;
  node.classList.add('show');
  clearTimeout(node._timer);
  node._timer = setTimeout(() => node.classList.remove('show'), 2600);
}

function boardApplyPrintField(field, value) {
  if (!BOARD_DETAIL) return;
  const print = { ...(BOARD_DETAIL.print || {}) };
  if (field === 'note_ratio') {
    print[field] = clampNumber(value, .30, .55, .42);
    const valueNode = document.querySelector('[data-board-ratio-value]');
    if (valueNode) valueNode.textContent = `${Math.round(print[field] * 100)}%`;
  } else if (field === 'gap_lines') print[field] = clampNumber(value, 0, 24, 6);
  else if (field === 'binding_mm') print[field] = clampNumber(value, 10, 40, 22);
  else if (field === 'binding_marks') print[field] = ['none', '3hole', '26hole'].includes(value) ? value : 'none';
  else if (field === 'answers') print[field] = value === 'append' ? 'append' : 'none';
  BOARD_DETAIL.print = print;
  clearTimeout(BOARD_SAVE_TIMER);
  BOARD_SAVE_TIMER = setTimeout(async () => {
    try {
      const result = await api('/api/board/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: BOARD_DETAIL.id, print }) });
      BOARD_DETAIL = result.board;
      await boardReloadData();
    } catch (error) { showBoardToast(`版面保存失败：${error.message}`); }
  }, 500);
}

function boardBindDrag() {
  const content = document.getElementById('bd-content');
  if (!content || content.dataset.bound === '1') return;
  content.dataset.bound = '1';
  content.addEventListener('dragstart', event => {
    const row = event.target.closest('[data-board-row]');
    if (row) event.dataTransfer?.setData('text/plain', row.dataset.boardIndex);
  });
  content.addEventListener('dragover', event => { if (event.target.closest('[data-board-row]')) event.preventDefault(); });
  content.addEventListener('drop', async event => {
    const row = event.target.closest('[data-board-row]');
    if (!row || !BOARD_DETAIL) return;
    event.preventDefault();
    const from = asNumber(event.dataTransfer?.getData('text/plain'), -1);
    const to = asNumber(row.dataset.boardIndex, -1);
    if (from === to || from < 0 || to < 0) return;
    await boardPersistItems(boardMoveItems(BOARD_DETAIL.items, from, to), '排序已保存', Math.min(from, to));
  });
}

document.addEventListener('click', event => {
  const menuToggle = event.target.closest?.('[data-board-menu-toggle]');
  if (menuToggle) {
    event.stopPropagation();
    document.querySelectorAll('[data-board-menu].open').forEach(node => {
      if (node.dataset.boardMenu !== menuToggle.dataset.boardMenuToggle) node.classList.remove('open');
    });
    document.querySelector(`[data-board-menu="${menuToggle.dataset.boardMenuToggle}"]`)?.classList.toggle('open');
    return;
  }
  const sortToggle = event.target.closest?.('[data-board-sort-toggle]');
  if (sortToggle) {
    event.stopPropagation();
    const menu = sortToggle.parentElement?.querySelector('[data-board-sort-menu]');
    menu?.classList.toggle('open');
    return;
  }
  const sort = event.target.closest?.('[data-board-sort]');
  if (sort) {
    event.stopPropagation();
    BOARD_SORT_CHOICE = sort.dataset.boardSort;
    boardSort();
    return;
  }
  const action = event.target.closest?.('[data-board-action]');
  if (action) {
    const type = action.dataset.boardAction;
    const id = action.dataset.boardId || BOARD_CURRENT;
    if (type === 'create') boardCreate();
    else if (type === 'rename') boardRename(id);
    else if (type === 'duplicate') boardDuplicate(id);
    else if (type === 'delete') boardDelete(id);
    else if (type === 'export-board') { boardLoad(id, false).then(() => boardExportCurrent(false)); }
    else if (type === 'add') boardAddPrompt();
    else if (type === 'remove-item') boardRemoveItem(action.dataset.boardUid);
    else if (type === 'preview-item') viewQ(action.dataset.boardUid, (BOARD_DETAIL?.items || []).map(item => item.uid));
    else if (type === 'sync-label') boardSyncLabel();
    else if (type === 'clean-missing') boardCleanMissing();
    else if (type === 'clear') boardClear();
    else if (type === 'preview') boardPrintPreview();
    else if (type === 'export') boardExportCurrent(false);
    else if (type === 'clear-highwater') { api('/api/board/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: BOARD_CURRENT, last_printed_page: 0 }) }).then(boardReloadData); }
    return;
  }
  const select = event.target.closest?.('[data-board-select]');
  if (select) { boardLoad(select.dataset.boardSelect); return; }
  const answer = event.target.closest?.('[data-board-answer]');
  if (answer && BOARD_DETAIL) {
    boardApplyPrintField('answers', answer.dataset.boardAnswer);
    boardRender();
    return;
  }
  const range = event.target.closest?.('[data-board-range]');
  if (range) {
    document.querySelectorAll('[data-board-range]').forEach(node => node.classList.toggle('on', node === range));
    const custom = document.querySelector('.bd-range-custom');
    if (custom) custom.hidden = range.dataset.boardRange !== 'custom';
  }
});

document.addEventListener('input', event => {
  const gap = event.target.closest?.('[data-board-gap]');
  if (gap && BOARD_DETAIL) {
    const item = boardCurrentItem(gap.dataset.boardGap);
    if (item) { item.extra_gap_lines = clampNumber(gap.value, 0, 24, 0); boardSchedulePersist(); }
    return;
  }
  const print = event.target.closest?.('[data-board-print]');
  if (print) boardApplyPrintField(print.dataset.boardPrint, print.value);
});

document.addEventListener('keydown', event => {
  if (!document.getElementById('panel-board')?.classList.contains('active')) return;
  if (event.target.closest?.('input,textarea,select,button')) return;
  const key = event.key.toLowerCase();
  if (key === 'n') boardCreate();
  else if (key === 'a') boardAddPrompt();
  else if (key === 'p') boardPrintPreview();
  else if ((key === 'arrowup' || key === 'arrowdown') && BOARD_DETAIL) {
    event.preventDefault();
    const index = boardSelectedIndex();
    if (index < 0) return boardSelectUid(BOARD_DETAIL.items?.[0]?.uid || '');
    const delta = key === 'arrowup' ? -1 : 1;
    if (event.ctrlKey || event.metaKey) {
      const to = index + delta;
      if (to >= 0 && to < BOARD_DETAIL.items.length) {
        boardPersistItems(boardMoveItems(BOARD_DETAIL.items, index, to), '排序已保存', Math.min(index, to));
      }
    } else {
      boardSelectUid(BOARD_DETAIL.items[index + delta]?.uid || BOARD_DETAIL.items[index].uid);
    }
  } else if (key === 'enter' && BOARD_DETAIL) {
    const current = BOARD_DETAIL.items?.[boardSelectedIndex()];
    if (current && !current.missing) viewQ(current.uid, BOARD_DETAIL.items.map(item => item.uid));
    else if (current?.missing) showBoardToast('该题已缺失，无法打开题目；可先清理缺失条目');
  } else if ((key === 'delete' || key === 'backspace') && BOARD_DETAIL) {
    const current = BOARD_DETAIL.items?.[boardSelectedIndex()];
    if (current) boardRemoveItem(current.uid);
  }
});

document.addEventListener('click', event => {
  const row = event.target.closest?.('[data-board-row]');
  if (row && !event.target.closest('input,button,[data-lbl-target]')) {
    boardSelectUid(row.dataset.boardRow);
  }
  if (!event.target.closest('[data-board-menu-toggle],[data-board-menu]')) {
    document.querySelectorAll('[data-board-menu].open').forEach(node => node.classList.remove('open'));
  }
  if (!event.target.closest('[data-board-sort-toggle],[data-board-sort-menu]')) boardCloseSortMenus();
});

if (typeof module !== 'undefined') module.exports = {
  boardMoveItems, boardItemsPayload, boardUniqueUids,
};
