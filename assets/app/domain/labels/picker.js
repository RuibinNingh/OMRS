import { questionItem, questionRef } from '../question/ref.js';
/** Shared label picker used in question views and create forms. */
import { escape as escapeHtml, escape as escapeAttr, raw as asHtml } from '../../core/html.js';
import { render as renderHtml } from '../../core/dom.js';
import { hostGuest, releaseGuest } from '../../ui/overlay.js';
import { toast } from '../../ui/toast.js';
import { chipHtml } from './chips.js';
import { pickerOptions as labelPickerOptions } from './model.js';
import { allLabels, quickLabels, createLabel, saveQuestionLabels } from './state.js';
import { openLabelManager } from './manager.js';
let LABEL_PICKER = null;
export const pickerOpen = () => !!LABEL_PICKER?.isConnected;
function labelHostLayer(node, close) {
  hostGuest(node, { close, escape: true });
}
function labelReleaseLayer(node) {
  if (node) releaseGuest(node);
}
export function closeLabelPicker() {
  const node = LABEL_PICKER;
  LABEL_PICKER = null;
  if (!node) return;
  node.remove();
  labelReleaseLayer(node);
}
// openLabelPicker(uid, anchorEl, {get: () => names, onSave: names => Promise, title})
export function openLabelPicker(value, anchor, config = {}) {
  const item = questionItem(value);
  const uid = item?.uid || String(value || '');
  let ref;
  try { ref = typeof config.onSave === 'function' ? null : questionRef(item); }
  catch (error) { toast(error.message, { kind: 'error' }); return; }
  if (LABEL_PICKER && LABEL_PICKER.dataset.uid === String(uid)) { closeLabelPicker(); return; }
  closeLabelPicker();
  const readLabels = typeof config.get === 'function' ? config.get : () => (item?.labels || []);
  const saveLabels = typeof config.onSave === 'function' ? config.onSave : labels => saveQuestionLabels(ref, labels);
  const initial = [...(readLabels() || [])];
  const current = new Set(initial);
  const box = document.createElement('div');
  box.className = 'label-picker-pop';
  box.dataset.uid = uid;
  renderHtml(box, asHtml( `<div class="label-picker-head"><span>标记</span><small>${escapeHtml(config.title || uid || '')}</small></div>
    <input class="ui-input label-picker-search" placeholder="搜索或输入新标记，回车创建…" autocomplete="off">
    <div class="label-picker-options"></div>
    <div class="label-picker-recent"></div>
    <div class="label-picker-foot"><button type="button" class="ui-btn ui-btn--sm ui-btn--ghost" data-lbl-manage>管理标记…</button><span class="hint">↑↓ 移动 · 空格切换 · Esc 关闭</span><button type="button" class="ui-btn ui-btn--sm ui-btn--primary" data-lbl-save>完成</button></div>`));
  labelHostLayer(box, closeLabelPicker);
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
  const paintOptions = () => {
    const { raw: query, create, matches } = labelPickerOptions(allLabels(), search.value);
    renderHtml(optionsBox, asHtml(
      (create ? `<button type="button" class="label-picker-option new" data-lbl-new="${escapeAttr(query)}"><span class="check">＋</span>新建「${escapeHtml(query)}」并选中</button>` : '') +
      (matches.map(label => `<button type="button" class="label-picker-option ${current.has(label.name) ? 'selected' : ''}" data-lbl-name="${escapeAttr(label.name)}"><span class="check">${current.has(label.name) ? '✓' : ''}</span>${chipHtml(label)}<span class="cnt">${label.count ?? ''}</span></button>`).join('') ||
        (query ? '' : '<div class="label-picker-empty">还没有标记：输入名称后回车即可创建。</div>'))));
    const quick = quickLabels(4).filter(label => !current.has(label.name));
    renderHtml(recentBox, asHtml(quick.length ? `<span>快速：</span>${quick.map(label => chipHtml(label, { uid: '' })).join('')}` : ''));
    recentBox.style.display = quick.length ? '' : 'none';
    activeIndex = Math.max(0, Math.min(activeIndex, Math.max(0, optionNodes().length - 1)));
    optionNodes().forEach((node, index) => node.classList.toggle('keyboard-active', index === activeIndex));
  };
  paintOptions();
  requestAnimationFrame(() => search.focus());
  search.addEventListener('input', () => { activeIndex = 0; paintOptions(); });
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
      paintOptions();
      return;
    }
    const quick = event.target.closest('.label-picker-recent [data-lbl-name]');
    if (quick) { current.add(quick.dataset.lblName); paintOptions(); return; }
    const create = event.target.closest('[data-lbl-new]');
    if (create) {
      try { await createLabel(create.dataset.lblNew, current); search.value = ''; paintOptions(); }
      catch (error) { toast(`新建标记失败：${error.message}`, { kind: 'error' }); }
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

