/**
 * 展示板领域入口。
 * - 纯函数（选板分组、行状态、过滤、最近使用、行模型与点击决策、UID 归一化）在 model.js，P7 第 1 步起归新代码所有；
 * - 选板浮层在 picker.js（模板 picker-view.js、样式 picker.css、过渡期数据来源 source.js），P7 第 4 轮起原生；
 *   新页面经这里的 boardQuickAdd / boardChooseAndAdd 打开它，旧代码经过渡桥 installBoardBridge 挂回的同名全局。
 */
import { boardPickerOpen } from './picker.js';

export * from './model.js';
export { boardPickerOpen, boardPickerClose, boardPickerIsOpen, boardPickerNode, configureBoardPicker } from './picker.js';

/** 「加入展示板」（单题）：anchor 锚定弹出；direct（Shift + 点击）直接进上次的板。 */
export function boardQuickAdd(uid, options) {
  if (!uid || (Array.isArray(uid) && !uid.length)) return undefined;
  return boardPickerOpen(uid, options || {});
}

/** 「加入展示板」（一批）：批量条、收件箱提示条等。 */
export function boardChooseAndAdd(uids, options) {
  if (!Array.isArray(uids) || !uids.length) return undefined;
  return boardPickerOpen(uids, options || {});
}
