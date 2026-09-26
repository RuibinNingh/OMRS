/**
 * 展示板（过渡期适配器）：「加入展示板」的选板浮层仍在旧 board_picker.js（boardQuickAdd / boardChooseAndAdd），
 * 新页面只经这里调用；展示板页迁移（P7）时换实现。
 */
const g = globalThis;

export function boardQuickAdd(uid, options) {
  if (uid && typeof g.boardQuickAdd === 'function') return g.boardQuickAdd(uid, options || {});
  return undefined;
}

export function boardChooseAndAdd(uids, options) {
  if (Array.isArray(uids) && uids.length && typeof g.boardChooseAndAdd === 'function') return g.boardChooseAndAdd(uids, options || {});
  return undefined;
}
