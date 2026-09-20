// === assets/labels.js — 用户标记：<=> 芯片、LabelPicker、管理标记、标记筛选 ===
// 标记是用户自己打的横切备注（「考前必看」「计算失误」…），名称写进题目 YAML 的 `标记:`，
// 不替代状态 Current_Tag，也不替代知识点 Knowledge_Tags。
// 依赖 core.js（api/escapeHtml/escapeAttr/getItemByUid/uiToast/uiDialog），必须排在 core.js 之后、questions.js 之前。
// 约定：DOM 里不拼函数名，交互走 data-lbl-* 事件委托。

let LABELS = [];                       // /api/labels 的定义列表 [{id,name,color,order,priority_bonus,count}]
let LABEL_PICKER = null;               // 当前打开的 picker 节点
const LABEL_RECENT_KEY = 'omrs-label-recent';
const LABEL_PRESETS = [
  '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0d9488',
  '#2563eb', '#7c3aed', '#db2777', '#64748b', '#78716c',
];

// ---------- 颜色工具 ----------
function labelHex(value) {
  const raw = String(value || '').trim().replace(/^#/, '');
  if (/^[0-9a-f]{3}$/i.test(raw)) return '#' + raw.split('').map(ch => ch + ch).join('').toLowerCase();
  if (/^[0-9a-f]{6}$/i.test(raw)) return '#' + raw.toLowerCase();
  return '#64748b';
}
function labelRgb(hex) {
  const value = labelHex(hex).slice(1);
  return [parseInt(value.slice(0, 2), 16), parseInt(value.slice(2, 4), 16), parseInt(value.slice(4, 6), 16)];
}
function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h = 0, s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > .5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4;
    }
    h /= 6;
  }
  return [h, s, l];
}
function hslToRgb(h, s, l) {
  if (!s) { const n = Math.round(l * 255); return [n, n, n]; }
  const hue = (p, q, t) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };
  const q = l < .5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  return [hue(p, q, h + 1 / 3), hue(p, q, h), hue(p, q, h - 1 / 3)].map(v => Math.round(v * 255));
}
function rgbHex(rgb) {
  return '#' + rgb.map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('');
}
function relativeLuminance(rgb) {
  const linear = rgb.map(value => { const v = value / 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); });
  return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
}
function contrastRatio(a, b) {
  const l1 = relativeLuminance(a), l2 = relativeLuminance(b);
  return (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05);
}
// solid 变体的前景色：相对亮度 > .55 用近黑，否则用白（浅黄底不会配白字）
function labelFg(hex) {
  return relativeLuminance(labelRgb(hex)) > .55 ? '#1a1c1f' : '#ffffff';
}
function labelCompositeBackground(color, theme) {
  const base = theme === 'dark' ? [33, 31, 29] : [255, 255, 255];
  const alpha = theme === 'dark' ? .24 : .16;
  return labelRgb(color).map((value, index) => Math.round(value * alpha + base[index] * (1 - alpha)));
}
// soft / print 变体的文字色：只钳同色相的亮度，保证淡底上的小字达到 WCAG AA；用户保存的 color 永远不变。
function lblInk(hex, theme) {
  const [h, s] = rgbToHsl(...labelRgb(hex));
  const background = labelCompositeBackground(hex, theme);
  const candidates = [];
  if (theme === 'dark') { for (let l = .98; l >= .46; l -= .01) candidates.push(hslToRgb(h, Math.max(s, .35), l)); candidates.push([255, 255, 255]); }
  else { for (let l = .02; l <= .58; l += .01) candidates.push(hslToRgb(h, Math.max(s, .35), l)); candidates.push([0, 0, 0]); }
  const good = candidates.find(rgb => contrastRatio(rgb, background) >= 4.5);
  return rgbHex(good || candidates.sort((a, b) => contrastRatio(b, background) - contrastRatio(a, background))[0]);
}
const _INK_CACHE = new Map();
function lblInkCached(hex, theme) {
  const key = hex + theme;
  if (!_INK_CACHE.has(key)) _INK_CACHE.set(key, lblInk(hex, theme));
  return _INK_CACHE.get(key);
}

// ---------- 定义查询 ----------
function labelObject(label) {
  if (typeof label === 'string') return LABELS.find(item => item.name === label) || { name: label, color: '#64748b' };
  return label || { name: '', color: '#64748b' };
}
function labelNames() { return LABELS.map(item => item.name); }
function nextLabelColor() {
  const used = new Set(LABELS.map(item => labelHex(item.color)));
  return LABEL_PRESETS.find(color => !used.has(color)) || LABEL_PRESETS[LABELS.length % LABEL_PRESETS.length];
}

// ---------- 芯片 ----------
// lblChip(labelOrName, {variant:'soft'|'solid'|'print', lg, uid, add, dim})
function lblChipStyle(color) {
  const hex = labelHex(color);
  const [r, g, b] = labelRgb(hex);
  return `--lbl-c:${hex};--lbl-fg:${labelFg(hex)};--lbl-rgb:${r},${g},${b};--lbl-ink-l:${lblInkCached(hex, 'light')};--lbl-ink-d:${lblInkCached(hex, 'dark')}`;
}
function lblChip(label, options = {}) {
  const item = labelObject(label);
  const name = String(item.name || '').trim();
  if (!name) return '';
  const classes = ['lbl'];
  if (options.variant === 'solid' || options.solid) classes.push('solid');
  if (options.variant === 'print' || options.print) classes.push('print');
  if (options.lg) classes.push('lg');
  if (options.dim) classes.push('dim');
  const attrs = [`class="${classes.join(' ')}"`, `style="${lblChipStyle(item.color)}"`, `data-lbl-name="${escapeAttr(name)}"`, `title="${escapeAttr(name)}"`];
  return `<span ${attrs.join(' ')}>${escapeHtml(name)}</span>`;
}
// lblChips(names, {uid, add, lg, variant, max}) —— add:true 时追加一个「＋」入口；uid 给委托用
function lblChips(labels, options = {}) {
  const values = Array.isArray(labels) ? labels.filter(Boolean) : [];
  const max = options.max || 0;
  const shown = max && values.length > max ? values.slice(0, max) : values;
  let html = shown.map(name => lblChip(name, options)).join('');
  if (max && values.length > max) html += `<span class="lbl add" title="${escapeAttr(values.slice(max).join('、'))}">+${values.length - max}</span>`;
  if (options.add) {
    const cls = `lbl add${options.lg ? ' lg' : ''}`;
    html += `<span class="${cls}" data-lbl-add="1" title="打标记">${values.length ? '＋' : '＋ 标记'}</span>`;
  }
  // 传 uid 时包一层可点击的委托容器：点任意芯片或「＋」都打开该题的 picker
  if (options.uid) html = `<span class="lbl-row" data-lbl-target="${escapeAttr(options.uid)}">${html}</span>`;
  return html;
}

// ---------- 加载 ----------
async function loadLabels() {
  try {
    const result = await api('/api/labels');
    LABELS = Array.isArray(result?.labels) ? result.labels : [];
  } catch (error) {
    LABELS = [];
  }
  LABELS.sort((a, b) => (a.order || 0) - (b.order || 0) || String(a.name).localeCompare(String(b.name), 'zh-CN'));
  renderLabelFilterOptions();
  renderCreateLabels();
  return LABELS;
}
function labelUpsertLocal(label) {
  if (!label || !label.name) return;
  LABELS = [...LABELS.filter(item => item.id !== label.id && item.name !== label.name), label];
  LABELS.sort((a, b) => (a.order || 0) - (b.order || 0) || String(a.name).localeCompare(String(b.name), 'zh-CN'));
}

// ---------- 标记筛选（题库 q / 推荐 rec / 导出 pick / 即时练习 inst / 展示板选题 bdadd） ----------
function labelFilterIds(prefix) {
  return { box: `${prefix}-label-filter-list`, hidden: `${prefix}-filter-labels`, mode: `${prefix}-label-mode` };
}
function renderLabelFilterOptions(prefix) {
  const prefixes = prefix ? [prefix] : ['q', 'rec', 'rec-v2', 'pick', 'inst'];
  prefixes.forEach(name => {
    const ids = labelFilterIds(name);
    const box = document.getElementById(ids.box);
    if (!box) return;
    const selected = new Set(selectedLabelNamesFor(name));
    const defs = LABELS.filter(item => !item.archived);
    box.innerHTML = defs.length
      ? defs.map(item => `<button type="button" class="label-filter-chip ${selected.has(item.name) ? 'on' : ''}" data-label-filter="${escapeAttr(name)}" data-label-name="${escapeAttr(item.name)}" title="${escapeAttr(item.name)}${item.count != null ? ` · ${item.count} 题` : ''}">${lblChip(item)}</button>`).join('')
      : '<span class="label-filter-empty">还没有标记 · 在题目上点「＋ 标记」即可创建</span>';
  });
}
function selectedLabelNamesFor(prefix = 'q') {
  const ids = labelFilterIds(prefix);
  return String(document.getElementById(ids.hidden)?.value || '').split('|').map(s => s.trim()).filter(Boolean);
}
function setSelectedLabelNamesFor(prefix, values) {
  const ids = labelFilterIds(prefix);
  let hidden = document.getElementById(ids.hidden);
  if (!hidden) {
    hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.id = ids.hidden;
    (document.getElementById(ids.box)?.parentElement || document.body).appendChild(hidden);
  }
  hidden.value = [...new Set(values || [])].join('|');
  renderLabelFilterOptions(prefix);
}
function selectedLabelNames() { return selectedLabelNamesFor('q'); }
function setSelectedLabelNames(values) { setSelectedLabelNamesFor('q', values); }
function labelFilterChanged(prefix) {
  if (prefix === 'q' && typeof filterQ === 'function') filterQ();
  else if (prefix === 'rec-v2' && typeof renderUnifiedListV2 === 'function') renderUnifiedListV2();
  else if (prefix === 'rec' && typeof renderDualLists === 'function') renderDualLists();
  else if (prefix === 'pick' && typeof renderExportPicker === 'function') renderExportPicker();
  else if (prefix === 'inst' && typeof instRenderSide === 'function') instRenderSide();
}

// ---------- 最近使用 ----------
function labelRecent() {
  try { return JSON.parse(localStorage.getItem(LABEL_RECENT_KEY) || '[]').filter(name => LABELS.some(item => item.name === name)); } catch (error) { return []; }
}
function labelTouchRecent(names) {
  try {
    const next = [...new Set([...(names || []), ...labelRecent()])].slice(0, 6);
    localStorage.setItem(LABEL_RECENT_KEY, JSON.stringify(next));
  } catch (error) {}
}
function labelQuickList(limit = 4) {
  const recent = labelRecent();
  const rest = LABELS.filter(item => !recent.includes(item.name)).map(item => item.name);
  return [...recent, ...rest].slice(0, limit).map(name => labelObject(name));
}

// ---------- LabelPicker（题库 / Modal / 反馈 / 录入 / 展示板 共用） ----------
function closeLabelPicker() {
  LABEL_PICKER?.remove();
  LABEL_PICKER = null;
}
// openLabelPicker(uid, anchorEl, {get: () => names, onSave: names => Promise, title})
function openLabelPicker(uid, anchor, config = {}) {
  if (LABEL_PICKER && LABEL_PICKER.dataset.uid === String(uid)) { closeLabelPicker(); return; }
  closeLabelPicker();
  const readLabels = typeof config.get === 'function' ? config.get : () => (getItemByUid(uid)?.labels || []);
  const saveLabels = typeof config.onSave === 'function' ? config.onSave : labels => saveQuestionLabels(uid, labels);
  const initial = [...(readLabels() || [])];
  const current = new Set(initial);
  const box = document.createElement('div');
  box.className = 'label-picker-pop';
  box.dataset.uid = uid;
  box.innerHTML = `<div class="label-picker-head"><span>标记</span><small>${escapeHtml(config.title || uid || '')}</small></div>
    <input class="input label-picker-search" placeholder="搜索或输入新标记，回车创建…" autocomplete="off">
    <div class="label-picker-options"></div>
    <div class="label-picker-recent"></div>
    <div class="label-picker-foot"><button type="button" class="btn sm ghost" data-lbl-manage>管理标记…</button><span class="hint">↑↓ 移动 · 空格切换 · Esc 关闭</span><button type="button" class="btn sm primary" data-lbl-save>完成</button></div>`;
  document.body.appendChild(box);
  LABEL_PICKER = box;
  const rect = anchor?.getBoundingClientRect?.() || { left: 24, bottom: 80, top: 60 };
  const width = 284, height = box.offsetHeight || 330;
  let left = Math.max(10, Math.min(window.innerWidth - width - 10, rect.left));
  let top = rect.bottom + 6;
  if (top + height > window.innerHeight - 10) top = Math.max(10, rect.top - height - 6);
  box.style.left = `${left}px`;
  box.style.top = `${top}px`;
  const search = box.querySelector('.label-picker-search');
  const optionsBox = box.querySelector('.label-picker-options');
  const recentBox = box.querySelector('.label-picker-recent');
  let activeIndex = 0;
  const optionNodes = () => [...optionsBox.querySelectorAll('[data-lbl-name],[data-lbl-new]')];
  const render = () => {
    const raw = search.value.trim();
    const needle = raw.toLowerCase();
    const matches = LABELS.filter(label => !label.archived && (!needle || label.name.toLowerCase().includes(needle)));
    const exact = LABELS.some(label => label.name === raw);
    optionsBox.innerHTML =
      (raw && !exact ? `<button type="button" class="label-picker-option new" data-lbl-new="${escapeAttr(raw)}"><span class="check">＋</span>新建「${escapeHtml(raw)}」并选中</button>` : '') +
      (matches.map(label => `<button type="button" class="label-picker-option ${current.has(label.name) ? 'selected' : ''}" data-lbl-name="${escapeAttr(label.name)}"><span class="check">${current.has(label.name) ? '✓' : ''}</span>${lblChip(label)}<span class="cnt">${label.count ?? ''}</span></button>`).join('') ||
        (raw ? '' : '<div class="label-picker-empty">还没有标记：输入名称后回车即可创建。</div>'));
    const quick = labelQuickList(4).filter(label => !current.has(label.name));
    recentBox.innerHTML = quick.length ? `<span>快速：</span>${quick.map(label => lblChip(label, { uid: '' })).join('')}` : '';
    recentBox.style.display = quick.length ? '' : 'none';
    activeIndex = Math.max(0, Math.min(activeIndex, Math.max(0, optionNodes().length - 1)));
    optionNodes().forEach((node, index) => node.classList.toggle('keyboard-active', index === activeIndex));
  };
  render();
  requestAnimationFrame(() => search.focus());
  search.addEventListener('input', () => { activeIndex = 0; render(); });
  search.addEventListener('keydown', async event => {
    const options = optionNodes();
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!options.length) return;
      event.preventDefault();
      activeIndex = (activeIndex + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
      options.forEach((node, index) => node.classList.toggle('keyboard-active', index === activeIndex));
      options[activeIndex]?.scrollIntoView?.({ block: 'nearest' });
      return;
    }
    if (event.key === 'Enter' || (event.key === ' ' && !search.value)) {
      event.preventDefault();
      if (options[activeIndex]) options[activeIndex].click();
      return;
    }
    if (event.key === 'Escape') { event.stopPropagation(); closeLabelPicker(); }
  });
  box.addEventListener('click', async event => {
    const option = event.target.closest('[data-lbl-name]');
    if (option && !event.target.closest('.label-picker-recent')) {
      const name = option.dataset.lblName;
      current.has(name) ? current.delete(name) : current.add(name);
      render();
      return;
    }
    const quick = event.target.closest('.label-picker-recent [data-lbl-name]');
    if (quick) { current.add(quick.dataset.lblName); render(); return; }
    const create = event.target.closest('[data-lbl-new]');
    if (create) {
      try { await createAndSelectLabel(create.dataset.lblNew, current); search.value = ''; render(); }
      catch (error) { uiToast(`新建标记失败：${error.message}`, { kind: 'error' }); }
      return;
    }
    if (event.target.closest('[data-lbl-save]')) {
      const next = [...current];
      closeLabelPicker();
      if (next.join('|') !== initial.join('|')) await saveLabels(next);
      return;
    }
    if (event.target.closest('[data-lbl-manage]')) { closeLabelPicker(); openLabelManager(); }
  });
}

async function createAndSelectLabel(name, selected) {
  const clean = String(name || '').trim();
  if (!clean) return null;
  let found = LABELS.find(label => label.name === clean);
  if (!found) {
    const result = await api('/api/label/save', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: clean, color: nextLabelColor() }),
    });
    found = result.label;
    labelUpsertLocal(found);
    renderLabelFilterOptions();
  }
  if (selected) selected.add(found.name);
  return found;
}

// ---------- 保存（乐观更新 + 失败回滚） ----------
function labelRefreshViews(uids) {
  if (typeof renderQ === 'function') renderQ();
  if (typeof boardReloadData === 'function' && document.getElementById('panel-board')?.classList.contains('active')) boardReloadData();
  if (typeof renderExportPicker === 'function' && document.getElementById('export-panel')?.style.display !== 'none') renderExportPicker();
  (uids || []).forEach(uid => { if (typeof qvInvalidate === 'function') qvInvalidate(uid); });
  if (typeof renderFb === 'function' && document.getElementById('panel-feedback')?.classList.contains('active')) { try { renderFb(); } catch (error) {} }
}
async function saveQuestionLabels(uid, labels) {
  const item = getItemByUid(uid);
  const before = item ? [...(item.labels || [])] : [];
  if (item) item.labels = [...labels];
  labelRefreshViews([uid]);
  try {
    await api('/api/question/labels', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid, labels }),
    });
    labelTouchRecent(labels);
    await loadLabels();
    uiToast(labels.length ? `已保存标记：${labels.join('、')}` : '已清空标记');
  } catch (error) {
    if (item) item.labels = before;
    labelRefreshViews([uid]);
    uiToast(`保存标记失败：${error.message}`, { kind: 'error' });
  }
}
async function batchAddRemoveLabels(uids, add = [], remove = []) {
  const result = await api('/api/questions/labels', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uids, add, remove }),
  });
  const removeSet = new Set(remove);
  getItems().forEach(item => {
    if (!uids.includes(item.uid)) return;
    item.labels = [...new Set([...(item.labels || []), ...add])].filter(label => !removeSet.has(label));
  });
  labelTouchRecent(add);
  await loadLabels();
  labelRefreshViews(uids);
  return result;
}

// ---------- 录入表单里的「标记」字段 ----------
function selectedCreateLabels() {
  return String(document.getElementById('cr-labels-value')?.value || '').split('|').map(value => value.trim()).filter(Boolean);
}
function setCreateLabels(values) {
  const hidden = document.getElementById('cr-labels-value');
  if (hidden) hidden.value = [...new Set(values || [])].map(value => String(value).trim()).filter(Boolean).join('|');
  renderCreateLabels();
}
function renderCreateLabels() {
  const box = document.getElementById('cr-labels');
  if (!box) return;
  let hidden = document.getElementById('cr-labels-value');
  if (!hidden) {
    hidden = document.createElement('input');
    hidden.type = 'hidden';
    hidden.id = 'cr-labels-value';
  }
  const values = selectedCreateLabels();
  box.innerHTML = `${values.map(value => lblChip(value, { lg: true })).join('')}<button type="button" class="lbl-form-add" data-lbl-create-open>＋ 添加标记</button>`;
  box.appendChild(hidden);
}
function openCreateLabelsPicker(anchor) {
  openLabelPicker('__create__', anchor, { get: selectedCreateLabels, onSave: values => setCreateLabels(values), title: '新题目' });
}

// ---------- 管理标记（改名 / 换色 / 调度加成 / 合并 / 删除） ----------
function labelManagerRowHtml(item) {
  const bonus = Number(item.priority_bonus || 0);
  return `<div class="label-manager-row" data-label-id="${escapeAttr(item.id)}">
    <span class="label-swatch" style="background:${labelHex(item.color)}"></span>
    <span class="label-manager-name">${lblChip(item, { lg: true, variant: 'solid' })}</span>
    <span class="label-manager-count">${item.count || 0} 题</span>
    <span class="label-manager-bonus" title="推荐优先级加成">${bonus > 0 ? `+${bonus.toFixed(2)}` : '—'}</span>
    <span class="label-manager-acts"><button class="btn sm" type="button" data-label-edit="${escapeAttr(item.id)}">编辑</button><button class="btn sm" type="button" data-label-merge="${escapeAttr(item.id)}" ${LABELS.length < 2 ? 'disabled' : ''}>合并</button><button class="btn sm danger" type="button" data-label-delete="${escapeAttr(item.id)}">删除</button></span>
  </div>`;
}
function labelSwatchesHtml(current, name = 'color') {
  const hex = labelHex(current);
  const custom = !LABEL_PRESETS.includes(hex);
  return `<div class="lbl-swatches" data-lbl-swatches="${escapeAttr(name)}">${LABEL_PRESETS.map(color => `<button type="button" class="sw ${color === hex ? 'on' : ''}" style="background:${color}" data-sw="${color}" title="${color}"></button>`).join('')}<span class="sw custom ${custom ? 'on' : ''}" title="自定义颜色"><input type="color" value="${escapeAttr(hex)}" data-sw-custom></span><input type="hidden" data-sw-value value="${escapeAttr(hex)}"></div>`;
}
function labelEditFormHtml(item) {
  return `<div class="label-edit">
    <div class="label-edit-row"><label>名称</label><input class="input" data-label-field="name" value="${escapeAttr(item.name || '')}" maxlength="80" placeholder="标记名称"></div>
    <div class="label-edit-row"><label>颜色</label>${labelSwatchesHtml(item.color)}</div>
    <div class="label-edit-row"><label>调度加成</label><input class="input" type="number" data-label-field="priority_bonus" min="0" max="1" step="0.05" value="${escapeAttr(Number(item.priority_bonus || 0))}" style="max-width:100px"><span class="hint">0 = 不影响推荐；例如给「考前必看」设 0.3 让它在推荐里上浮（上限受 label_bonus_cap 约束）</span></div>
    <div class="label-edit-row"><span class="grow"></span><button class="btn sm ghost" type="button" data-label-cancel>取消</button><button class="btn sm primary" type="button" data-label-save="${escapeAttr(item.id || '')}">${item.id ? '保存' : '＋ 新建'}</button></div>
  </div>`;
}
function openLabelManager() {
  document.getElementById('label-manager')?.remove();
  const modal = document.createElement('div');
  modal.id = 'label-manager';
  modal.className = 'modal-overlay open';
  const renderList = () => {
    modal.querySelector('.label-manager-list').innerHTML = LABELS.length
      ? LABELS.map(labelManagerRowHtml).join('')
      : '<div class="empty-inline">还没有标记。用下面的表单新建，或在任意题目上点「＋ 标记」。</div>';
  };
  modal.innerHTML = `<div class="modal label-manager-modal">
    <div class="modal-close" data-label-close>✕</div>
    <h2 style="font-size:.95rem;font-weight:800;color:var(--accent2);margin:0 0 4px">管理标记</h2>
    <div class="hint">标记名称写在题目 Markdown 的 YAML「标记:」里，Obsidian 可读可改。改名 / 合并 / 删除会逐题重写引用它的文件并记 metadata commit；题目多时会花几秒。</div>
    <div class="label-manager-list"></div>
    <div class="label-manager-form" data-label-new-form>${labelEditFormHtml({ name: '', color: nextLabelColor(), priority_bonus: 0 })}</div>
    <div class="label-manager-foot"><button class="btn" type="button" data-label-close>关闭</button></div>
  </div>`;
  document.body.appendChild(modal);
  renderList();
  const readForm = root => {
    const name = root.querySelector('[data-label-field="name"]')?.value.trim() || '';
    const color = root.querySelector('[data-sw-value]')?.value || nextLabelColor();
    const bonus = asNumber(root.querySelector('[data-label-field="priority_bonus"]')?.value, 0);
    return { name, color, priority_bonus: Math.max(0, Math.min(1, bonus)) };
  };
  modal.addEventListener('input', event => {
    const custom = event.target.closest('[data-sw-custom]');
    if (custom) {
      const wrap = custom.closest('[data-lbl-swatches]');
      wrap.querySelector('[data-sw-value]').value = custom.value;
      wrap.querySelectorAll('.sw').forEach(node => node.classList.toggle('on', node.classList.contains('custom')));
    }
  });
  modal.addEventListener('click', async event => {
    if (event.target === modal || event.target.closest('[data-label-close]')) { modal.remove(); return; }
    const sw = event.target.closest('[data-sw]');
    if (sw) {
      const wrap = sw.closest('[data-lbl-swatches]');
      wrap.querySelector('[data-sw-value]').value = sw.dataset.sw;
      wrap.querySelectorAll('.sw').forEach(node => node.classList.toggle('on', node === sw));
      return;
    }
    const edit = event.target.closest('[data-label-edit]');
    if (edit) {
      const item = LABELS.find(label => label.id === edit.dataset.labelEdit);
      const row = edit.closest('.label-manager-row');
      if (!item || !row) return;
      row.classList.add('editing');
      row.innerHTML = labelEditFormHtml(item);
      row.querySelector('[data-label-field="name"]')?.focus();
      return;
    }
    if (event.target.closest('[data-label-cancel]')) {
      const row = event.target.closest('.label-manager-row');
      if (row) renderList(); else modal.querySelector('[data-label-new-form]').innerHTML = labelEditFormHtml({ name: '', color: nextLabelColor(), priority_bonus: 0 });
      return;
    }
    const save = event.target.closest('[data-label-save]');
    if (save) {
      const root = save.closest('.label-manager-row') || save.closest('[data-label-new-form]');
      const form = readForm(root);
      if (!form.name) { uiToast('标记名称不能为空', { kind: 'warn' }); return; }
      const id = save.dataset.labelSave || '';
      const item = id ? LABELS.find(label => label.id === id) : null;
      if (item && item.name !== form.name && (item.count || 0) > 200) {
        const ok = await uiConfirm(`把「${item.name}」改名为「${form.name}」？`, { hint: `会重写 ${item.count} 道题的 Markdown，可能需要几秒钟。`, okText: '改名' });
        if (!ok) return;
      }
      save.disabled = true;
      try {
        const result = await api('/api/label/save', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...form, id: id || undefined }) });
        await loadLabels();
        renderList();
        if (!id) modal.querySelector('[data-label-new-form]').innerHTML = labelEditFormHtml({ name: '', color: nextLabelColor(), priority_bonus: 0 });
        if (item && item.name !== form.name) { if (typeof reloadData === 'function') await reloadData(); }
        else labelRefreshViews();
        uiToast(id ? `已保存「${form.name}」${result.label?.affected ? ` · 更新了 ${result.label.affected} 道题` : ''}` : `已新建「${form.name}」`);
      } catch (error) { uiToast(`保存标记失败：${error.message}`, { kind: 'error' }); }
      finally { save.disabled = false; }
      return;
    }
    const merge = event.target.closest('[data-label-merge]');
    if (merge) {
      const item = LABELS.find(label => label.id === merge.dataset.labelMerge);
      if (!item) return;
      const others = LABELS.filter(label => label.id !== item.id);
      const selectId = 'label-merge-target';
      const res = await uiDialog({
        title: `把「${item.name}」合并到…`, okText: '合并',
        hint: `引用「${item.name}」的 ${item.count || 0} 道题会改成目标标记，然后删除「${item.name}」。`,
        body: `<select class="input" id="${selectId}">${others.map(label => `<option value="${escapeAttr(label.id)}">${escapeHtml(label.name)}（${label.count || 0} 题）</option>`).join('')}</select>`,
        focus: '#' + selectId,
      });
      if (!res.ok) return;
      try {
        const result = await api('/api/label/merge', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ from: item.id, into: res.values[selectId] }) });
        if (typeof reloadData === 'function') await reloadData(); else await loadLabels();
        renderList();
        uiToast(`已合并到「${result.into}」，影响 ${result.affected} 道题`);
      } catch (error) { uiToast(`合并失败：${error.message}`, { kind: 'error' }); }
      return;
    }
    const remove = event.target.closest('[data-label-delete]');
    if (remove) {
      const item = LABELS.find(label => label.id === remove.dataset.labelDelete);
      if (!item) return;
      const ok = await uiConfirm(`删除标记「${item.name}」？`, { hint: `会从 ${item.count || 0} 道题的 YAML 里移除它；题目本身不受影响。`, okText: '删除', danger: true });
      if (!ok) return;
      try {
        await api('/api/label/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: item.id, detach: true }) });
        if (typeof reloadData === 'function') await reloadData(); else await loadLabels();
        renderList();
        uiToast(`已删除「${item.name}」`);
      } catch (error) { uiToast(`删除标记失败：${error.message}`, { kind: 'error' }); }
    }
  });
}
// 兼容旧调用名
function boardManageLabels() { return openLabelManager(); }

// ---------- 事件委托 ----------
if (typeof document !== 'undefined') {
  document.addEventListener('click', event => {
    const create = event.target.closest?.('[data-lbl-create-open]');
    if (create) { event.stopPropagation(); openCreateLabelsPicker(create); return; }
    // 选项点击后 picker 会重绘，event.target 可能已脱离 DOM：用 composedPath 判断是否点在 picker 内
    const insidePicker = !!(LABEL_PICKER && (event.composedPath ? event.composedPath().includes(LABEL_PICKER) : LABEL_PICKER.contains(event.target)));
    const target = event.target.closest?.('[data-lbl-target]');
    if (target && !insidePicker) {
      event.stopPropagation();
      openLabelPicker(target.dataset.lblTarget, event.target.closest('.lbl') || target);
      return;
    }
    if (LABEL_PICKER && !insidePicker) closeLabelPicker();
    const filter = event.target.closest?.('[data-label-filter]');
    if (filter) {
      const prefix = filter.dataset.labelFilter || 'q';
      const values = selectedLabelNamesFor(prefix);
      const name = filter.dataset.labelName;
      setSelectedLabelNamesFor(prefix, values.includes(name) ? values.filter(item => item !== name) : [...values, name]);
      labelFilterChanged(prefix);
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && LABEL_PICKER) { closeLabelPicker(); }
  });
}

if (typeof module !== 'undefined') module.exports = {
  lblInk, lblChip, lblChips, labelHex, labelRgb, labelFg, rgbToHsl, hslToRgb, contrastRatio, LABEL_PRESETS,
};
