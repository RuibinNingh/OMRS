// === assets/board_picker.js — 展示板选板浮层与文件夹分组 ===
// 从 board.js 拆出（board.js 曾到 1800+ 行，板 CRUD、选板、版面、打印、预览挤在一个文件里）。
// 依赖 board.js（BOARD_DATA / BOARD_FOLDERS / boardAddToBoard / boardCreate / boardLoad …）
// 与 core.js（api / uiToast / uiPrompt）；必须排在 board.js 之后。
//
// 共享全局作用域，因此这次拆分是纯搬运：函数名、签名、调用关系、行内 handler 全不变。
// 唯一有顺序要求的是 BOARD_PICKER 这个 let——它跟着浮层实现一起搬到了这里。

let BOARD_PICKER = null;                      // 当前打开的选板浮层

// ---------- 选板浮层 boardPicker：所有「加入展示板」入口的唯一实现 ----------
// 设计要点：动作发生前先看见目标板，并且当场能改；单击行即完成，没有「确定」按钮。
// 视觉与键盘沿用 labels.js 的 label-picker-pop（同一套浮层语言，不新造第二种）。

// 分组：文件夹顺序在前，未归档恒在最后；空文件夹保留（左栏要显示「把板拖进来」占位）。
function boardFolderTree(boards, folders, options = {}) {
  const list = Array.isArray(boards) ? boards : [];
  const groups = (Array.isArray(folders) ? folders : [])
    .slice()
    .sort((a, b) => asNumber(a.order, 0) - asNumber(b.order, 0))
    .map(folder => ({ id: folder.id, name: folder.name, folder, boards: [] }));
  const index = new Map(groups.map(group => [group.id, group]));
  const unfiled = { id: '', name: '未归档', folder: null, boards: [] };
  list.forEach(board => (index.get(board.folder_id) || unfiled).boards.push(board));
  groups.forEach(group => group.boards.sort((a, b) => asNumber(a.order, 0) - asNumber(b.order, 0)));
  unfiled.boards.sort((a, b) => asNumber(a.order, 0) - asNumber(b.order, 0));
  const result = options.dropEmpty ? groups.filter(group => group.boards.length) : groups;
  // 未归档不是真文件夹：没有板时不占一行；一个文件夹都没有时也不必显示这个标题
  return unfiled.boards.length && result.length ? [...result, unfiled] : (result.length ? result : [unfiled]);
}

// 行状态：全新 / 部分已在板中 / 全部已在板中。pending 是这次点击真正会加进去的那些题。
function boardPickerRowState(board, uids) {
  const wanted = boardUniqueUids(uids);
  const owned = new Set(board?.uids || []);
  const pending = wanted.filter(uid => !owned.has(uid));
  const have = wanted.length - pending.length;
  if (!wanted.length) return { kind: 'new', have: 0, total: 0, pending: [] };
  if (!have) return { kind: 'new', have, total: wanted.length, pending };
  if (!pending.length) return { kind: 'full', have, total: wanted.length, pending };
  return { kind: 'partial', have, total: wanted.length, pending };
}

// 过滤态展平分组，每行带上所属文件夹名（否则同名板分不清）。板名与文件夹名都参与匹配。
function boardPickerFilter(groups, query) {
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

// 最近：上次用过的板 + 最近更新的，最多 2 条；与下方全量列表共用同一份状态（同一板同时打勾）。
function boardPickerRecent(boards, lastId, limit = 2) {
  const list = (boards || []).slice();
  const last = list.find(board => board.id === lastId);
  const rest = list
    .filter(board => board.id !== lastId)
    .sort((a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || '')));
  return [last, ...rest].filter(Boolean).slice(0, limit);
}

function boardPickerClose() {
  if (!BOARD_PICKER) return;
  document.removeEventListener('keydown', BOARD_PICKER.onKey, true);
  document.removeEventListener('click', BOARD_PICKER.onOutside, true);
  window.removeEventListener('resize', BOARD_PICKER.onReflow);
  window.removeEventListener('scroll', BOARD_PICKER.onReflow, true);
  BOARD_PICKER.node.remove();
  const done = BOARD_PICKER.onDone;
  const touched = BOARD_PICKER.touched;
  BOARD_PICKER = null;
  if (typeof done === 'function') done(touched);
}

function boardPickerMetaHtml(board, state) {
  const paper = board.printed_summary || {};
  const bits = [`${board.count} 题`];
  if (paper.pages) bits.push(`<span class="pt">已印 ${paper.pages} 页</span>`);
  if (board.missing) bits.push(`<span class="warn">缺失 ${board.missing}</span>`);
  if (state.kind === 'full') return '<span class="bd-picker-state">已全部在板中</span>';
  if (state.kind === 'partial') bits.push(`<span class="bd-picker-state">已有 ${state.have}/${state.total}</span>`);
  return bits.join(' · ');
}

function boardPickerOptionHtml(board, state, folderName, checked) {
  const cue = checked ? '✓' : (state.kind === 'full' ? '↗' : '');
  return `<button type="button" class="bd-picker-option ${state.kind === 'full' ? 'is-full' : ''} ${checked ? 'is-added' : ''}"
    data-bd-pick="${escapeAttr(board.id)}" role="option" aria-selected="${checked ? 'true' : 'false'}"
    title="${escapeAttr(board.note || board.name)}">
    <span class="check">${cue}</span>
    <span class="nm">${escapeHtml(board.name)}${folderName ? `<small>${escapeHtml(folderName)}</small>` : ''}</span>
    <span class="cnt">${boardPickerMetaHtml(board, state)}</span></button>`;
}

function boardPickerRender() {
  const picker = BOARD_PICKER;
  if (!picker) return;
  const query = picker.search.value.trim();
  const groups = boardFolderTree(picker.boards, picker.folders, { dropEmpty: true });
  const filtered = boardPickerFilter(groups, query);
  const rowHtml = (board, folderName) => {
    const state = boardPickerRowState(board, picker.uids);
    return boardPickerOptionHtml(board, state, folderName, picker.added.has(board.id));
  };
  let html = '';
  if (filtered) {
    html = filtered.length
      ? filtered.map(row => rowHtml(row.board, row.folderName)).join('')
      : `<div class="bd-picker-empty">没有匹配「${escapeHtml(query)}」的板</div>`;
  } else {
    // 「最近」只在列表长到要滚动时才有意义；板少时它只会让同一个板出现两次
    const recent = picker.boards.length > 6 ? boardPickerRecent(picker.boards, boardLastId()) : [];
    if (recent.length) {
      html += `<div class="bd-picker-group plain"><span>最近</span></div>${recent.map(board => rowHtml(board, '')).join('')}`;
    }
    html += groups.map(group => {
      const folded = group.id && picker.collapsed.has(group.id);
      const head = !picker.showGroups ? ''
        : group.id
          ? `<div class="bd-picker-group ${folded ? 'folded' : ''}" data-bd-pick-fold="${escapeAttr(group.id)}">
               <button type="button" class="bd-picker-chev" aria-expanded="${folded ? 'false' : 'true'}" tabindex="-1">▾</button>
               <span>${escapeHtml(group.name)}</span><em>${group.boards.length}</em></div>`
          : `<div class="bd-picker-group plain"><span>${escapeHtml(group.name)}</span><em>${group.boards.length}</em></div>`;
      return head + (folded ? '' : group.boards.map(board => rowHtml(board, '')).join(''));
    }).join('');
  }
  picker.options.innerHTML = html || '<div class="bd-picker-empty">还没有展示板：下面新建一个。</div>';
  picker.newLabel.textContent = query ? `＋ 新建《${query}》并加入` : '＋ 新建板并加入…';
  boardPickerMove(0, true);
  boardPickerSyncHint();
}

// 键盘高亮：默认落在第一个「点了有用」的行上——上次用的板如果题目全在里面，Enter 不该是空动作。
function boardPickerMove(step, reset = false) {
  const picker = BOARD_PICKER;
  if (!picker) return;
  const nodes = [...picker.options.querySelectorAll('[data-bd-pick]')];
  if (!nodes.length) { picker.active = -1; return; }
  if (reset) {
    const first = nodes.findIndex(node => !node.classList.contains('is-full'));
    picker.active = first >= 0 ? first : 0;
  } else {
    picker.active = (picker.active + step + nodes.length) % nodes.length;
  }
  nodes.forEach((node, index) => node.classList.toggle('keyboard-active', index === picker.active));
  const current = nodes[picker.active];
  current?.scrollIntoView?.({ block: 'nearest' });
  if (current) picker.search.setAttribute('aria-activedescendant', current.dataset.bdPick);
  picker.options.querySelectorAll('.check').forEach(node => {
    const option = node.closest('[data-bd-pick]');
    if (option.classList.contains('is-added') || option.classList.contains('is-full')) return;
    node.textContent = option.classList.contains('keyboard-active') ? '↵' : '';
  });
}

function boardPickerSyncHint() {
  const picker = BOARD_PICKER;
  if (!picker) return;
  const count = picker.added.size;
  picker.hint.innerHTML = count
    ? `已加入 <b>${count}</b> 个板 · ⌘ 点击撤回`
    : 'Enter 加入 · Esc 关闭 · ⌘ 连加';
}

function boardPickerPlace(anchor) {
  const picker = BOARD_PICKER;
  const box = picker.node;
  if (!anchor?.getBoundingClientRect) { box.classList.add('centered'); return; }
  box.classList.remove('centered');
  const rect = anchor.getBoundingClientRect();
  const width = box.offsetWidth || 318;
  const height = box.offsetHeight || 340;
  const left = Math.max(10, Math.min(window.innerWidth - width - 10, rect.left));
  let top = rect.bottom + 6;
  if (top + height > window.innerHeight - 10) top = Math.max(10, rect.top - height - 6);
  box.style.left = `${left}px`;
  box.style.top = `${top}px`;
}

async function boardPickerCommit(board, additive) {
  const picker = BOARD_PICKER;
  if (!picker) return;
  const state = boardPickerRowState(board, picker.uids);
  // 全部已在板中：点击不重复加入，改为打开这个板
  if (state.kind === 'full' && !picker.added.has(board.id)) {
    boardPickerClose();
    if (typeof switchTab === 'function') switchTab('board');
    boardLoad(board.id);
    return;
  }
  // ⌘ 点已加过的行 = 撤回这次加进去的那些题（只撤本次会话加的，不动板里原有的）
  if (additive && picker.added.has(board.id)) {
    const undo = picker.added.get(board.id);
    picker.added.delete(board.id);
    try {
      await boardPost('/api/board/items/remove', { id: board.id, uids: undo });
      await boardPickerRefresh();
    } catch (error) {
      picker.added.set(board.id, undo);
      uiToast(`撤回失败：${error.message}`, { kind: 'error' });
    }
    return;
  }
  const uids = state.pending.length ? state.pending : picker.uids;
  if (picker.moveFrom && picker.moveFrom !== board.id) {
    try { await boardPost('/api/board/items/remove', { id: picker.moveFrom, uids: picker.uids }); } catch (error) {}
  }
  picker.touched = true;
  if (additive) {
    picker.added.set(board.id, uids);
    const result = await boardAddToBoard(board.id, uids, { silent: true });
    if (!result) picker.added.delete(board.id);
    await boardPickerRefresh();
    return;
  }
  const from = picker.moveFrom ? (picker.boards.find(item => item.id === picker.moveFrom)?.name || '') : '';
  boardPickerClose();
  await boardAddToBoard(board.id, uids, { moveFromName: from });
}

async function boardPickerRefresh() {
  const picker = BOARD_PICKER;
  if (!picker) return;
  try {
    const result = await api('/api/boards');
    if (!BOARD_PICKER) return;
    BOARD_DATA = result.boards || [];
    BOARD_FOLDERS = result.folders || [];
    picker.boards = BOARD_DATA.filter(board => board.id !== picker.exclude);
    picker.folders = BOARD_FOLDERS;
    boardPickerRender();
  } catch (error) {}
}

async function boardPickerNew() {
  const picker = BOARD_PICKER;
  if (!picker) return;
  const uids = [...picker.uids];
  const seed = picker.search.value.trim();
  const folders = picker.folders;
  const current = picker.folderHint || '';
  boardPickerClose();
  const res = await uiDialog({
    title: `新建展示板${uids.length ? ` · ${uids.length} 道题` : ''}`,
    okText: '新建并加入',
    body: `<input class="input" id="bd-new-name" value="${escapeAttr(seed)}" placeholder="如：考前速览·三角函数" maxlength="120">
      ${folders.length ? `<label class="bd-new-folder">放进<select class="input" id="bd-new-folder">
        ${folders.map(folder => `<option value="${escapeAttr(folder.id)}" ${folder.id === current ? 'selected' : ''}>${escapeHtml(folder.name)}</option>`).join('')}
        <option value="" ${current ? '' : 'selected'}>未归档</option></select></label>` : ''}`,
    hint: '板名只在系统内使用，纸面标题固定为「错题集」。',
    focus: '#bd-new-name',
  });
  if (!res.ok) return;
  const name = String(res.values['bd-new-name'] || '').trim();
  if (!name) return;
  try {
    const created = await boardPost('/api/board/create', { name, uids, folder_id: res.values['bd-new-folder'] ?? current });
    boardRemember(created.board.id);
    BOARD_DETAIL = created.board;
    await boardReloadData();
    uiToast(`已新建《${name}》${uids.length ? `，加入 ${created.board.items.length} 题` : ''}`);
  } catch (error) { uiToast(`新建展示板失败：${error.message}`, { kind: 'error' }); }
}

// uids 可以是单个 uid 或数组；anchor 有则锚定弹出，无则居中弱模态（toast 按钮、快捷键都走这条）
async function boardPickerOpen(uids, options = {}) {
  const clean = boardUniqueUids(Array.isArray(uids) ? uids : [uids]);
  if (!clean.length) return;
  if (BOARD_PICKER) { boardPickerClose(); return; }
  if (!BOARD_DATA.length || !BOARD_FOLDERS.length) {
    try {
      const result = await api('/api/boards');
      BOARD_DATA = result.boards || [];
      BOARD_FOLDERS = result.folders || [];
    } catch (error) {}
  }
  // Shift + 点击：跳过浮层直接进上次的板。默认给选择，加速留给显式修饰键，而不是反过来。
  if (options.direct) {
    const target = BOARD_DATA.find(board => board.id === boardLastId()) || BOARD_DATA[0];
    if (target) {
      const board = await boardAddToBoard(target.id, clean, { silent: true });
      if (board) {
        uiToast(`已直接加入《${board.name}》（现共 ${board.items.length} 题）`, {
          actions: [
            { label: '撤销', onClick: () => boardPost('/api/board/items/remove', { id: board.id, uids: clean }).then(boardReloadData).then(() => uiToast('已撤销加入')) },
            { label: '换个板…', onClick: () => boardPickerOpen(clean, { exclude: board.id, moveFrom: board.id }) },
          ],
        });
      }
      return;
    }
  }
  const candidates = BOARD_DATA.filter(board => board.id !== options.exclude);
  if (!candidates.length) {
    // 一个板都没有：不必先弹一个空浮层再让用户点「新建」
    BOARD_PICKER = { uids: clean, search: { value: '' }, folders: BOARD_FOLDERS, folderHint: '' };
    const node = BOARD_PICKER; BOARD_PICKER = null;
    await boardPickerNewFromEmpty(node);
    return;
  }
  const box = document.createElement('div');
  box.className = 'bd-picker-pop';
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-label', options.moveFrom ? '移动到' : '加入展示板');
  const title = options.moveFrom ? '移动到…' : '加入展示板';
  box.innerHTML = `<div class="bd-picker-head"><span>${title}</span><small>${clean.length} 道题</small>
      <button type="button" class="bd-picker-x" data-bd-pick-close aria-label="关闭">✕</button></div>
    <input class="input bd-picker-search" placeholder="搜索板名或文件夹…" autocomplete="off">
    <div class="bd-picker-options" role="listbox" aria-label="展示板"></div>
    <div class="bd-picker-foot"><button type="button" class="btn sm ghost bd-picker-new" data-bd-pick-new>＋ 新建板并加入…</button>
      <span class="hint bd-picker-hint"></span></div>`;
  document.body.appendChild(box);
  BOARD_PICKER = {
    node: box, uids: clean, boards: candidates, folders: BOARD_FOLDERS,
    exclude: options.exclude || '', moveFrom: options.moveFrom || '',
    folderHint: BOARD_DATA.find(board => board.id === boardLastId())?.folder_id || '',
    collapsed: boardFolderCollapsed(), added: new Map(), active: -1, touched: false,
    onDone: options.onDone,
    search: box.querySelector('.bd-picker-search'),
    options: box.querySelector('.bd-picker-options'),
    hint: box.querySelector('.bd-picker-hint'),
    newLabel: box.querySelector('.bd-picker-new'),
    showGroups: BOARD_FOLDERS.length > 0,
  };
  boardPickerPlace(options.anchor);
  boardPickerRender();
  boardPickerPlace(options.anchor);   // 渲染出高度后再定一次，避免贴着视口底部时翻转失准

  const picker = BOARD_PICKER;
  picker.onReflow = () => boardPickerPlace(options.anchor);
  // uiDialog 在 capture 阶段吃 Escape；这里必须同样 capture + stopPropagation，否则先关的是底层 Modal
  picker.onKey = event => {
    if (!BOARD_PICKER) return;
    if (event.key === 'Escape') { event.stopPropagation(); event.preventDefault(); boardPickerClose(); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault(); event.stopPropagation();
      boardPickerMove(event.key === 'ArrowDown' ? 1 : -1);
      return;
    }
    if (event.key === 'Enter') {
      event.preventDefault(); event.stopPropagation();
      picker.options.querySelectorAll('[data-bd-pick]')[picker.active]?.click();
      return;
    }
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      const active = picker.options.querySelectorAll('[data-bd-pick]')[picker.active];
      const group = active?.previousElementSibling?.closest?.('[data-bd-pick-fold]')
        || [...picker.options.querySelectorAll('[data-bd-pick-fold]')].filter(node => node.compareDocumentPosition(active || node) & Node.DOCUMENT_POSITION_FOLLOWING).pop();
      if (group?.dataset.bdPickFold) { event.preventDefault(); boardFolderToggle(group.dataset.bdPickFold, event.key === 'ArrowLeft' ? true : false); boardPickerRender(); }
      return;
    }
    // 焦点没在搜索框时（触屏不自动聚焦）也能直接打字过滤
    if (event.key.length === 1 && document.activeElement !== picker.search) picker.search.focus();
  };
  picker.onOutside = event => {
    if (BOARD_PICKER && !box.contains(event.target) && !document.querySelector('.modal-overlay.open')) boardPickerClose();
  };
  document.addEventListener('keydown', picker.onKey, true);
  window.addEventListener('resize', picker.onReflow);
  window.addEventListener('scroll', picker.onReflow, true);
  setTimeout(() => document.addEventListener('click', picker.onOutside, true), 0);
  box.addEventListener('input', () => boardPickerRender());
  box.addEventListener('click', async event => {
    if (event.target.closest('[data-bd-pick-close]')) { boardPickerClose(); return; }
    if (event.target.closest('[data-bd-pick-new]')) { boardPickerNew(); return; }
    const fold = event.target.closest('[data-bd-pick-fold]');
    if (fold) { boardFolderToggle(fold.dataset.bdPickFold); boardPickerRender(); return; }
    const option = event.target.closest('[data-bd-pick]');
    if (!option) return;
    const board = picker.boards.find(item => item.id === option.dataset.bdPick);
    if (board) await boardPickerCommit(board, event.metaKey || event.ctrlKey);
  });
  // 板少时不抢焦点去逼用户打字；触屏一律不自动聚焦，免得弹起软键盘挡住列表
  const coarse = window.matchMedia?.('(pointer: coarse)')?.matches;
  if (!coarse) requestAnimationFrame(() => picker.search.focus({ preventScroll: true }));
}

async function boardPickerNewFromEmpty(context) {
  const name = await uiPrompt('新建展示板', '', { placeholder: '如：考前速览·三角函数', hint: '还没有板，先建一个；板名只在系统内使用。' });
  if (!name) return;
  try {
    const created = await boardPost('/api/board/create', { name, uids: context.uids });
    boardRemember(created.board.id);
    BOARD_DETAIL = created.board;
    await boardReloadData();
    uiToast(`已新建《${name}》，加入 ${created.board.items.length} 题`);
  } catch (error) { uiToast(`新建展示板失败：${error.message}`, { kind: 'error' }); }
}

// 旧名保留成薄封装：调用点与既有测试不动
function boardQuickAdd(uid, options = {}) { return boardPickerOpen(uid, options); }
function boardChooseAndAdd(uids, options = {}) { return boardPickerOpen(uids, options); }


if (typeof module !== 'undefined') module.exports = {
  boardFolderTree, boardPickerRowState, boardPickerFilter, boardPickerRecent,
};
