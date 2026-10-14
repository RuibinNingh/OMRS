/** 成对 LaTeX 定界符转美元符号；规则与 omrs/math_text.py 共用测试夹具。 */
export function normalizeMathDelimiters(value = '') {
  const text = String(value ?? '');
  const re = /(?<fence>^ {0,3}(?:`{3,}|~{3,})[^\n]*)|(?<code>`+)|(?<math>(?<![\\$])\${1,2})(?!\$)|(?<latex>(?<!\\)\\[([])/gm;
  let out = '';
  let position = 0;
  let match;
  while ((match = re.exec(text))) {
    const start = match.index;
    const end = re.lastIndex;
    const token = match[0];
    const kind = Object.keys(match.groups).find(key => match.groups[key] !== undefined);
    out += text.slice(position, start);
    let close;
    if (kind === 'fence') {
      const marker = /^ {0,3}(`+|~+)/.exec(token)[1];
      close = new RegExp(`^ {0,3}${marker[0]}{${marker.length},}[\\t ]*\\r?$`, 'gm');
    } else if (kind === 'code') close = new RegExp('(?<!`)`{' + token.length + '}(?!`)', 'g');
    else if (kind === 'math') close = new RegExp('(?<![\\\\$])\\${' + token.length + '}(?!\\$)', 'g');
    else close = new RegExp(token === '\\(' ? '(?<!\\\\)\\\\\\)' : '(?<!\\\\)\\\\\\]', 'g');
    close.lastIndex = end;
    const closing = close.exec(text);
    if (closing && (kind !== 'latex' || (closing.index > end &&
        (token !== '\\(' || !text.slice(end, closing.index).includes('\n'))))) {
      const body = text.slice(end, closing.index);
      const delimiter = token === '\\(' ? '$' : '$$';
      out += kind === 'latex' ? delimiter + body + delimiter : text.slice(start, close.lastIndex);
      position = close.lastIndex;
    } else {
      position = kind === 'fence' ? text.length : end;
      out += text.slice(start, position);
    }
    re.lastIndex = position;
  }
  return out + text.slice(position);
}
