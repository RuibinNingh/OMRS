// === assets/qtable.js — 题库新壳：筛选抽屉、计数条、激活 chips、列/密度、视图预设、批量条、快捷键 ===
// 表格 / 画廊本身仍由 questions.js 渲染（renderQ / filterQ / setQView 签名不变）；
// 本文件只负责「围绕列表的壳」。筛选控件沿用 q-filter-* id，getFilterState('q') 契约不变。
let QB_SELECTED = new Set();
let QB_DENSITY = 'comfortable';
let QB_GALLERY_DETAIL = false;              // 画廊卡是否展开元数据行，默认精简
let QB_GALLERY_COLS = 0;                    // 画廊列数：0 = 自动（按卡片最小宽度铺满），1–6 = 固定列数
let QB_MD_MODE = 'lean';                    // 题面换行：lean = 忽略单个换行（当前默认）/ full = 原文每处换行都保留
let QB_VISIBLE_COLUMNS = null;
let QB_CURSOR_UID = '';
let QB_QUICK = '';                                 // 计数条快捷筛选：overdue | attack | leech | suspended
const QB_VIEW_KEY = 'omrs-question-views';
const QB_DEFAULT_COLUMNS = ['select', 'main', 'labels', 'mastery', 'due', 'status', 'actions'];
const QB_FILTER_IDS = ['q-search', 'q-filter-subj', 'q-filter-category', 'q-filter-tag', 'q-filter-ktag',
  'q-filter-due', 'q-filter-suspended', 'q-filter-diff-min', 'q-filter-diff-max',
  'q-filter-mastery-min', 'q-filter-mastery-max', 'q-label-mode', 'q-sort'];
const QB_FILTER_DEFAULTS = { 'q-filter-diff-min': '1', 'q-filter-diff-max': '10', 'q-filter-mastery-min': '0', 'q-filter-mastery-max': '100', 'q-label-mode': 'any', 'q-sort': 'mastery-asc' };
const QB_DUE_LABELS = { overdue: '逾期', today: '今日到期', '3days': '3 天内到期', '7days': '7 天内到期', future: '未到期' };
const QB_SUSPENDED_LABELS = { suspended: '仅停用题目', all: '含停用题目' };

function qbReadPrefs() {
  try {
    QB_DENSITY = localStorage.getItem('omrs-qb-density') === 'compact' ? 'compact' : 'comfortable';
    QB_GALLERY_DETAIL = localStorage.getItem('omrs-qb-gallery-detail') === '1';
    QB_GALLERY_COLS = qbClampCols(localStorage.getItem('omrs-qb-gallery-cols'));
    QB_MD_MODE = localStorage.getItem('omrs-qb-md-mode') === 'full' ? 'full' : 'lean';
    const raw = localStorage.getItem('omrs-qb-columns');
    QB_VISIBLE_COLUMNS = raw ? JSON.parse(raw) : null;
    if (!Array.isArray(QB_VISIBLE_COLUMNS)) QB_VISIBLE_COLUMNS = null;
  } catch (error) {
    QB_DENSITY = 'comfortable';
    QB_GALLERY_DETAIL = false;
    QB_GALLERY_COLS = 0;
    QB_MD_MODE = 'lean';
    QB_VISIBLE_COLUMNS = null;
  }
}
function qbClampCols(value) { const n = Math.round(Number(value)); return Number.isFinite(n) ? Math.max(0, Math.min(6, n)) : 0; }
// 当前视图：菜单据此只显示与该视图有关的那一组开关（表格 = 列 + 行密度，画廊 = 列数 + 卡片密度）
function qbCurrentView() { return (typeof Q_VIEW !== 'undefined' && Q_VIEW === 'gallery') ? 'gallery' : 'table'; }
function qbVisibleColumns() {
  const values = new Set(Array.isArray(QB_VISIBLE_COLUMNS) ? QB_VISIBLE_COLUMNS : QB_DEFAULT_COLUMNS);
  values.add('main'); values.add('select'); values.add('actions');
  return values;
}
function qbFieldValue(id) { return document.getElementById(id)?.value ?? ''; }
function qbSetField(id, value) { const el = document.getElementById(id); if (el) el.value = value; }

// ---------- 当前筛选的可视化（chips + 徽标 + 抽屉命中数） ----------
// 与 getFilterState('q') 的区别：只关心「用户设了什么」，滑块处于两端 / 下拉为空都算未设。
function qbActiveFilters(filters = getFilterState('q')) {
  const active = [];
  if (filters.text) active.push({ id: 'q-search', label: `搜索：${filters.text}` });
  if (filters.subject) active.push({ id: 'q-filter-subj', label: `科目：${filters.subject}` });
  if (filters.category) active.push({ id: 'q-filter-category', label: `分类：${filters.category}` });
  if (filters.knowledgeTag) active.push({ id: 'q-filter-ktag', label: `知识点：${filters.knowledgeTag}` });
  (filters.labels || []).forEach(label => active.push({ label: '', chip: label, kind: 'label', value: label }));
  if ((filters.labels || []).length > 1 && filters.labelMode === 'all') active.push({ id: 'q-label-mode', label: '标记：全部命中', reset: 'any' });
  if (filters.difficultyMin > 1 || (filters.difficultyMax || 10) < 10) active.push({ kind: 'diff', label: `难度 ${filters.difficultyMin}–${filters.difficultyMax || 10}` });
  const mMin = filters.masteryMin == null ? 0 : filters.masteryMin, mMax = filters.masteryMax == null ? 1 : filters.masteryMax;
  if (mMin > 0 || mMax < 1) active.push({ kind: 'mastery', label: `熟练度 ${Math.round(mMin * 100)}–${Math.round(mMax * 100)}%` });
  if (filters.dueFilter) active.push({ id: 'q-filter-due', label: `到期：${QB_DUE_LABELS[filters.dueFilter] || filters.dueFilter}` });
  if (filters.tag) active.push({ id: 'q-filter-tag', label: `状态：${filters.tag === '易错' ? '易错坑' : filters.tag}` });
  if (filters.suspended) active.push({ id: 'q-filter-suspended', label: `题目：${QB_SUSPENDED_LABELS[filters.suspended] || filters.suspended}` });
  return active;
}
function qbFilterCount(filters) { return qbActiveFilters(filters).length; }

function qbRenderSummary(items, filters) {
  const all = getItems();
  const badge = document.getElementById('qb-filter-badge');
  if (badge) {
    const n = qbFilterCount(filters);
    badge.textContent = n;
    badge.style.display = n ? 'inline-flex' : 'none';
  }
  const match = document.getElementById('qb-match-count');
  if (match) match.textContent = items.length;
  const count = document.getElementById('qb-counts');
  if (!count) return;
  const active = all.filter(item => !item.suspended);
  const overdue = active.filter(item => { const d = getDueDays(item); return d != null && d < 0; }).length;
  const attack = active.filter(item => (item.tag || '').includes('待攻克')).length;
  const leech = active.filter(item => item.is_leech).length;
  const suspended = all.length - active.length;
  const quick = (key, label, n, cls) => `<button type="button" class="qb-quick ${cls || ''} ${QB_QUICK === key ? 'on' : ''}" data-qb-quick="${key}" title="点击筛选">${label} <b>${n}</b></button>`;
  count.innerHTML = quick('overdue', '逾期', overdue, overdue ? 'red' : '') + quick('attack', '待攻克', attack) + quick('leech', '顽固题', leech, leech ? 'yellow' : '') + quick('suspended', '停用', suspended)
    + `<span class="qb-total">共 <b>${all.length}</b> 题 · 显示 <b>${items.length}</b>${QB_SELECTED.size ? ` · 已选 <b>${QB_SELECTED.size}</b>` : ''}</span>`;
}
function qbRenderChips(filters = getFilterState('q')) {
  const box = document.getElementById('qb-chips');
  if (!box) return;
  const active = qbActiveFilters(filters);
  const chip = entry => {
    const data = entry.kind === 'label' ? `data-qb-clear="label" data-qb-value="${escapeAttr(entry.value)}"`
      : entry.kind ? `data-qb-clear="${entry.kind}"` : `data-qb-clear="id" data-qb-value="${escapeAttr(entry.id)}" data-qb-reset="${escapeAttr(entry.reset || '')}"`;
    const body = entry.chip ? lblChip(entry.chip) : escapeHtml(entry.label);
    return `<button type="button" class="qb-chip" ${data} title="移除该条件">${body}<span class="x">✕</span></button>`;
  };
  if (!active.length) { box.innerHTML = ''; return; }   // 空条件不再占一整行提示文字（`.qb-chips:empty` 收起）
  box.innerHTML = active.map(chip).join('') + `<button type="button" class="btn sm ghost" data-qb-clear="all">清空</button>`;
}
function qbRenderControls() {
  const columns = qbVisibleColumns();
  const view = qbCurrentView();
  document.querySelectorAll('[data-qb-column]').forEach(node => { node.checked = columns.has(node.dataset.qbColumn); });
  document.querySelectorAll('[data-qb-density]').forEach(node => node.classList.toggle('on', node.dataset.qbDensity === QB_DENSITY));
  document.querySelectorAll('[data-qb-cols]').forEach(node => node.classList.toggle('on', qbClampCols(node.dataset.qbCols) === QB_GALLERY_COLS));
  document.querySelectorAll('[data-qb-md]').forEach(node => node.classList.toggle('on', node.dataset.qbMd === QB_MD_MODE));
  document.querySelectorAll('[data-qb-gallery-detail]').forEach(node => { node.checked = QB_GALLERY_DETAIL; });
  // 菜单按当前视图只露相关的一半，免得在画廊里点半天「列设置」却毫无反应
  document.querySelectorAll('[data-qb-menu="columns"]').forEach(node => { node.dataset.view = view; });
  const trigger = document.getElementById('qb-layout-label');
  if (trigger) trigger.textContent = view === 'gallery' ? '列数 / 密度' : '列 / 密度';
  document.querySelectorAll('[data-qb-seg]').forEach(seg => {
    const value = qbFieldValue(seg.dataset.qbSeg);
    seg.querySelectorAll('button').forEach(button => button.classList.toggle('on', (button.dataset.value || '') === value));
  });
  qbSyncDual('diff'); qbSyncDual('mastery');
  qbRenderViews();
}
// 密度对表格和画廊都生效；画廊另外把列数写成 data-cols，由 CSS 决定 grid-template-columns
function qbRenderDensity() {
  const compact = QB_DENSITY === 'compact';
  document.getElementById('q-table-wrap')?.classList.toggle('qb-compact', compact);
  const gallery = document.getElementById('q-gallery-wrap');
  if (!gallery) return;
  gallery.classList.toggle('qb-compact', compact);
  gallery.dataset.cols = QB_GALLERY_COLS ? String(QB_GALLERY_COLS) : 'auto';
}

// ---------- 抽屉 ----------
function qbToggleDrawer(force) {
  const wrap = document.getElementById('qb-wrap');
  if (!wrap) return;
  const next = force == null ? !wrap.classList.contains('drawer') : !!force;
  wrap.classList.toggle('drawer', next);
  document.getElementById('qb-filter-btn')?.classList.toggle('is-on', next);
  if (next) { qbRenderControls(); }
}
// 双滑块：保证 min ≤ max，更新填充条与文案；释放时才重排列表
function qbSyncDual(kind) {
  const minEl = document.getElementById(`q-filter-${kind}-min`), maxEl = document.getElementById(`q-filter-${kind}-max`);
  if (!minEl || !maxEl) return;
  let lo = asNumber(minEl.value, Number(minEl.min)), hi = asNumber(maxEl.value, Number(maxEl.max));
  if (lo > hi) { if (document.activeElement === minEl) { hi = lo; maxEl.value = hi; } else { lo = hi; minEl.value = lo; } }
  const min = Number(minEl.min), max = Number(maxEl.max);
  const fill = document.getElementById(`qb-${kind}-fill`);
  if (fill) { fill.style.left = `${(lo - min) / (max - min) * 100}%`; fill.style.width = `${(hi - lo) / (max - min) * 100}%`; }
  const label = document.getElementById(`qb-${kind}-label`);
  if (label) label.textContent = kind === 'mastery' ? `${lo} – ${hi}%` : `${lo} – ${hi}`;
}
function qbResetFilters(keepSearch = false) {
  QB_FILTER_IDS.forEach(id => { if (keepSearch && id === 'q-search') return; if (id === 'q-sort') return; qbSetField(id, QB_FILTER_DEFAULTS[id] ?? ''); });
  setSelectedLabelNames([]);
  QB_QUICK = '';
  renderQ();
}
function qbClearChip(type, value, reset) {
  if (type === 'all') { qbResetFilters(); return; }
  if (type === 'label') setSelectedLabelNames(selectedLabelNames().filter(label => label !== value));
  else if (type === 'diff') { qbSetField('q-filter-diff-min', '1'); qbSetField('q-filter-diff-max', '10'); }
  else if (type === 'mastery') { qbSetField('q-filter-mastery-min', '0'); qbSetField('q-filter-mastery-max', '100'); }
  else qbSetField(value, reset || QB_FILTER_DEFAULTS[value] || '');
  QB_QUICK = '';
  renderQ();
}
// 计数条快捷筛选：一键切到「逾期 / 待攻克 / 顽固题 / 停用」，再点一次取消
function qbApplyQuick(key) {
  const same = QB_QUICK === key;
  qbResetFilters(true);
  if (same) return;
  QB_QUICK = key;
  if (key === 'overdue') qbSetField('q-filter-due', 'overdue');
  else if (key === 'attack') qbSetField('q-filter-tag', '待攻克');
  else if (key === 'suspended') qbSetField('q-filter-suspended', 'suspended');
  else if (key === 'leech') qbSetField('q-sort', 'mastery-asc');
  renderQ();
}
// 顽固题没有对应筛选字段：由 questions.js 在 filterItems 之后再过一遍
function qbPostFilter(items) {
  if (QB_QUICK === 'leech') return items.filter(item => item.is_leech);
  return items;
}

// ---------- 选择与批量 ----------
function qbUpdateBatchBar() {
  const bar = document.getElementById('qb-batchbar');
  const count = document.getElementById('qb-selected-count');
  if (bar) bar.classList.toggle('show', QB_SELECTED.size > 0);
  if (count) count.textContent = QB_SELECTED.size;
  const all = document.getElementById('qb-select-all');
  if (all) {
    const visible = qbVisibleItems();
    all.checked = visible.length > 0 && visible.every(item => QB_SELECTED.has(item.uid));
    all.indeterminate = !all.checked && visible.some(item => QB_SELECTED.has(item.uid));
  }
  document.querySelectorAll('[data-q-row]').forEach(row => row.classList.toggle('qb-selected', QB_SELECTED.has(row.dataset.qRow)));
}
function qbVisibleItems() { return qbPostFilter(filterItems(getItems(), getFilterState('q'))); }
function qbSelect(uid, checked) {
  if (checked) QB_SELECTED.add(uid); else QB_SELECTED.delete(uid);
  qbUpdateBatchBar();
  const summaryItems = qbVisibleItems();
  qbRenderSummary(summaryItems, getFilterState('q'));
}
function qbSelectAll(checked) {
  qbVisibleItems().forEach(item => checked ? QB_SELECTED.add(item.uid) : QB_SELECTED.delete(item.uid));
  renderQ();
}
function qbClearSelection() { QB_SELECTED.clear(); renderQ(); }
async function qbBatchBoard() {
  const uids = [...QB_SELECTED];
  if (!uids.length) return;
  if (typeof boardChooseAndAdd === 'function') await boardChooseAndAdd(uids);
}
async function qbBatchLabels() {
  const uids = [...QB_SELECTED];
  if (!uids.length) return;
  const names = LABELS.filter(label => !label.archived);
  const modal = document.createElement('div');
  modal.className = 'modal-overlay open';
  modal.innerHTML = `<div class="modal qb-label-modal">
    <div class="modal-close" data-qb-label-close>✕</div>
    <h2 style="font-size:.95rem;font-weight:800;color:var(--accent2);margin:0 0 4px">批量打标记</h2>
    <div class="hint">已选 ${uids.length} 道题。勾选要添加 / 移除的标记，一次保存；没勾的标记保持原样。</div>
    <div class="qb-label-section"><strong>添加</strong><div class="qb-label-options">${names.map(label => `<label><input type="checkbox" data-qb-label-add-name="${escapeAttr(label.name)}">${lblChip(label)}</label>`).join('') || '<span class="hint">暂无标记</span>'}<button type="button" class="lbl add" data-qb-label-new>＋ 新建标记</button></div></div>
    <div class="qb-label-section"><strong>移除</strong><div class="qb-label-options">${names.map(label => `<label><input type="checkbox" data-qb-label-remove-name="${escapeAttr(label.name)}">${lblChip(label)}</label>`).join('') || '<span class="hint">暂无标记</span>'}</div></div>
    <div class="qb-label-foot"><button class="btn" type="button" data-qb-label-close>取消</button><button class="btn primary" type="button" data-qb-label-save>保存到 ${uids.length} 道题</button></div>
  </div>`;
  document.body.appendChild(modal);
  const close = () => modal.remove();
  modal.addEventListener('click', async event => {
    if (event.target === modal || event.target.closest('[data-qb-label-close]')) { close(); return; }
    if (event.target.closest('[data-qb-label-new]')) {
      const name = await uiPrompt('新标记名称', '', { placeholder: '如：考前必看' });
      if (!name) return;
      try {
        const label = await createAndSelectLabel(name, null);
        const box = modal.querySelector('[data-qb-label-add-name]')?.parentElement?.parentElement || modal.querySelector('.qb-label-options');
        box.insertAdjacentHTML('afterbegin', `<label><input type="checkbox" data-qb-label-add-name="${escapeAttr(label.name)}" checked>${lblChip(label)}</label>`);
      } catch (error) { uiToast(`新建标记失败：${error.message}`, { kind: 'error' }); }
      return;
    }
    if (!event.target.closest('[data-qb-label-save]')) return;
    const add = [...modal.querySelectorAll('[data-qb-label-add-name]:checked')].map(node => node.dataset.qbLabelAddName);
    const remove = [...modal.querySelectorAll('[data-qb-label-remove-name]:checked')].map(node => node.dataset.qbLabelRemoveName);
    if (!add.length && !remove.length) { close(); return; }
    try {
      const result = await batchAddRemoveLabels(uids, add, remove);
      close();
      uiToast(`已更新 ${result?.changed ?? uids.length} 道题的标记${result?.failed?.length ? `，${result.failed.length} 道失败` : ''}`, { kind: result?.failed?.length ? 'warn' : 'ok' });
    } catch (error) { uiToast(`批量保存标记失败：${error.message}`, { kind: 'error' }); }
  });
}
async function qbBatchSuspend() {
  const uids = [...QB_SELECTED];
  if (!uids.length) return;
  const items = uids.map(uid => getItemByUid(uid)).filter(Boolean);
  const toSuspend = items.filter(item => !item.suspended), toResume = items.filter(item => item.suspended);
  const ok = await uiConfirm(`停用 ${toSuspend.length} 道 / 恢复 ${toResume.length} 道题？`, { hint: '停用后不进入调度与统计，可随时恢复；正文与历史都保留。', okText: '执行' });
  if (!ok) return;
  let failed = 0;
  for (const item of items) {
    try {
      await api(item.suspended ? '/api/question/resume' : '/api/question/suspend', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ uid: item.uid }) });
    } catch (error) { failed += 1; }
  }
  QB_SELECTED.clear();
  await reloadData();
  if (typeof loadHist === 'function') loadHist();
  uiToast(failed ? `完成，但有 ${failed} 道题失败` : `已处理 ${items.length} 道题`, { kind: failed ? 'warn' : 'ok' });
}
async function qbBatchExport() {
  const uids = [...QB_SELECTED];
  if (!uids.length) return;
  try {
    const response = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ uids, format: 'a4', include_answers: false }) });
    if (!response.ok) { let message = '导出失败'; try { message = (await response.json()).msg || message; } catch (error) {} throw new Error(message); }
    await downloadExportResponse(response, 'OMRS-题库筛选-a4.html');
    uiToast(`已导出 ${uids.length} 道题的 A4 打印版`);
  } catch (error) { uiToast(`导出失败：${error.message}`, { kind: 'error' }); }
}

// ---------- 列 / 密度 ----------
function qbToggleDensity(value) {
  QB_DENSITY = value === 'compact' ? 'compact' : 'comfortable';
  try { localStorage.setItem('omrs-qb-density', QB_DENSITY); } catch (error) {}
  renderQ();
}
function qbSetGalleryDetail(checked) {
  QB_GALLERY_DETAIL = !!checked;
  try { localStorage.setItem('omrs-qb-gallery-detail', QB_GALLERY_DETAIL ? '1' : '0'); } catch (error) {}
  renderQ();
}
// 列数只改栅格，不动数据：写 data-cols 让 CSS 换 grid-template-columns，
// 不走 renderQ()，免得每点一次都重新拉一遍画廊预览
function qbSetGalleryCols(value) {
  QB_GALLERY_COLS = qbClampCols(value);
  try { localStorage.setItem('omrs-qb-gallery-cols', String(QB_GALLERY_COLS)); } catch (error) {}
  qbRenderDensity();
  qbRenderControls();
}
// 题面换行模式：只影响 renderMdContent 的换行处理，筛选 / 排序 / 数据都不动。
// 画廊卡直接由 renderQ 重绘；题目 Modal、反馈台、即时练习挂在 QV_MOUNTS 上，走 qvRerenderAll。
function qbSetMdMode(mode) {
  QB_MD_MODE = mode === 'full' ? 'full' : 'lean';
  try { localStorage.setItem('omrs-qb-md-mode', QB_MD_MODE); } catch (error) {}
  renderQ();
  if (typeof qvRerenderAll === 'function') qvRerenderAll();
}
function qbResetLayout() {
  QB_DENSITY = 'comfortable';
  QB_GALLERY_DETAIL = false;
  QB_GALLERY_COLS = 0;
  QB_MD_MODE = 'lean';
  QB_VISIBLE_COLUMNS = null;
  try {
    localStorage.removeItem('omrs-qb-density');
    localStorage.removeItem('omrs-qb-gallery-detail');
    localStorage.removeItem('omrs-qb-gallery-cols');
    localStorage.removeItem('omrs-qb-md-mode');
    localStorage.removeItem('omrs-qb-columns');
  } catch (error) {}
  renderQ();
  if (typeof qvRerenderAll === 'function') qvRerenderAll();
  uiToast('显示设置已恢复默认');
}
function qbSetColumnVisibility(key, checked) {
  const visible = qbVisibleColumns();
  if (checked) visible.add(key); else visible.delete(key);
  QB_VISIBLE_COLUMNS = [...visible];
  try { localStorage.setItem('omrs-qb-columns', JSON.stringify(QB_VISIBLE_COLUMNS)); } catch (error) {}
  renderQ();
}
function qbToggleColumn(key) { qbSetColumnVisibility(key, !qbVisibleColumns().has(key)); }

// ---------- 视图预设（localStorage） ----------
function qbViews() { try { return JSON.parse(localStorage.getItem(QB_VIEW_KEY) || '{}') || {}; } catch (error) { return {}; } }
function qbSaveViews(views) { try { localStorage.setItem(QB_VIEW_KEY, JSON.stringify(views)); } catch (error) {} }
function qbCurrentViewName() {
  const snapshot = JSON.stringify(qbViewSnapshot());
  return Object.entries(qbViews()).find(([, view]) => JSON.stringify({ fields: view.fields, labels: view.labels }) === JSON.stringify({ fields: qbViewSnapshot().fields, labels: qbViewSnapshot().labels }))?.[0] || '';
}
function qbViewSnapshot() {
  return {
    fields: Object.fromEntries(QB_FILTER_IDS.map(id => [id, qbFieldValue(id)])),
    labels: selectedLabelNames(),
    view: Q_VIEW,
    columns: [...qbVisibleColumns()],
    density: QB_DENSITY,
    galleryCols: QB_GALLERY_COLS,
    galleryDetail: QB_GALLERY_DETAIL,
    mdMode: QB_MD_MODE,
  };
}
function qbApplyView(name) {
  const view = qbViews()[name];
  if (!view) return;
  Object.entries(view.fields || {}).forEach(([id, value]) => qbSetField(id, value));
  setSelectedLabelNames(view.labels || []);
  if (view.view) Q_VIEW = view.view;
  if (Array.isArray(view.columns)) QB_VISIBLE_COLUMNS = view.columns;
  if (view.density) QB_DENSITY = view.density === 'compact' ? 'compact' : 'comfortable';
  if (view.galleryCols != null) QB_GALLERY_COLS = qbClampCols(view.galleryCols);
  if (view.galleryDetail != null) QB_GALLERY_DETAIL = !!view.galleryDetail;
  if (view.mdMode) QB_MD_MODE = view.mdMode === 'full' ? 'full' : 'lean';
  QB_QUICK = '';
  try {
    localStorage.setItem('omrs-qb-columns', JSON.stringify(QB_VISIBLE_COLUMNS));
    localStorage.setItem('omrs-qb-density', QB_DENSITY);
    localStorage.setItem('omrs-qb-gallery-cols', String(QB_GALLERY_COLS));
    localStorage.setItem('omrs-qb-gallery-detail', QB_GALLERY_DETAIL ? '1' : '0');
    localStorage.setItem('omrs-qb-md-mode', QB_MD_MODE);
  } catch (error) {}
  renderQ();
  uiToast(`已切换到视图「${name}」`);
}
async function qbSaveView() {
  const name = await uiPrompt('把当前筛选 + 排序 + 列设置存为视图', qbCurrentViewName() || '', { placeholder: '如：考前必看·未掌握', hint: '存在本机浏览器里，下次一键回到同一子集。' });
  if (!name) return;
  const views = qbViews();
  views[name] = qbViewSnapshot();
  qbSaveViews(views);
  qbRenderViews();
  uiToast(`已保存视图「${name}」`);
}
function qbRenderViews() {
  const box = document.getElementById('qb-view-menu');
  if (!box) return;
  const names = Object.keys(qbViews());
  const current = names.length ? qbCurrentViewName() : '';
  box.innerHTML = names.length
    ? names.map(name => `<button type="button" data-qb-view="${escapeAttr(name)}" class="${name === current ? 'on' : ''}">${escapeHtml(name)}</button>`).join('')
    : '<span class="qb-view-empty">还没有视图预设</span>';
}
function qbManageViews() {
  const views = qbViews();
  const names = Object.keys(views);
  if (!names.length) { uiToast('还没有保存的视图', { kind: 'warn' }); return; }
  const modal = document.createElement('div');
  modal.className = 'modal-overlay open';
  const describe = view => {
    const fields = view.fields || {};
    const bits = [];
    if (fields['q-filter-subj']) bits.push(fields['q-filter-subj']);
    if (fields['q-filter-category']) bits.push(fields['q-filter-category']);
    if ((view.labels || []).length) bits.push(`标记 ${view.labels.join('/')}`);
    if (fields['q-filter-due']) bits.push(QB_DUE_LABELS[fields['q-filter-due']] || fields['q-filter-due']);
    if (fields['q-filter-tag']) bits.push(fields['q-filter-tag']);
    return bits.join(' · ') || '无筛选条件';
  };
  modal.innerHTML = `<div class="modal qb-view-modal" style="max-width:520px">
    <div class="modal-close" data-qb-view-close>✕</div>
    <h2 style="font-size:.95rem;font-weight:800;color:var(--accent2);margin:0 0 4px">管理视图预设</h2>
    <div class="qb-view-manager-list">${names.map(name => `<div class="qb-view-manager-row"><span>${escapeHtml(name)}<small>${escapeHtml(describe(views[name]))}</small></span><button type="button" class="btn sm" data-qb-view-apply="${escapeAttr(name)}">应用</button><button type="button" class="btn sm danger" data-qb-view-delete="${escapeAttr(name)}">删除</button></div>`).join('')}</div>
    <div class="qb-view-modal-foot"><button type="button" class="btn" data-qb-view-close>关闭</button></div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', event => {
    if (event.target === modal || event.target.closest('[data-qb-view-close]')) { modal.remove(); return; }
    const apply = event.target.closest('[data-qb-view-apply]');
    if (apply) { modal.remove(); qbApplyView(apply.dataset.qbViewApply); return; }
    const remove = event.target.closest('[data-qb-view-delete]');
    if (!remove) return;
    const current = qbViews();
    delete current[remove.dataset.qbViewDelete];
    qbSaveViews(current);
    remove.closest('.qb-view-manager-row')?.remove();
    qbRenderViews();
  });
}

// ---------- 键盘 ----------
function qbHandleKey(event) {
  const panel = document.getElementById('panel-questions');
  if (!panel?.classList.contains('active')) return;
  if (document.querySelector('.modal-overlay.open') || LABEL_PICKER) return;
  const key = event.key || '';
  if (event.target.closest?.('input,textarea,select,[contenteditable]')) {
    if (key === 'Escape' && event.target.id === 'q-search') { event.target.value = ''; filterQ(); }
    return;
  }
  if (event.metaKey || event.ctrlKey || event.altKey) return;
  const visible = qbVisibleItems();
  const cursorIndex = visible.findIndex(item => item.uid === QB_CURSOR_UID);
  const focusRow = () => {
    const row = [...document.querySelectorAll('[data-q-row]')].find(node => node.dataset.qRow === QB_CURSOR_UID);
    row?.scrollIntoView?.({ block: 'nearest' });
  };
  if (key === 'ArrowUp' || key === 'ArrowDown') {
    event.preventDefault();
    if (!visible.length) return;
    const delta = key === 'ArrowUp' ? -1 : 1;
    const next = cursorIndex < 0 ? (delta > 0 ? 0 : visible.length - 1) : Math.max(0, Math.min(visible.length - 1, cursorIndex + delta));
    QB_CURSOR_UID = visible[next].uid;
    document.querySelectorAll('[data-q-row]').forEach(row => { const on = row.dataset.qRow === QB_CURSOR_UID; row.classList.toggle('qb-cursor', on); row.setAttribute('aria-selected', on ? 'true' : 'false'); });
    focusRow();
  } else if (key === ' ') {
    event.preventDefault();
    const current = visible[cursorIndex < 0 ? 0 : cursorIndex];
    if (current) { QB_CURSOR_UID = current.uid; qbSelect(current.uid, !QB_SELECTED.has(current.uid)); const box = document.querySelector(`[data-qb-uid="${CSS.escape(current.uid)}"]`); if (box) box.checked = QB_SELECTED.has(current.uid); }
  } else if (key === 'Enter') {
    const current = visible[cursorIndex < 0 ? 0 : cursorIndex];
    if (current && typeof viewQ === 'function') { event.preventDefault(); viewQ(current.uid, 'q'); }
  } else if (key === '/') { event.preventDefault(); document.getElementById('q-search')?.focus(); }
  else if (key === 'f' || key === 'F') qbToggleDrawer();
  else if (key === 'v' || key === 'V') setQView(Q_VIEW === 'table' ? 'gallery' : 'table');
  // 画廊里用 [ / ] 直接加减列数；0 是自动，所以从自动往下调先落到 6
  else if ((key === '[' || key === ']') && qbCurrentView() === 'gallery') {
    event.preventDefault();
    const step = key === ']' ? 1 : -1;
    const current = QB_GALLERY_COLS || 0;
    qbSetGalleryCols(current === 0 ? (step > 0 ? 1 : 6) : current + step);
  }
  else if (key === 'Escape') { if (QB_SELECTED.size) qbClearSelection(); else qbToggleDrawer(false); }
  else if ((key === 'b' || key === 'B') && QB_SELECTED.size) qbBatchBoard();
  else if ((key === 'l' || key === 'L') && QB_SELECTED.size) qbBatchLabels();
}

// ---------- 事件委托 ----------
if (typeof document !== 'undefined') {
  document.addEventListener('click', event => {
    const clear = event.target.closest?.('[data-qb-clear]');
    if (clear) { qbClearChip(clear.dataset.qbClear, clear.dataset.qbValue, clear.dataset.qbReset); return; }
    const quick = event.target.closest?.('[data-qb-quick]');
    if (quick) { qbApplyQuick(quick.dataset.qbQuick); return; }
    const seg = event.target.closest?.('[data-qb-seg] button');
    if (seg) {
      const group = seg.closest('[data-qb-seg]');
      qbSetField(group.dataset.qbSeg, seg.dataset.value || '');
      QB_QUICK = '';
      renderQ();
      return;
    }
    const view = event.target.closest?.('[data-qb-view]');
    if (view) { qbApplyView(view.dataset.qbView); return; }
    const density = event.target.closest?.('[data-qb-density]');
    if (density) { qbToggleDensity(density.dataset.qbDensity); return; }
    const cols = event.target.closest?.('[data-qb-cols]');
    if (cols) { qbSetGalleryCols(cols.dataset.qbCols); return; }
    const mdMode = event.target.closest?.('[data-qb-md]');
    if (mdMode) { qbSetMdMode(mdMode.dataset.qbMd); return; }
    if (event.target.closest?.('[data-qb-layout-reset]')) { qbResetLayout(); return; }
    const menuToggle = event.target.closest?.('[data-qb-menu-toggle]');
    if (menuToggle) {
      event.stopPropagation();
      const name = menuToggle.dataset.qbMenuToggle;
      document.querySelectorAll('[data-qb-menu]').forEach(node => node.classList.toggle('open', node.dataset.qbMenu === name && !node.classList.contains('open')));
      qbRenderControls();
      return;
    }
    if (event.target.closest?.('[data-qb-view-save]')) { qbSaveView(); return; }
    if (event.target.closest?.('[data-qb-view-manage]')) { qbManageViews(); return; }
    if (!event.target.closest?.('[data-qb-menu]')) document.querySelectorAll('[data-qb-menu].open').forEach(node => node.classList.remove('open'));
  });
  document.addEventListener('change', event => {
    const column = event.target.closest?.('[data-qb-column]');
    if (column) { qbSetColumnVisibility(column.dataset.qbColumn, column.checked); return; }
    const galleryDetail = event.target.closest?.('[data-qb-gallery-detail]');
    if (galleryDetail) { qbSetGalleryDetail(galleryDetail.checked); return; }
    const dual = event.target.closest?.('.qb-dual input[type=range]');
    if (dual) { qbSyncDual(dual.closest('.qb-dual').dataset.qbDual); QB_QUICK = ''; renderQ(); }
  });
  document.addEventListener('input', event => {
    const dual = event.target.closest?.('.qb-dual input[type=range]');
    if (dual) {
      qbSyncDual(dual.closest('.qb-dual').dataset.qbDual);
      const match = document.getElementById('qb-match-count');
      if (match) match.textContent = qbVisibleItems().length;   // 拖动时只预览命中数，不重排列表
    }
  });
  document.addEventListener('keydown', qbHandleKey);
  qbReadPrefs();
}

if (typeof module !== 'undefined') module.exports = {
  qbActiveFilters, qbFilterCount, qbViewSnapshot, qbVisibleColumns, qbClampCols, QB_DEFAULT_COLUMNS,
};
