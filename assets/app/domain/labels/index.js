/**
 * 标记领域（P5 第 4 轮起由 domain/labels.js 扩成本目录）：芯片 chips.js（data-lbl-c + 运行时样式表 sheet.js，不写 style=）、
 * 颜色 color.js（预设色读 tokens.css）、选择器与管理的数据部分 model.js。文档：AI/frontend/library.md「标记」。
 * 定义列表仍是旧 labels.js 的 LABELS；选择器浮层、管理弹层、新建与批量增删的 DOM 与写接口仍在旧 labels.js，这里转调。
 * 旧代码经过渡桥 installLabelsBridge 拿到同名全局（lblChip、lblChips、labelHex、nextLabelColor……）。
 */
import { raw } from '../../core/html.js';
import { chipHtml, chipsHtml } from './chips.js';

export { hexKey, hexOf, rgbOf, labelFg, lblInk, chipBackground, contrastRatio, presetColors, defaultColor, normalizeColor, setTokenReader } from './color.js';
export { colorRule, ensureColor, registeredColors } from './sheet.js';
export { chipHtml, chipsHtml, labelObject } from './chips.js';
export { RECENT_KEY, sortLabels, upsertLabel, pickerOptions, readRecent, touchRecent, quickList, nextColor, applyBatch, formValues } from './model.js';

const g = globalThis;
const fn = name => (typeof g[name] === 'function' ? g[name] : null);

/** 全部定义（含归档）/ 未归档的定义。 */
export const allLabels = () => (typeof LABELS !== 'undefined' && Array.isArray(LABELS) ? LABELS : []);
export const listLabels = () => allLabels().filter(item => !item.archived);

export const labelChip = (name, options = {}) => raw(chipHtml(name, options));
export const labelChips = (names, options = {}) => raw(chipsHtml(Array.isArray(names) ? names : [], options));

/** 标记选择器（旧 labels.js 的浮层 LABEL_PICKER）是否打开：打开时页面快捷键让位。宿主对话框关闭时浮层随之移除，按「仍在文档里」判定。 */
export const pickerOpen = () => typeof LABEL_PICKER !== 'undefined' && !!LABEL_PICKER && LABEL_PICKER.isConnected !== false;
export function closePicker() { if (pickerOpen()) fn('closeLabelPicker')?.(); }
export function openLabelPicker(uid, anchor) { if (uid) fn('openLabelPicker')?.(uid, anchor); }
export function openLabelManager() { return fn('openLabelManager')?.(); }
/** 标记管理（旧 labels.js 的 .modal-overlay#label-manager）是否打开 / 关闭它：全局 Esc 用（legacy-bridge 的 installEscapeBridge）。 */
export const managerOpen = () => !!fn('labelManagerOpen')?.();
export function closeManager() { fn('closeLabelManager')?.(); }
/** 新建标记（旧 createAndSelectLabel，已存在则直接返回）。 */
export async function createLabel(name) { const create = fn('createAndSelectLabel'); return create ? create(name, null) : null; }
/** 批量增删标记（旧 batchAddRemoveLabels：写接口、就地更新题目、重载定义、刷新各视图），失败时抛出。 */
export async function batchLabels(uids, add, remove) { const run = fn('batchAddRemoveLabels'); return run ? run(uids, add, remove) : null; }
