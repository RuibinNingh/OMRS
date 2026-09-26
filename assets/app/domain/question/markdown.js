/**
 * 题目 Markdown 渲染（从旧 questions.js 迁入）：段落、表格、Obsidian 图片 `![[a.png|300]]`、`$…$` / `$$…$$` KaTeX。
 * 结果按「换行模式 + 内容哈希」缓存：同一道题在题库画廊、题目弹窗、反馈台、即时练习之间来回切换时只算一次 KaTeX。
 * KaTeX 还没加载时的降级结果（公式显示源码）不进缓存，等 KaTeX 就绪后下一次渲染自然补上。
 * 输出是字符串（旧代码直接拼进 innerHTML）；新代码经 raw() 嵌入模板。图片宽度用 width 属性，不写 style=（check_ui R6）。
 */
import { escape } from '../../core/html.js';

const g = globalThis;
const CACHE_LIMIT = 600;
const cache = new Map();
let hits = 0;
let misses = 0;

/** FNV-1a 32 位，配合长度作缓存键；题面几 KB，算一次远比 KaTeX 便宜。 */
export function hashText(text) {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(36);
}

const katexReady = () => !!(g.katex && typeof g.katex.renderToString === 'function');

/** 题面换行模式：lean（默认）把单个换行当软换行接续；full 保留每一处换行。全站 qview 共用一个偏好，
 * 存 localStorage('omrs-qb-md-mode')（键名沿用旧版）；题库页的「显示设置」经 setMdLineBreakMode 改它，再 qvRerenderAll 重绘。 */
const MD_MODE_KEY = 'omrs-qb-md-mode';
let lineBreak = (() => { try { return g.localStorage?.getItem(MD_MODE_KEY) === 'full' ? 'full' : 'lean'; } catch (error) { return 'lean'; } })();

export const mdLineBreakMode = () => lineBreak;

export function setMdLineBreakMode(mode) {
  lineBreak = mode === 'full' ? 'full' : 'lean';
  try { if (lineBreak === 'full') g.localStorage?.setItem(MD_MODE_KEY, 'full'); else g.localStorage?.removeItem(MD_MODE_KEY); } catch (error) { /* 偏好只在本次会话生效 */ }
  return lineBreak;
}

export const normalizeImageName = raw => String(raw ?? '').trim().split('/').pop().split('\\').pop();

export function renderInlineImage(name, alt, width) {
  const image = normalizeImageName(name);
  const capped = width ? Math.min(Number(width) || 0, 600) : 0;
  const size = capped > 0 ? ` width="${capped}"` : '';
  return `<img class="md-img" src="/api/image?name=${encodeURIComponent(image)}" alt="${escape(alt || image)}" data-omrs-image="${escape(image)}"${size}>`;
}

export function renderLatexSegment(source, display) {
  const latex = String(source ?? '');
  if (katexReady()) {
    try {
      return g.katex.renderToString(latex, { displayMode: !!display, throwOnError: false, strict: 'ignore', trust: false, output: 'html' });
    } catch (error) { /* 落到下面的源码降级 */ }
  }
  return `<span class="math ${display ? 'display' : ''}">${escape(latex)}</span>`;
}

const TOKEN_RE = /(!\[\[[^\]]+?\]\]|!\[[^\]]*\]\([^)]+\)|\$\$[\s\S]+?\$\$|\$[^$\n]+\$)/g;

export function renderMdInline(text = '') {
  const source = String(text ?? '');
  const re = new RegExp(TOKEN_RE.source, 'g');
  let out = '';
  let last = 0;
  let match;
  while ((match = re.exec(source))) {
    out += escape(source.slice(last, match.index));
    const token = match[0];
    let parsed = token.match(/^!\[\[([^\]|]+?)(?:\|(\d+))?\]\]$/);
    if (parsed) out += renderInlineImage(parsed[1], parsed[1], parsed[2] || '');
    else if ((parsed = token.match(/^!\[([^\]]*)\]\(([^)]+)\)$/))) {
      const image = normalizeImageName(parsed[2]);
      out += renderInlineImage(image, parsed[1] || image, '');
    } else if (token.startsWith('$$') && token.endsWith('$$')) out += renderLatexSegment(token.slice(2, -2), true);
    else if (token.startsWith('$') && token.endsWith('$')) out += renderLatexSegment(token.slice(1, -1), false);
    last = re.lastIndex;
  }
  return out + escape(source.slice(last));
}

export function splitMdTableRow(line) {
  const source = String(line ?? '').trim().replace(/^\|/, '').replace(/\|$/, '');
  const cells = [];
  let cell = '';
  for (let i = 0; i < source.length; i += 1) {
    const ch = source[i];
    if (ch === '\\' && source[i + 1] === '|') { cell += '|'; i += 1; } else if (ch === '|') { cells.push(cell.trim()); cell = ''; } else cell += ch;
  }
  cells.push(cell.trim());
  return cells;
}

export function isMdTableSeparator(line) {
  const cells = splitMdTableRow(line);
  return cells.length > 0 && cells.every(cell => /^:?-{3,}:?$/.test(cell));
}

export function renderMdTable(header, rows) {
  const headings = splitMdTableRow(header);
  const body = rows.map(row => {
    const cells = splitMdTableRow(row);
    return `<tr>${headings.map((_, i) => `<td>${renderMdInline(cells[i] || '')}</td>`).join('')}</tr>`;
  }).join('');
  return `<div class="md-table-wrap"><table class="md-table"><thead><tr>${headings.map(cell => `<th>${renderMdInline(cell)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>`;
}

function countDisplayMathDelimiters(line = '') {
  const source = String(line ?? '');
  let count = 0;
  for (let i = 0; i < source.length - 1; i += 1) {
    if (source[i] === '$' && source[i + 1] === '$' && (i === 0 || source[i - 1] !== '\\')) { count += 1; i += 1; }
  }
  return count;
}

function findDisplayMathEnd(lines, start) {
  let delimiters = 0;
  for (let i = start; i < lines.length; i += 1) {
    delimiters += countDisplayMathDelimiters(lines[i]);
    if (delimiters && delimiters % 2 === 0) return i;
  }
  return -1;
}

/** 逐行渲染（不查缓存）。空行 = 分段（`<p class="md-p">`，间距由样式表决定），连续空行只算一段。 */
export function renderMdUncached(text = '', mode) {
  const soft = (mode || mdLineBreakMode()) !== 'full';
  const lines = String(text ?? '').split(/\r?\n/);
  const blocks = [];
  let para = '';
  let pendingSoftJoin = false;
  // 段尾多出来的 <br> 一律削掉，免得「硬换行 / 完整模式 + 紧跟空行」叠出多余空行
  const flush = () => {
    const body = para.replace(/(?:<br>)+$/, '');
    if (body) blocks.push(`<p class="md-p">${body}</p>`);
    para = '';
    pendingSoftJoin = false;
  };
  for (let i = 0; i < lines.length;) {
    if (i + 1 < lines.length && lines[i].includes('|') && isMdTableSeparator(lines[i + 1])) {
      const header = lines[i];
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) { rows.push(lines[i]); i += 1; }
      flush();
      blocks.push(renderMdTable(header, rows));
      continue;
    }
    if (lines[i].trim() === '') {
      flush();
      i += 1;
      while (i < lines.length && lines[i].trim() === '') i += 1;
      continue;
    }
    let source = lines[i];
    let end = i;
    if (countDisplayMathDelimiters(source) % 2 === 1) {
      const close = findDisplayMathEnd(lines, i);
      if (close >= i) { source = lines.slice(i, close + 1).join('\n'); end = close; }
    }
    const hardBreak = / {2,}$/.test(source);
    if (hardBreak) source = source.replace(/ +$/, '');
    if (pendingSoftJoin) para += ' ';
    para += renderMdInline(source);
    pendingSoftJoin = false;
    if (end < lines.length - 1) {
      if (hardBreak || !soft) para += '<br>';
      else pendingSoftJoin = true;
    }
    i = end + 1;
  }
  flush();
  return blocks.join('');
}

/** 带缓存的入口（旧名 renderMdContent 经过渡桥指向这里）。 */
export function renderMd(text = '', mode) {
  const source = String(text ?? '');
  const resolved = (mode || mdLineBreakMode()) === 'full' ? 'full' : 'lean';
  if (!source) return '';
  const key = `${resolved}|${source.length}|${hashText(source)}`;
  const cached = cache.get(key);
  if (cached !== undefined) {
    hits += 1;
    cache.delete(key);
    cache.set(key, cached);   // 最近使用的挪到末尾，淘汰时从头删
    return cached;
  }
  misses += 1;
  const out = renderMdUncached(source, resolved);
  if (katexReady() || !source.includes('$')) {
    cache.set(key, out);
    if (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
  }
  return out;
}

export const mdCacheStats = () => ({ size: cache.size, hits, misses, limit: CACHE_LIMIT });
export function clearMdCache() { cache.clear(); hits = 0; misses = 0; }
