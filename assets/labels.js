// === assets/labels.js — 用户标记芯片与轻量选择器 ===
// 标记是横切的用户备注，不替代状态 Current_Tag 或知识点 Knowledge_Tags。

let LABELS = [];
let LABEL_PICKER = null;
const CREATE_LABELS_KEY = 'omrs-create-labels';

const LABEL_PRESETS = [
  '#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0d9488',
  '#2563eb', '#7c3aed', '#db2777', '#64748b', '#78716c',
];

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
  let h = 0, s = 0, l = (max + min) / 2;
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
  if (!s) {
    const n = Math.round(l * 255);
    return [n, n, n];
  }
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
  const linear = rgb.map(value => {
    const v = value / 255;
    return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4);
  });
  return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
}

function contrastRatio(a, b) {
  const l1 = relativeLuminance(a), l2 = relativeLuminance(b);
  return (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05);
}

function labelCompositeBackground(color, theme) {
  const base = theme === 'dark' ? [33, 31, 29] : [255, 255, 255];
  const rgb = labelRgb(color);
  return rgb.map((value, index) => Math.round(value * .18 + base[index] * .82));
}

// 文字色只钳同色系的亮度；用户保存的 color 永远不变。
// 先按主题尝试同色相的亮度，再用纯黑/白兜底，确保淡底上的小字仍达到 WCAG AA。
function lblInk(hex, theme) {
  const [h, s, originalL] = rgbToHsl(...labelRgb(hex));
  const background = labelCompositeBackground(hex, theme);
  const candidates = [];
  const start = theme === 'dark' ? .98 : .02;
  const end = theme === 'dark' ? .46 : .58;
  const step = theme === 'dark' ? -.01 : .01;
  for (let l = start; theme === 'dark' ? l >= end : l <= end; l += step) {
    candidates.push(hslToRgb(h, Math.max(s, .35), l));
  }
  candidates.push(theme === 'dark' ? [255, 255, 255] : [0, 0, 0]);
  const good = candidates.find(rgb => contrastRatio(rgb, background) >= 4.5);
  if (good) return rgbHex(good);
  const fallback = candidates.sort((a, b) => contrastRatio(b, background) - contrastRatio(a, background))[0];
  return rgbHex(fallback || hslToRgb(h, Math.max(s, .35), originalL));
}

function labelObject(label) {
  if (typeof label === 'string') {
    const found = LABELS.find(item => item.name === label);
    return found || { name: label, color: '#64748b' };
  }
  return label || { name: '', color: '#64748b' };
}

function lblChip(label, options = {}) {
  const item = labelObject(label);
  const name = String(item.name || '').trim();
  if (!name) return '';
  const color = labelHex(item.color);
  const [r, g, b] = labelRgb(color);
  const classes = ['lbl'];
  if (options.lg) classes.push('lg');
  if (options.print) classes.push('print');
  if (options.add) classes.push('add');
  const attrs = [
    `class="${classes.join(' ')}"`,
    `style="--lbl-rgb:${r},${g},${b};--lbl-ink-l:${lblInk(color, 'light')};--lbl-ink-d:${lblInk(color, 'dark')}"`,
  ];
  if (options.uid) attrs.push(`data-lbl-target="${escapeAttr(options.uid)}"`);
  if (options.add) attrs.push('data-lbl-add="1"');
  return `<span ${attrs.join(' ')}>${escapeHtml(name)}</span>`;
}

function lblChips(labels, options = {}) {
  const values = Array.isArray(labels) ? labels : [];
  const html = values.map(name => lblChip(name, options)).join('');
  return html || (options.add ? lblChip({ name: '＋ 标记', color: '#64748b' }, { ...options, add: true }) : '');
}

async function loadLabels() {
  try {
    const result = await api('/api/labels');
    LABELS = Array.isArray(result?.labels) ? result.labels : [];
  } catch (error) {
    LABELS = [];
  }
  renderLabelFilterOptions();
  renderCreateLabels();
  return LABELS;
}

function labelFilterIds(prefix) {
  return { box: `${prefix}-label-filter-list`, hidden: `${prefix}-filter-labels`, mode: `${prefix}-label-mode` };
}

function renderLabelFilterOptions(prefix) {
  const prefixes = prefix ? [prefix] : ['q', 'rec', 'pick', 'inst'];
  prefixes.forEach(name => {
    const ids = labelFilterIds(name);
    const box = document.getElementById(ids.box);
    if (!box) return;
    const selected = new Set(selectedLabelNamesFor(name));
    box.innerHTML = LABELS.filter(item => !item.archived)
      .map(item => `<button type="button" class="label-filter-chip ${selected.has(item.name) ? 'on' : ''}" data-label-filter="${escapeAttr(name)}" data-label-name="${escapeAttr(item.name)}">${lblChip(item)}</button>`)
      .join('');
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

function selectedLabelNames() {
  return selectedLabelNamesFor('q');
}

function setSelectedLabelNames(values) {
  setSelectedLabelNamesFor('q', values);
}

function labelFilterChanged(prefix) {
  if (prefix === 'q' && typeof filterQ === 'function') filterQ();
  else if (prefix === 'rec' && typeof loadRecommendations === 'function') loadRecommendations();
  else if (prefix === 'pick' && typeof renderExportPicker === 'function') renderExportPicker();
  else if (prefix === 'inst' && typeof instLoadPractice === 'function') instLoadPractice();
}

function closeLabelPicker() {
  LABEL_PICKER?.remove();
  LABEL_PICKER = null;
}

function openLabelPicker(uid, anchor, config = {}) {
  closeLabelPicker();
  const readLabels = typeof config.get === 'function'
    ? config.get
    : () => (getItemByUid(uid)?.labels || []);
  const saveLabels = typeof config.onSave === 'function'
    ? config.onSave
    : labels => saveQuestionLabels(uid, labels);
  const current = new Set(readLabels() || []);
  const box = document.createElement('div');
  box.className = 'label-picker-pop';
  box.dataset.uid = uid;
  box.innerHTML = `<div class="label-picker-title">标记</div>
    <input class="input label-picker-search" placeholder="搜索或新建…" autofocus>
    <div class="label-picker-options"></div>
    <div class="label-picker-recent">${LABELS.slice(0, 4).map(label => lblChip(label, { add: true })).join('')}</div>
    <div class="label-picker-foot"><button type="button" class="btn sm" data-lbl-manage>管理标记…</button><button type="button" class="btn sm primary" data-lbl-save>完成</button></div>`;
  document.body.appendChild(box);
  LABEL_PICKER = box;
  const rect = (anchor || document.body).getBoundingClientRect?.() || { left: 20, bottom: 80 };
  box.style.left = `${Math.min(window.innerWidth - 300, Math.max(10, rect.left))}px`;
  box.style.top = `${Math.min(window.innerHeight - 360, Math.max(10, rect.bottom + 6))}px`;
  const search = box.querySelector('.label-picker-search');
  let activeIndex = 0;
  const optionNodes = () => [...box.querySelectorAll('[data-lbl-name],[data-lbl-new]')];
  const render = () => {
    const needle = search.value.trim().toLowerCase();
    const matches = LABELS.filter(label => !needle || label.name.toLowerCase().includes(needle));
    const exact = LABELS.some(label => label.name.toLowerCase() === needle);
    box.querySelector('.label-picker-options').innerHTML =
      (!exact && needle ? `<button type="button" class="label-picker-option new" data-lbl-new="${escapeAttr(search.value.trim())}">＋ 新建「${escapeHtml(search.value.trim())}」</button>` : '') +
      matches.map(label => `<button type="button" class="label-picker-option ${current.has(label.name) ? 'selected' : ''}" data-lbl-name="${escapeAttr(label.name)}"><span class="check">${current.has(label.name) ? '✓' : ''}</span>${lblChip(label)}</button>`).join('') ||
      '<div class="hint" style="padding:8px">暂无标记</div>';
    activeIndex = Math.max(0, Math.min(activeIndex, Math.max(0, optionNodes().length - 1)));
    optionNodes().forEach((node, index) => node.classList.toggle('keyboard-active', index === activeIndex));
  };
  render();
  search.addEventListener('input', render);
  search.addEventListener('keydown', event => {
    const options = optionNodes();
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (!options.length) return;
      event.preventDefault();
      activeIndex = (activeIndex + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
      options.forEach((node, index) => node.classList.toggle('keyboard-active', index === activeIndex));
      options[activeIndex]?.scrollIntoView?.({ block: 'nearest' });
      return;
    }
    if ((event.key === 'Enter' || event.key === ' ') && options[activeIndex]) {
      event.preventDefault();
      options[activeIndex].click();
      return;
    }
    if (event.key === 'Enter' && search.value.trim() && !LABELS.some(label => label.name === search.value.trim())) {
      event.preventDefault();
      createAndSelectLabel(search.value.trim(), current).then(render);
    }
    if (event.key === 'Escape') closeLabelPicker();
  });
  box.addEventListener('click', async event => {
    const option = event.target.closest('[data-lbl-name]');
    if (option) {
      const name = option.dataset.lblName;
      current.has(name) ? current.delete(name) : current.add(name);
      render();
      return;
    }
    const create = event.target.closest('[data-lbl-new]');
    if (create) { await createAndSelectLabel(create.dataset.lblNew, current); render(); return; }
    const recent = event.target.closest('[data-lbl-add]');
    if (recent) {
      const name = recent.textContent.replace(/^＋\s*/, '').trim();
      if (name) current.add(name);
      render();
      return;
    }
    if (event.target.closest('[data-lbl-save]')) {
      await saveLabels([...current]);
      closeLabelPicker();
    }
    if (event.target.closest('[data-lbl-manage]')) {
      closeLabelPicker();
      if (typeof boardManageLabels === 'function') boardManageLabels();
    }
  });
}

function selectedCreateLabels() {
  const hidden = document.getElementById('cr-labels-value');
  return String(hidden?.value || '').split('|').map(value => value.trim()).filter(Boolean);
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
    box.appendChild(hidden);
  }
  const values = selectedCreateLabels();
  box.innerHTML = `${values.map(value => lblChip(value, { lg: true })).join('')}
    <button type="button" class="lbl-form-add" data-lbl-create-open>＋ 添加标记</button>`;
  box.appendChild(hidden);
}

function openCreateLabelsPicker(anchor) {
  openLabelPicker('__create__', anchor, {
    get: selectedCreateLabels,
    onSave: values => setCreateLabels(values),
  });
}

function labelManagerRows() {
  return LABELS.map(item => `<div class="label-manager-row" data-label-id="${escapeAttr(item.id)}">
    <span class="label-swatch" style="background:${labelHex(item.color)}"></span>
    <span class="label-manager-name">${lblChip(item, { lg: true })}</span>
    <span class="label-manager-count">${item.count || 0} 题</span>
    <button class="btn sm" data-label-edit="${escapeAttr(item.id)}">编辑</button>
    <button class="btn sm danger" data-label-delete="${escapeAttr(item.id)}">删除</button>
  </div>`).join('');
}

function boardManageLabels() {
  const old = document.getElementById('label-manager');
  old?.remove();
  const modal = document.createElement('div');
  modal.id = 'label-manager';
  modal.className = 'modal-overlay open';
  modal.innerHTML = `<div class="modal label-manager-modal">
    <div class="modal-close" data-label-close>✕</div>
    <h2>管理标记</h2>
    <div class="hint" style="margin-bottom:12px">标记名称会写入题目 Markdown 的 YAML「标记」字段；改名会级联更新引用。</div>
    <div class="label-manager-list">${labelManagerRows() || '<div class="empty-inline">还没有标记。</div>'}</div>
    <div class="label-manager-form">
      <input class="input" id="label-manager-name" placeholder="新标记名称">
      <input type="color" id="label-manager-color" value="${LABEL_PRESETS[0]}">
      <input class="input" id="label-manager-bonus" type="number" min="0" max="1" step=".05" value="0" title="推荐优先级加成">
      <button class="btn primary" data-label-new>＋ 新建</button>
    </div>
    <div class="hint" style="margin-top:8px">优先级加成默认 0；只有你主动设置时才影响推荐。</div>
  </div>`;
  document.body.appendChild(modal);
  modal.addEventListener('click', async event => {
    if (event.target === modal || event.target.closest('[data-label-close]')) { modal.remove(); return; }
    const edit = event.target.closest('[data-label-edit]');
    if (edit) {
      const item = LABELS.find(label => label.id === edit.dataset.labelEdit);
      if (!item) return;
      const name = prompt('标记名称', item.name);
      if (name === null) return;
      const color = prompt('颜色（#RRGGBB）', item.color) || item.color;
      const bonus = prompt('推荐优先级加成（0–1）', item.priority_bonus || 0);
      try {
        const result = await api('/api/label/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: item.id, name: name.trim(), color, priority_bonus: asNumber(bonus, item.priority_bonus || 0) }) });
        LABELS = LABELS.map(label => label.id === item.id ? result.label : label);
        renderLabelFilterOptions(); modal.querySelector('.label-manager-list').innerHTML = labelManagerRows();
        renderQ?.();
      } catch (error) { alert(`保存标记失败：${error.message}`); }
      return;
    }
    const remove = event.target.closest('[data-label-delete]');
    if (remove) {
      const item = LABELS.find(label => label.id === remove.dataset.labelDelete);
      if (!item || !confirm(`删除「${item.name}」并从题目中解除引用？`)) return;
      try {
        await api('/api/label/delete', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: item.id, detach: true }) });
        LABELS = LABELS.filter(label => label.id !== item.id);
        renderLabelFilterOptions(); modal.querySelector('.label-manager-list').innerHTML = labelManagerRows();
        renderQ?.();
      } catch (error) { alert(`删除标记失败：${error.message}`); }
      return;
    }
    if (event.target.closest('[data-label-new]')) {
      const name = document.getElementById('label-manager-name')?.value.trim();
      if (!name) return;
      try {
        const result = await api('/api/label/save', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, color: document.getElementById('label-manager-color')?.value,
            priority_bonus: asNumber(document.getElementById('label-manager-bonus')?.value, 0) }) });
        LABELS.push(result.label);
        LABELS.sort((a, b) => (a.order || 0) - (b.order || 0));
        renderLabelFilterOptions(); modal.querySelector('.label-manager-list').innerHTML = labelManagerRows();
        document.getElementById('label-manager-name').value = '';
        renderQ?.();
      } catch (error) { alert(`新建标记失败：${error.message}`); }
    }
  });
}

async function createAndSelectLabel(name, selected) {
  const clean = String(name || '').trim();
  if (!clean) return;
  let found = LABELS.find(label => label.name === clean);
  if (!found) {
    const result = await api('/api/label/save', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: clean }),
    });
    found = result.label || { name: clean, color: LABEL_PRESETS[LABELS.length % LABEL_PRESETS.length] };
    LABELS = [...LABELS.filter(label => label.name !== clean), found];
  }
  selected.add(found.name);
}

async function saveQuestionLabels(uid, labels) {
  const item = getItemByUid(uid);
  const before = item ? [...(item.labels || [])] : [];
  if (item) item.labels = [...labels];
  try {
    await api('/api/question/labels', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ uid, labels }),
    });
    renderQ();
    if (typeof boardRender === 'function') boardRender();
  } catch (error) {
    if (item) item.labels = before;
    renderQ();
    alert(`保存标记失败：${error.message}`);
  }
}

async function batchAddRemoveLabels(uids, add = [], remove = []) {
  await api('/api/questions/labels', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ uids, add, remove }),
  });
  const addSet = new Set(add), removeSet = new Set(remove);
  getItems().forEach(item => {
    if (!uids.includes(item.uid)) return;
    item.labels = [...new Set([...(item.labels || []), ...add])].filter(label => !removeSet.has(label));
  });
  renderQ();
}

if (typeof document !== 'undefined') {
  document.addEventListener('click', event => {
    const create = event.target.closest?.('[data-lbl-create-open]');
    if (create) {
      event.stopPropagation();
      openCreateLabelsPicker(create);
      return;
    }
    const target = event.target.closest?.('[data-lbl-target]');
    if (target) {
      event.stopPropagation();
      openLabelPicker(target.dataset.lblTarget, target);
      return;
    }
    if (LABEL_PICKER && !event.target.closest('.label-picker-pop')) closeLabelPicker();
    const filter = event.target.closest?.('[data-label-filter],[data-q-label]');
    if (filter) {
      const prefix = filter.dataset.labelFilter || 'q';
      const values = selectedLabelNamesFor(prefix);
      const name = filter.dataset.labelName || filter.dataset.qLabel;
      const next = values.includes(name) ? values.filter(item => item !== name) : [...values, name];
      setSelectedLabelNamesFor(prefix, next);
      labelFilterChanged(prefix);
    }
  });
}

if (typeof module !== 'undefined') module.exports = {
  lblInk, lblChip, labelHex, labelRgb, rgbToHsl, hslToRgb,
};
