/** 说明与备注共用的安全Markdown子集；保留公式和受控题图，普通HTML转义。 */
import { escape } from '../core/html.js';
import { renderMd, renderMdInline } from './question/markdown.js';
import { normalizeMathDelimiters } from './question/math-text.js';

const TOKENS = /(!\[\[[^\]]+\]\]|!\[[^\]]*\]\([^)]+\)|\$\$[\s\S]+?\$\$|\$[^$\n]+\$|`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;

function inline(source, mode) {
  const plain = text => escape(text).replace(/ {2,}\n/g, '<br>').replace(/\n/g, mode === 'lean' ? ' ' : '<br>');
  let out = '', last = 0;
  for (const match of source.matchAll(new RegExp(TOKENS.source, 'g'))) {
    out += plain(source.slice(last, match.index));
    const token = match[0];
    if (token.startsWith('!') || token.startsWith('$')) out += renderMdInline(token);
    else if (token.startsWith('`')) out += `<code>${escape(token.slice(1, -1))}</code>`;
    else if (token.startsWith('**')) out += `<strong>${inline(token.slice(2, -2), mode)}</strong>`;
    else if (token.startsWith('*')) out += `<em>${inline(token.slice(1, -1), mode)}</em>`;
    else {
      const link = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      out += link && /^(https?:\/\/|#)/i.test(link[2]) ? `<a href="${escape(link[2])}" target="_blank" rel="noopener noreferrer">${escape(link[1])}</a>` : plain(token);
    }
    last = match.index + token.length;
  }
  return out + plain(source.slice(last));
}

export function richMarkdown(source = '', mode = 'full') {
  const lines = normalizeMathDelimiters(source).split(/\r?\n/), out = [];
  let paragraph = [];
  const flush = () => {
    if (!paragraph.length) return;
    out.push(paragraph[0].includes('|') && paragraph[1]?.match(/^\s*\|?\s*:?-+/)
      ? renderMd(paragraph.join('\n'), mode) : `<p class="md-p">${inline(paragraph.join('\n'), mode)}</p>`);
    paragraph = [];
  };
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const fence = line.match(/^ {0,3}(`{3,}|~{3,})/);
    if (fence) {
      flush();
      const code = [], close = new RegExp(`^ {0,3}${fence[1][0]}{${fence[1].length},}\\s*$`);
      while (++i < lines.length && !close.test(lines[i])) code.push(lines[i]);
      out.push(`<pre><code>${escape(code.join('\n'))}</code></pre>`);
      continue;
    }
    // 多行展示公式作为完整段落输入，公式内的 #、- 和空行不能变成Markdown块。
    if (line.trim() === '$$') {
      const end = lines.findIndex((value, index) => index > i && value.trim() === '$$');
      if (end > i) {
        flush();
        out.push(inline(lines.slice(i, end + 1).join('\n'), mode));
        i = end;
        continue;
      }
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flush();
      const n = heading[1].length;
      out.push(`<h${n}>${inline(heading[2], mode)}</h${n}>`);
      continue;
    }
    if (/^\s*(?:[-*+] |\d+\. )/.test(line)) {
      flush();
      const ordered = /^\s*\d+\./.test(line), list = [], pattern = ordered ? /^\s*\d+\. (.*)$/ : /^\s*[-*+] (.*)$/;
      while (i < lines.length && pattern.test(lines[i])) {
        list.push(`<li>${inline(lines[i].replace(pattern, '$1'), mode)}</li>`);
        i += 1;
      }
      i -= 1;
      const tag = ordered ? 'ol' : 'ul';
      out.push(`<${tag}>${list.join('')}</${tag}>`);
      continue;
    }
    if (/^>\s?/.test(line)) { flush(); out.push(`<blockquote>${inline(line.replace(/^>\s?/, ''), mode)}</blockquote>`); continue; }
    if (!line.trim()) flush(); else paragraph.push(line);
  }
  flush();
  return out.join('');
}
