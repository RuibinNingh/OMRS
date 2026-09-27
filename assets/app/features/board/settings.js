/**
 * 展示板版面设置（P7 第 5 步从 assets/board.js 搬来，行为与文案不变）：
 * - 版式字段写入（applyPrintField）与单题题后留白写入（setItemGap），写完记脏、几何类只 relayout、
 *   答案与标记开关立即保存（服务端按它们裁剪内容，必须保存后重新导出）；
 * - 锁定保护（allow）：锁定且改动真的会改旧纸面时才确认；同一轮输入事件里的多次请求共用一个确认框，
 *   确认后本轮去抖保存前不再问（granted），保存完成、重新载入或安全操作后收回（revoke）。
 * 模块不读旧全局：当前板、确认框、保存队列、预览与界面刷新都由调用方注入；旧 board.js 经 boardSettings() 懒创建。
 */
import { CUT_LINES, boardPaperLayoutChanged } from './model.js';

const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };
const clamp = (value, min, max, fallback = 0) => Math.max(min, Math.min(max, num(value, fallback)));

/** 按字段规范化后的新 print；未知字段或值没变返回 null（不记脏、不发请求）。 */
export function boardNormalizePrint(current, field, value) {
  const print = { ...(current || {}) };
  if (field === 'note_ratio') print[field] = clamp(value, 30, 55, 50) / 100;
  else if (field === 'gap_lines') print[field] = clamp(value, 0, 24, 2);
  else if (field === 'answers') print[field] = value === 'append' ? 'append' : 'none';
  else if (field === 'show_labels' || field === 'show_meta' || field === 'cut_label' || field === 'locked') print[field] = !!value;
  else if (field === 'cut_line') print[field] = CUT_LINES.includes(value) ? value : 'dash';
  else return null;
  return print[field] === (current || {})[field] ? null : print;
}

/** 这两个开关会让服务端裁剪导出内容，改完必须立即保存再重新导出；其余版式只重排。 */
export function boardPrintFieldSavesNow(field) { return field === 'answers' || field === 'show_labels'; }

/**
 * deps：detail() 当前板；confirm(title, options) → Promise<bool>；markDirty(kind)；flush() → Promise<bool>；relayout()；
 * 界面钩子 printApplied(field, print)、printRejected()、gapApplied(uid, item, options)、gapRejected(uid, item)。
 */
export function createBoardSettings(deps) {
  const { detail, confirm, markDirty, flush, relayout } = deps;
  const hook = name => (...args) => deps[name]?.(...args);
  const printApplied = hook('printApplied'), printRejected = hook('printRejected');
  const gapApplied = hook('gapApplied'), gapRejected = hook('gapRejected');
  let asking = null;      // 进行中的锁定确认：同一轮输入事件共用
  let granted = false;    // 本轮去抖保存前已确认过版式变更

  const settings = {
    granted: () => granted,
    revoke() { granted = false; },
    /** 锁定保护：不需要确认、或已确认过时直接放行；否则弹一次确认（并发调用共用同一个）。 */
    allow(changes = {}) {
      const board = detail();
      const locked = !!board?.print?.locked || !!changes.print?.locked;
      if (!locked || !boardPaperLayoutChanged(board, changes) || granted) return Promise.resolve(true);
      if (!asking) {
        asking = Promise.resolve(confirm('版式已锁定，确认修改？', {
          hint: '确认后会清空当前纸面记录，打印状态恢复为未打印，需要重新打印全部。',
          okText: '确认修改', cancelText: '保持锁定',
        })).then(ok => { asking = null; if (ok) granted = true; return ok; });
      }
      return asking;
    },
    async applyPrintField(field, value) {
      const board = detail();
      if (!board) return false;
      const print = boardNormalizePrint(board.print, field, value);
      if (!print) return false;
      if (!(await settings.allow({ print }))) { printRejected(); return false; }
      board.print = print;
      printApplied(field, print);
      markDirty('print');
      if (boardPrintFieldSavesNow(field)) await flush();
      else relayout();
      return true;
    },
    /** 单题题后留白：value 为 null / undefined 表示继承板设置。返回写入后的题，被拒或找不到题时返回 null。 */
    async setItemGap(uid, value, options = {}) {
      const board = detail();
      const item = (board?.items || []).find(current => current.uid === uid || current.question_id === uid);
      if (!item || !board) return null;
      const gap = value == null ? null : clamp(value, 0, 48, 0);
      const items = board.items.map(current => (current === item ? { ...item, gap_lines: gap } : current));
      if (!(await settings.allow({ items }))) { gapRejected(uid, item); return null; }
      item.gap_lines = gap;
      relayout();
      markDirty('items');
      gapApplied(uid, item, options);
      return item;
    },
  };
  return settings;
}
