/**
 * 标记颜色的运行时样式表：芯片、色板、颜色圆点只写 data-lbl-c="rrggbb"，每种用到的颜色在这里登记一条
 * [data-lbl-c="rrggbb"]{--lbl-c;--lbl-fg;--lbl-rgb;--lbl-ink-l;--lbl-ink-d}，插进 <style id="omrs-label-colors"> 的 @layer domain 块。
 * 旧 styles.css 里 .lbl 的默认值在 legacy 层，domain 层压得住（层序决定，不看特异度）。没有 document 时（node 单测）只记账。
 */
import { hexKey, hexOf, rgbOf, labelFg, lblInk } from './color.js';

const rules = new Map();   // 'rrggbb' → 规则文本
let block = null;          // CSSLayerBlockRule

export function colorRule(key) {
  const hex = hexOf(key);
  const [r, g, b] = rgbOf(hex);
  return `[data-lbl-c="${key}"]{--lbl-c:${hex};--lbl-fg:${labelFg(hex)};--lbl-rgb:${r},${g},${b};--lbl-ink-l:${lblInk(hex, 'light')};--lbl-ink-d:${lblInk(hex, 'dark')}}`;
}

function layer(doc) {
  if (block && block.parentStyleSheet?.ownerNode?.isConnected) return block;
  const el = doc.createElement('style');
  el.id = 'omrs-label-colors';
  el.textContent = '@layer domain {}';
  doc.head.append(el);
  block = el.sheet.cssRules[0];
  rules.forEach(rule => block.insertRule(rule, block.cssRules.length));
  return block;
}

/** 登记一种颜色，返回写进 data-lbl-c 的键；不合法返回 ''（芯片退回 .lbl 的默认灰）。 */
export function ensureColor(value) {
  const key = hexKey(value);
  if (!key || rules.has(key)) return key;
  const doc = globalThis.document;
  let target = null;
  try { target = doc?.head ? layer(doc) : null; } catch (error) { console.error('[domain/labels] 颜色样式表创建失败', error); }
  const rule = colorRule(key);
  rules.set(key, rule);
  try { target?.insertRule(rule, target.cssRules.length); } catch (error) { console.error('[domain/labels] 颜色规则插入失败', error); }
  return key;
}

export const registeredColors = () => [...rules.keys()];
