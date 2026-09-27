/** Label definitions and shared picker / management UI. */
import { raw } from '../../core/html.js';
import { chipHtml, chipsHtml } from './chips.js';
import { openLabelPicker as openPicker, closeLabelPicker, pickerOpen } from './picker.js';
import { openLabelManager, closeLabelManager, managerOpen } from './manager.js';
export { hexKey, hexOf, rgbOf, labelFg, lblInk, chipBackground, contrastRatio, presetColors, defaultColor, normalizeColor, setTokenReader } from './color.js';
export { colorRule, ensureColor, registeredColors } from './sheet.js';
export { chipHtml, chipsHtml, labelObject } from './chips.js';
export { RECENT_KEY, sortLabels, upsertLabel, pickerOptions, readRecent, touchRecent, quickList, nextColor, applyBatch, formValues } from './model.js';
export { allLabels, listLabels, connectLabels, loadLabels, createLabel, batchLabels, saveQuestionLabels } from './state.js';
export { pickerOpen, openLabelManager, managerOpen };
export const labelChip = (name, options = {}) => raw(chipHtml(name, options));
export const labelChips = (names, options = {}) => raw(chipsHtml(Array.isArray(names) ? names : [], options));
export const closePicker = closeLabelPicker;
export const closeManager = closeLabelManager;
export function openLabelPicker(uid, anchor) { if (uid) openPicker(uid, anchor); }
export function openCreateLabelPicker(anchor, { get, onSave } = {}) {
  openPicker('__create__', anchor, { get, onSave, title: '新题目' });
}
let bound = false;
export function bindLabelEvents(doc = document) {
  if (bound) return;
  bound = true;
  doc.addEventListener('click', event => {
    const inside = !!(pickerOpen() && event.composedPath?.().some(node => node?.classList?.contains('label-picker-pop')));
    const target = event.target.closest?.('[data-lbl-target]');
    if (target && !inside) {
      event.stopPropagation();
      openLabelPicker(target.dataset.lblTarget, event.target.closest('.lbl') || target);
      return;
    }
    if (!inside && pickerOpen()) closeLabelPicker();
  }, true);
}
