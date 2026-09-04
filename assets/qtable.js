// === assets/qtable.js — 题库抽屉、批量操作、列设置、视图预设与快捷键 ===
let QB_SELECTED = new Set();
let QB_DENSITY = 'comfortable';
let QB_VISIBLE_COLUMNS = null;
let QB_CURSOR_UID = '';
const QB_VIEW_KEY = 'omrs-question-views';
const QB_DEFAULT_COLUMNS = ['select', 'main', 'labels', 'mastery', 'due', 'status', 'actions'];
const QB_EXTRA_COLUMNS = [
  ['difficulty', '难度'],
  ['decayed', '衰减后'],
  ['attempts', '次数'],
  ['last_review', '上次复习'],
  ['ef', 'EF'],
];

function qbReadPrefs() {
  try {
    QB_DENSITY = localStorage.getItem('omrs-qb-density') || 'comfortable';
    const raw = localStorage.getItem('omrs-qb-columns');
    QB_VISIBLE_COLUMNS = raw ? JSON.parse(raw) : null;
    if (!Array.isArray(QB_VISIBLE_COLUMNS)) QB_VISIBLE_COLUMNS = null;
  } catch (error) {
    QB_DENSITY = 'comfortable';
    QB_VISIBLE_COLUMNS = null;
  }
}

function qbVisibleColumns() {
  const values = new Set(Array.isArray(QB_VISIBLE_COLUMNS) ? QB_VISIBLE_COLUMNS : QB_DEFAULT_COLUMNS);
  values.add('main');
  return values;
}

function qbRenderControls() {
  const columns = qbVisibleColumns();
  document.querySelectorAll('[data-qb-column]').forEach(node => {
    node.checked = columns.has(node.dataset.qbColumn);
    node.disabled = node.dataset.qbColumn === 'main';
  });
  document.querySelectorAll('[data-qb-density]').forEach(node => {
    node.classList.toggle('on', node.dataset.qbDensity === QB_DENSITY);
  });
  qbRenderViews();
}

function qbToggleDrawer(force) {
  const wrap = document.getElementById('qb-wrap');
  if (!wrap) return;
  const next = force == null ? !wrap.classList.contains('drawer') : !!force;
  wrap.classList.toggle('drawer', next);
}

function qbFilterValues() {
  const filters = getFilterState('q');
  return filters;
}

function qbFilterCount(filters = qbFilterValues()) {
  return [
    filters.subject, filters.category, filters.tag, filters.knowledgeTag,
    ...(filters.labels || []),
    filters.dueFilter, filters.suspended,
    filters.masteryMin != null ? 'mastery-min' : '',
    filters.masteryMax != null ? 'mastery-max' : '',
    filters.difficultyMin > 0 ? 'difficulty-min' : '',
    filters.difficultyMax < 10 ? 'difficulty-max' : '',
    filters.text,
  ].filter(Boolean).length;
}

function qbFilterDisplayState() {
  const fields = ['q-filter-due', 'q-filter-suspended'];
  return fields.some(id => {
    const el = document.getElementById(id);
    return el && el.value;
  });
}

function qbRenderSummary(items, filters) {
  const all = getItems();
  const count = document.getElementById('qb-counts');
  const badge = document.getElementById('qb-filter-badge');
  if (badge) {
    const n = qbFilterCount(filters);
    badge.textContent = n;
    badge.style.display = n ? 'inline-flex' : 'none';
  }
  if (count) {
    const overdue = all.filter(item => getDueDays(item) != null && getDueDays(item) < 0).length;
    const leech = all.filter(item => item.is_leech).length;
    const suspended = all.filter(item => item.suspended).length;
    count.innerHTML = `<span>逾期 <b>${overdue}</b></span><span>待攻克 <b>${all.filter(item => (item.tag || '').includes('待攻克') && !item.suspended).length}</b></span><span>顽固题 <b>${leech}</b></span><span>停用 <b>${suspended}</b></span><span class="grow"></span><span>共 <b>${all.length}</b> 题 / 显示 <b>${items.length}</b></span>`;
  }
}

function qbLabel(text, value, type = 'field') {
  const safe = escapeHtml(text);
  return `<button type="button" class="qb-chip" data-qb-clear="${escapeAttr(type)}" data-qb-value="${escapeAttr(value || '')}">${safe} <span class="x">✕</span></button>`;
}

function qbRenderChips(filters = qbFilterValues()) {
  const box = document.getElementById('qb-chips');
  if (!box) return;
  const chips = [];
  if (filters.text) chips.push(qbLabel(`搜索：${filters.text}`, 'q-search', 'id'));
  if (filters.subject) chips.push(qbLabel(`科目：${filters.subject}`, 'q-filter-subj', 'id'));
  if (filters.category) chips.push(qbLabel(`分类：${filters.category}`, 'q-filter-category', 'id'));
  if (filters.tag) chips.push(qbLabel(`状态：${filters.tag}`, 'q-filter-tag', 'id'));
  if (filters.knowledgeTag) chips.push(qbLabel(`知识点：${filters.knowledgeTag}`, 'q-filter-ktag', 'id'));
  (filters.labels || []).forEach(label => chips.push(qbLabel(`标记：${label}`, label, 'label')));
  if (filters.dueFilter) chips.push(qbLabel(`到期：${filters.dueFilter}`, 'q-filter-due', 'id'));
  if (filters.suspended) chips.push(qbLabel(`题目：${filters.suspended}`, 'q-filter-suspended', 'id'));
  if (filters.difficultyMin > 1) chips.push(qbLabel(`难度 ≥ ${filters.difficultyMin}`, 'q-filter-diff-min', 'id'));
  if (filters.difficultyMax < 10) chips.push(qbLabel(`难度 ≤ ${filters.difficultyMax}`, 'q-filter-diff-max', 'id'));
  if (filters.masteryMin != null) chips.push(qbLabel(`熟练度 ≥ ${Math.round(filters.masteryMin * 100)}%`, 'q-filter-mastery-min', 'id'));
  if (filters.masteryMax != null) chips.push(qbLabel(`熟练度 ≤ ${Math.round(filters.masteryMax * 100)}%`, 'q-filter-mastery-max', 'id'));
  box.innerHTML = chips.length ? `${chips.join('')}<button type="button" class="btn sm ghost" data-qb-clear="all">清空</button>` : '<span class="hint">未设置高级筛选</span>';
}

function qbResetFilters() {
  ['q-search', 'q-filter-subj', 'q-filter-category', 'q-filter-tag', 'q-filter-ktag',
    'q-filter-due', 'q-filter-suspended', 'q-filter-diff-min', 'q-filter-diff-max',
    'q-filter-mastery-min', 'q-filter-mastery-max'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const mode = document.getElementById('q-label-mode');
  if (mode) mode.value = 'any';
  setSelectedLabelNames([]);
  document.querySelectorAll('[data-qb-menu].open').forEach(node => node.classList.remove('open'));
  renderQ();
}

function qbClearChip(type, value) {
  if (type === 'all') { qbResetFilters(); return; }
  if (type === 'label') {
    setSelectedLabelNames(selectedLabelNames().filter(label => label !== value));
  } else {
    const el = document.getElementById(value);
    if (el) el.value = '';
  }
  renderQ();
}

function qbUpdateBatchBar() {
  const bar = document.getElementById('qb-batchbar');
  const count = document.getElementById('qb-selected-count');
  if (bar) bar.style.display = QB_SELECTED.size ? 'flex' : 'none';
  if (count) count.textContent = QB_SELECTED.size;
  const all = document.getElementById('qb-select-all');
  const visible = filterItems(getItems(), getFilterState('q'));
  if (all) {
    all.checked = visible.length > 0 && visible.every(item => QB_SELECTED.has(item.uid));
    all.indeterminate = visible.some(item => QB_SELECTED.has(item.uid)) && !all.checked;
  }
}

function qbSelect(uid, checked) {
  if (checked) QB_SELECTED.add(uid); else QB_SELECTED.delete(uid);
  qbUpdateBatchBar();
}

function qbSelectAll(checked) {
  const visible = filterItems(getItems(), getFilterState('q'));
  visible.forEach(item => checked ? QB_SELECTED.add(item.uid) : QB_SELECTED.delete(item.uid));
  renderQ();
}

function qbClearSelection() {
  QB_SELECTED.clear();
  renderQ();
}

async function qbBatchBoard() {
  const uids = [...QB_SELECTED];
  if (!uids.length) return;
  if (typeof qbChooseBoardForUids === 'function') {
    await qbChooseBoardForUids(uids);
  } else if (typeof boardAddUids === 'function') {
    await boardAddUids(uids);
  }
}

async function qbBatchLabels() {
  const uids = [...QB_SELECTED];
  if (!uids.length) return;
  const modal = document.createElement('div');
  modal.className = 'modal-overlay open';
  modal.id = 'qb-label-modal';
  const selectedAdd = new Set();
  const selectedRemove = new Set();
  const names = LABELS.filter(label => !label.archived);
  modal.innerHTML = `<div class="modal qb-label-modal">
    <div class="modal-close" data-qb-label-close>✕</div>
    <h2>批量编辑标记</h2>
    <div class="hint">已选 ${uids.length} 道题。分别勾选要添加或移除的标记，完成后一次保存。</div>
    <div class="qb-label-section"><strong>添加标记</strong><div class="qb-label-options" data-qb-label-add>
      ${names.map(label => `<label><input type="checkbox" data-qb-label-add-name="${escapeAttr(label.name)}"> ${lblChip(label)}</label>`).join('') || '<span class="hint">暂无标记</span>'}
    </div></div>
    <div class="qb-label-section"><strong>移除标记</strong><div class="qb-label-options" data-qb-label-remove>
      ${names.map(label => `<label><input type="checkbox" data-qb-label-remove-name="${escapeAttr(label.name)}"> ${lblChip(label)}</label>`).join('') || '<span class="hint">暂无标记</span>'}
    </div></div>
    <div class="qb-label-foot"><button class="btn" data-qb-label-close>取消</button><button class="btn primary" data-qb-label-save>完成</button></div>
  </div>`;
  document.body.appendChild(modal);
  const close = () => modal.remove();
  modal.addEventListener('change', event => {
    const add = event.target.closest('[data-qb-label-add-name]');
    const remove = event.target.closest('[data-qb-label-remove-name]');
    if (add) add.checked ? selectedAdd.add(add.dataset.qbLabelAddName) : selectedAdd.delete(add.dataset.qbLabelAddName);
    if (remove) remove.checked ? selectedRemove.add(remove.dataset.qbLabelRemoveName) : selectedRemove.delete(remove.dataset.qbLabelRemoveName);
  });
  modal.addEventListener('click', async event => {
    if (event.target === modal || event.target.closest('[data-qb-label-close]')) { close(); return; }
    if (!event.target.closest('[data-qb-label-save]')) return;
    if (!selectedAdd.size && !selectedRemove.size) { close(); return; }
    const add = [...selectedAdd], remove = [...selectedRemove];
    try {
      await batchAddRemoveLabels(uids, add, remove);
      QB_SELECTED.clear();
      close();
    } catch (error) {
      alert(`批量保存标记失败：${error.message}`);
    }
  });
}

async function qbBatchSuspend() {
  const uids = [...QB_SELECTED];
  if (!uids.length) return;
  for (const uid of uids) {
    const item = getItemByUid(uid);
    if (!item) continue;
    try {
      await api(item.suspended ? '/api/question/resume' : '/api/question/suspend', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ uid }),
      });
    } catch (error) { /* keep going, final reload shows failures */ }
  }
  QB_SELECTED.clear();
  await reloadData();
}

async function qbBatchExport() {
  const uids = [...QB_SELECTED];
  if (!uids.length) return;
  const response = await fetch('/api/export', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uids, format: 'a4', include_answers: false }),
  });
  if (!response.ok) { alert('导出失败'); return; }
  await downloadExportResponse(response, 'OMRS-题库筛选-a4.html', 'qb-counts');
}

function qbRenderDensity() {
  document.getElementById('q-table-wrap')?.classList.toggle('qb-compact', QB_DENSITY === 'compact');
}

function qbToggleDensity(value) {
  QB_DENSITY = value === 'compact' ? 'compact' : 'comfortable';
  try { localStorage.setItem('omrs-qb-density', QB_DENSITY); } catch (error) {}
  renderQ();
}

function qbToggleColumn(key) {
  const visible = qbVisibleColumns();
  if (visible.has(key)) visible.delete(key); else visible.add(key);
  qbSetColumnVisibility(key, visible.has(key));
}

function qbSetColumnVisibility(key, checked) {
  const visible = qbVisibleColumns();
  if (checked) visible.add(key); else visible.delete(key);
  if (!visible.has('main')) visible.add('main');
  QB_VISIBLE_COLUMNS = [...visible];
  try { localStorage.setItem('omrs-qb-columns', JSON.stringify(QB_VISIBLE_COLUMNS)); } catch (error) {}
  renderQ();
}

function qbApplyView(name) {
  let views = {};
  try { views = JSON.parse(localStorage.getItem(QB_VIEW_KEY) || '{}'); } catch (error) {}
  const view = views[name];
  if (!view) return;
  Object.entries(view.fields || {}).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  });
  setSelectedLabelNames(view.labels || []);
  if (view.view) Q_VIEW = view.view;
  if (Array.isArray(view.columns)) QB_VISIBLE_COLUMNS = view.columns;
  if (view.density) QB_DENSITY = view.density === 'compact' ? 'compact' : 'comfortable';
  try {
    localStorage.setItem('omrs-qb-columns', JSON.stringify(QB_VISIBLE_COLUMNS));
    localStorage.setItem('omrs-qb-density', QB_DENSITY);
  } catch (error) {}
  renderQ();
}

function qbSaveView() {
  const name = prompt('视图名称', '考前必看');
  if (!name) return;
  let views = {};
  try { views = JSON.parse(localStorage.getItem(QB_VIEW_KEY) || '{}'); } catch (error) {}
  const ids = ['q-search', 'q-filter-subj', 'q-filter-category', 'q-filter-tag', 'q-filter-ktag',
    'q-filter-due', 'q-filter-suspended', 'q-filter-diff-min', 'q-filter-diff-max',
    'q-filter-mastery-min', 'q-filter-mastery-max', 'q-label-mode', 'q-sort'];
  views[name.trim()] = {
    fields: Object.fromEntries(ids.map(id => [id, document.getElementById(id)?.value || ''])),
    labels: selectedLabelNames(),
    view: Q_VIEW,
    columns: [...qbVisibleColumns()],
    density: QB_DENSITY,
  };
  try { localStorage.setItem(QB_VIEW_KEY, JSON.stringify(views)); } catch (error) {}
  alert(`已保存视图「${name.trim()}」`);
}

function qbRenderViews() {
  const box = document.getElementById('qb-view-menu');
  if (!box) return;
  let views = {};
  try { views = JSON.parse(localStorage.getItem(QB_VIEW_KEY) || '{}'); } catch (error) {}
  box.innerHTML = Object.keys(views).map(name => `<button type="button" data-qb-view="${escapeAttr(name)}">${escapeHtml(name)}</button>`).join('');
}

function qbManageViews() {
  let views = {};
  try { views = JSON.parse(localStorage.getItem(QB_VIEW_KEY) || '{}'); } catch (error) {}
  const names = Object.keys(views);
  if (!names.length) {
    alert('还没有保存的视图');
    return;
  }
  const modal = document.createElement('div');
  modal.className = 'modal-overlay open';
  modal.innerHTML = `<div class="modal qb-view-modal">
    <div class="modal-close" data-qb-view-close>✕</div>
    <h2>管理题库视图</h2>
    <div class="qb-view-manager-list">${names.map(name => `<div class="qb-view-manager-row"><span>${escapeHtml(name)}</span><button type="button" class="btn sm danger" data-qb-view-delete="${escapeAttr(name)}">删除</button></div>`).join('')}</div>
    <div class="qb-view-modal-foot"><button type="button" class="btn" data-qb-view-close>关闭</button></div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', event => {
    if (event.target === modal || event.target.closest('[data-qb-view-close]')) {
      modal.remove();
      return;
    }
    const remove = event.target.closest('[data-qb-view-delete]');
    if (!remove) return;
    const name = remove.dataset.qbViewDelete;
    if (!confirm(`删除视图「${name}」？`)) return;
    let current = {};
    try { current = JSON.parse(localStorage.getItem(QB_VIEW_KEY) || '{}'); } catch (error) {}
    delete current[name];
    try { localStorage.setItem(QB_VIEW_KEY, JSON.stringify(current)); } catch (error) {}
    remove.closest('.qb-view-manager-row')?.remove();
    qbRenderViews();
  });
}

function qbHandleKey(event) {
  const panel = document.getElementById('panel-questions');
  if (!panel?.classList.contains('active')) return;
  if (event.target.closest?.('input,textarea,select,button')) return;
  const visible = filterItems(getItems(), getFilterState('q'));
  const cursorIndex = visible.findIndex(item => item.uid === QB_CURSOR_UID);
  if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
    event.preventDefault();
    if (!visible.length) return;
    const delta = event.key === 'ArrowUp' ? -1 : 1;
    const next = cursorIndex < 0
      ? (delta > 0 ? 0 : visible.length - 1)
      : Math.max(0, Math.min(visible.length - 1, cursorIndex + delta));
    QB_CURSOR_UID = visible[next].uid;
    renderQ();
    const row = [...document.querySelectorAll('[data-q-row]')].find(node => node.dataset.qRow === QB_CURSOR_UID);
    row?.scrollIntoView?.({ block: 'nearest' });
  } else if (event.key === ' ') {
    event.preventDefault();
    const current = visible[cursorIndex < 0 ? 0 : cursorIndex];
    if (current) {
      QB_CURSOR_UID = current.uid;
      qbSelect(current.uid, !QB_SELECTED.has(current.uid));
      renderQ();
    }
  } else if (event.key === 'Enter') {
    event.preventDefault();
    const current = visible[cursorIndex < 0 ? 0 : cursorIndex];
    if (current && typeof viewQ === 'function') viewQ(current.uid, 'q');
  } else if (event.key === '/') { event.preventDefault(); document.getElementById('q-search')?.focus(); }
  else if (event.key.toLowerCase() === 'f') qbToggleDrawer();
  else if (event.key.toLowerCase() === 'v') setQView(Q_VIEW === 'table' ? 'gallery' : 'table');
  else if (event.key === 'Escape') qbClearSelection();
  else if (event.key.toLowerCase() === 'b') qbBatchBoard();
  else if (event.key.toLowerCase() === 'l') qbBatchLabels();
}

document.addEventListener('click', event => {
  const clear = event.target.closest?.('[data-qb-clear]');
  if (clear) { qbClearChip(clear.dataset.qbClear, clear.dataset.qbValue); return; }
  const view = event.target.closest?.('[data-qb-view]');
  if (view) qbApplyView(view.dataset.qbView);
  const density = event.target.closest?.('[data-qb-density]');
  if (density) qbToggleDensity(density.dataset.qbDensity);
  const menuToggle = event.target.closest?.('[data-qb-menu-toggle]');
  if (menuToggle) {
    event.stopPropagation();
    const name = menuToggle.dataset.qbMenuToggle;
    document.querySelectorAll('[data-qb-menu].open').forEach(node => {
      if (node.dataset.qbMenu !== name) node.classList.remove('open');
    });
    [...document.querySelectorAll('[data-qb-menu]')].find(node => node.dataset.qbMenu === name)?.classList.toggle('open');
  }
  const saveView = event.target.closest?.('[data-qb-view-save]');
  if (saveView) { qbSaveView(); return; }
  const manageViews = event.target.closest?.('[data-qb-view-manage]');
  if (manageViews) { qbManageViews(); return; }
});
document.addEventListener('change', event => {
  const column = event.target.closest?.('[data-qb-column]');
  if (column) qbSetColumnVisibility(column.dataset.qbColumn, column.checked);
});
document.addEventListener('click', event => {
  if (!event.target.closest?.('[data-qb-menu-toggle],[data-qb-menu]')) {
    document.querySelectorAll('[data-qb-menu].open').forEach(node => node.classList.remove('open'));
  }
});
document.addEventListener('keydown', qbHandleKey);
qbReadPrefs();

if (typeof module !== 'undefined') module.exports = {
  qbFilterCount, qbClearChip, qbApplyView, qbSaveView,
  qbToggleDensity, qbToggleColumn, qbVisibleColumns,
};
