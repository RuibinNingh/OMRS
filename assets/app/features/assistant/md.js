/**
 * 聊天正文的 Markdown：段落、粗体、行内代码（题目 UID / Session / commit 变成引用芯片）、列表、表格、$ / $$ 公式。
 * 公式走 domain/question/markdown.js 的 renderLatexSegment（仓库自带 KaTeX），结果按源码缓存。
 * 输出字符串，由 view 经 raw() 嵌入；refOf(code) 由调用方注入（知道哪些 UID 在题库里）。
 */
import { escape } from '../../core/html.js';
import { renderLatexSegment } from '../../domain/question/markdown.js';

const TEX = new Map();
export function tex(src, display) {
  const key = (display ? 'D' : 'I') + src;
  if (!TEX.has(key)) {
    const out = renderLatexSegment(src, display);
    if (!out.includes('class="math')) TEX.set(key, out);
    return out;
  }
  return TEX.get(key);
}

export function renderInline(src, refOf = code => `<code>${escape(code)}</code>`) {
  const re = /(\$[^$\n]+?\$)|(`[^`\n]+`)|(\*\*[^*\n]+?\*\*)/g;
  const plain = value => escape(value).replace(/\r?\n/g, '<br>');
  let out = '';
  let last = 0;
  let m;
  const text = String(src ?? '');
  while ((m = re.exec(text))) {
    out += plain(text.slice(last, m.index));
    if (m[1]) out += tex(m[1].slice(1, -1), false);
    else if (m[2]) out += refOf(m[2].slice(1, -1));
    else out += `<strong>${renderInline(m[3].slice(2, -2), refOf)}</strong>`;
    last = m.index + m[0].length;
  }
  return out + plain(text.slice(last));
}

const cellsOf = r => r.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
export const isSepRow = r => /^\s*\|?[\s:|-]+\|?\s*$/.test(r) && r.includes('-');

function tableHtml(rows, refOf) {
  let head = null;
  let body = rows;
  if (rows.length >= 2 && isSepRow(rows[1])) { head = cellsOf(rows[0]); body = rows.slice(2); }
  const cell = (tag, c) => `<${tag}>${renderInline(c, refOf)}</${tag}>`;
  return '<table>' + (head ? `<thead><tr>${head.map(c => cell('th', c)).join('')}</tr></thead>` : '')
    + `<tbody>${body.map(r => `<tr>${cellsOf(r).map(c => cell('td', c)).join('')}</tr>`).join('')}</tbody></table>`;
}

export function renderMd(src, { live = false, refOf } = {}) {
  const lines = String(src ?? '').split('\n');
  const blocks = [];
  let para = [];
  const flush = () => { if (para.length) { blocks.push({ t: 'p', h: para.map(l => renderInline(l, refOf)).join('<br>') }); para = []; } };
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    if (!line.trim()) { flush(); continue; }
    if (/^\s*\|/.test(line)) {
      flush();
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      i -= 1;
      blocks.push({ t: 'table', h: tableHtml(rows, refOf) });
      continue;
    }
    const ol = /^\s*\d+\.\s/.test(line);
    const ul = /^\s*[-*]\s/.test(line);
    if (ol || ul) {
      flush();
      const items = [];
      const re = ol ? /^\s*\d+\.\s/ : /^\s*[-*]\s/;
      while (i < lines.length && re.test(lines[i])) items.push(lines[i++].replace(re, ''));
      i -= 1;
      blocks.push({ t: ol ? 'ol' : 'ul', items });
      continue;
    }
    if (/^\s*\$\$/.test(line)) {
      flush();
      let body = line.replace(/^\s*\$\$/, '');
      if (/\$\$\s*$/.test(body)) body = body.replace(/\$\$\s*$/, '');
      else {
        while (i + 1 < lines.length && !/\$\$\s*$/.test(lines[i + 1])) body += '\n' + lines[++i];
        if (i + 1 < lines.length) body += '\n' + lines[++i].replace(/\$\$\s*$/, '');
      }
      blocks.push({ t: 'math', h: tex(body.trim(), true) });
      continue;
    }
    para.push(line);
  }
  flush();
  const caret = '<span class="ast-caret" aria-hidden="true"></span>';
  const out = blocks.map((b, k) => {
    const last = live && k === blocks.length - 1;
    if (b.t === 'p') return `<p>${b.h}${last ? caret : ''}</p>`;
    if (b.t === 'ul' || b.t === 'ol') {
      return `<${b.t}>${b.items.map((x, j) => `<li>${renderInline(x, refOf)}${last && j === b.items.length - 1 ? caret : ''}</li>`).join('')}</${b.t}>`;
    }
    if (b.t === 'table') return `<div class="ast-table">${b.h}</div>${last ? '<span class="ast-caret ast-caret--block" aria-hidden="true"></span>' : ''}`;
    return `<div class="ast-mathblock">${b.h}</div>`;
  }).join('');
  return out || (live ? `<p>${caret}</p>` : '');
}

/** 纯文本摘要（对话列表的第二行）：去掉表格、公式符号与标记。 */
export function plainOf(src) {
  const line = String(src ?? '').split('\n').find(l => l.trim() && !/^\s*\|/.test(l)) || '';
  return line.replace(/\$([^$]+)\$/g, (_, t) => t.replace(/\\([a-z]+)/gi, '$1').replace(/[{}\\]/g, '')).replace(/[`*]/g, '').trim();
}
