/**
 * 标记颜色（纯函数，node 可测）：规范化、RGB / HSL 换算、相对亮度与对比度、solid 变体前景、soft / print 变体的文字色钳制。
 * 用户保存的 color 永远不改，这里只算显示用的派生色。本目录的 JS 里没有颜色字面量：预设色与 solid 前景色是 tokens.css 的
 * --lbl-preset-1…10、--lbl-fg-dark / --lbl-fg-light，经 presetColors() 读取或以 var() 引用。
 */
const HEX3 = /^[0-9a-f]{3}$/i;
const HEX6 = /^[0-9a-f]{6}$/i;
const SLATE = [100, 116, 139];   // 颜色缺失时按默认灰算前景（与 .lbl 的默认 --lbl-rgb 相同）

/** '#abc' / 'ABC' / '#aabbcc' → 'aabbcc'（小写、不带 #）；不合法返回 ''。 */
export function hexKey(value) {
  const raw = String(value || '').trim().replace(/^#/, '');
  if (HEX3.test(raw)) return raw.split('').map(ch => ch + ch).join('').toLowerCase();
  if (HEX6.test(raw)) return raw.toLowerCase();
  return '';
}
export const hexOf = key => (key ? `#${key}` : '');
export function rgbOf(value) {
  const key = hexKey(value);
  return key ? [0, 2, 4].map(i => parseInt(key.slice(i, i + 2), 16)) : null;
}

export function rgbToHsl(r, g, b) {
  r /= 255; g /= 255; b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;
  if (max !== min) {
    const d = max - min;
    s = l > .5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h /= 6;
  }
  return [h, s, l];
}

export function hslToRgb(h, s, l) {
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

export const rgbHex = rgb => `#${rgb.map(v => Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')).join('')}`;

export function relativeLuminance(rgb) {
  const linear = rgb.map(value => { const v = value / 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; });
  return .2126 * linear[0] + .7152 * linear[1] + .0722 * linear[2];
}

export function contrastRatio(a, b) {
  const l1 = relativeLuminance(a);
  const l2 = relativeLuminance(b);
  return (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05);
}

/** solid 变体的前景：相对亮度 > .55 用深色、否则用白色（浅黄底不配白字）。返回 token 引用。 */
export const labelFg = value => (relativeLuminance(rgbOf(value) || SLATE) > .55 ? 'var(--lbl-fg-dark)' : 'var(--lbl-fg-light)');

/** 芯片淡底：用户色按主题的 α 合成在 surface-1 上（浅色 16% 叠白，深色 24% 叠 surface-1）。 */
export function chipBackground(value, theme) {
  const base = theme === 'dark' ? [33, 31, 29] : [255, 255, 255];
  const alpha = theme === 'dark' ? .24 : .16;
  return (rgbOf(value) || SLATE).map((v, i) => Math.round(v * alpha + base[i] * (1 - alpha)));
}

/** soft / print 变体的文字色：只钳同色相的亮度，让淡底上的小字达到 WCAG AA（4.5:1）。 */
export function lblInk(value, theme) {
  const [h, s] = rgbToHsl(...(rgbOf(value) || SLATE));
  const background = chipBackground(value, theme);
  const candidates = [];
  if (theme === 'dark') { for (let l = .98; l >= .46; l -= .01) candidates.push(hslToRgb(h, Math.max(s, .35), l)); candidates.push([255, 255, 255]); }
  else { for (let l = .02; l <= .58; l += .01) candidates.push(hslToRgb(h, Math.max(s, .35), l)); candidates.push([0, 0, 0]); }
  const good = candidates.find(rgb => contrastRatio(rgb, background) >= 4.5);
  return rgbHex(good || candidates.sort((a, b) => contrastRatio(b, background) - contrastRatio(a, background))[0]);
}

// 预设色：tokens.css 的 --lbl-preset-1…10。读取函数可替换（node 单测传入解析 tokens.css 的版本）。
export const PRESET_COUNT = 10;
let readToken = name => {
  const doc = globalThis.document;
  return doc && typeof getComputedStyle === 'function' ? getComputedStyle(doc.documentElement).getPropertyValue(name).trim() : '';
};
export function setTokenReader(fn) { readToken = typeof fn === 'function' ? fn : readToken; }
export const presetColors = () => Array.from({ length: PRESET_COUNT }, (_, i) => hexOf(hexKey(readToken(`--lbl-preset-${i + 1}`)))).filter(Boolean);
/** 默认色（颜色缺失或不合法时）：第 9 个预设（灰）。 */
export const defaultColor = () => presetColors()[8] || '';
/** 规范成 '#rrggbb'，不合法时给默认色。 */
export const normalizeColor = value => hexOf(hexKey(value)) || defaultColor();
