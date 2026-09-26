/**
 * 标记芯片（字符串模板：旧代码直接拼，新代码经 raw() 嵌入）。签名与结构同旧 labels.js 的 lblChip / lblChips，
 * 颜色改写 data-lbl-c（sheet.js 登记运行时规则），不写 style=。
 * chipHtml(label | name, {variant:'soft'|'solid'|'print', solid, print, lg, dim})
 * chipsHtml(names, {add, max, uid, lg, variant}) —— add 追加「＋」入口；max 超出显示 +N；uid 包一层委托容器（点芯片开该题的选择器）。
 */
import { escape } from '../../core/html.js';
import { ensureColor } from './sheet.js';

const defs = () => (typeof LABELS !== 'undefined' && Array.isArray(LABELS) ? LABELS : []);

/** 名称或定义 → 定义；找不到时只有名字（颜色空 → 默认灰）。list 默认读旧 labels.js 的 LABELS。 */
export function labelObject(label, list = defs()) {
  if (typeof label === 'string') return list.find(item => item.name === label) || { name: label, color: '' };
  return label || { name: '', color: '' };
}

export function chipHtml(label, options = {}, list) {
  const item = labelObject(label, list);
  const name = String(item.name || '').trim();
  if (!name) return '';
  const classes = ['lbl'];
  if (options.variant === 'solid' || options.solid) classes.push('solid');
  if (options.variant === 'print' || options.print) classes.push('print');
  if (options.lg) classes.push('lg');
  if (options.dim) classes.push('dim');
  const key = ensureColor(item.color);
  return `<span class="${classes.join(' ')}"${key ? ` data-lbl-c="${key}"` : ''} data-lbl-name="${escape(name)}" title="${escape(name)}">${escape(name)}</span>`;
}

export function chipsHtml(labels, options = {}, list) {
  const values = Array.isArray(labels) ? labels.filter(Boolean) : [];
  const max = options.max || 0;
  const shown = max && values.length > max ? values.slice(0, max) : values;
  let out = shown.map(name => chipHtml(name, options, list)).join('');
  if (max && values.length > max) out += `<span class="lbl add" title="${escape(values.slice(max).join('、'))}">+${values.length - max}</span>`;
  if (options.add) out += `<span class="lbl add${options.lg ? ' lg' : ''}" data-lbl-add="1" title="打标记">${values.length ? '＋' : '＋ 标记'}</span>`;
  if (options.uid) out = `<span class="lbl-row" data-lbl-target="${escape(options.uid)}">${out}</span>`;
  return out;
}
