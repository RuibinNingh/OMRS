/** 题目正文和离线导出共用的双星号规则。偏移基于源码，供打印换栏时保留加粗。 */
const TOKENS = /^(?: {0,3})(?<fence>\x60{3,}|~{3,})(?<suffix>[^\n]*)|(?<opaque>!\[\[[^\]\n]+\]\]|!\[[^\]\n]*\]\([^)\n]+\)|\$\$[\s\S]+?\$\$|\$[^$\n]+\$|\\\([^\n]*?\\\)|\\\[[\s\S]*?\\\]|(?<!\x60)(?<backticks>\x60+)(?!\x60)[^\r\n]*?(?<!\x60)\k<backticks>(?!\x60))|(?<newline>\r?\n)|(?<stars>\*+)/gm;

function escaped(source, index) {
  let start = index;
  while (start > 0 && source[start - 1] === '\\') start -= 1;
  return (index - start) % 2 === 1;
}

export function emphasisRanges(source) {
  if (!source.includes('**')) return [];
  const ranges = [];
  let start = -1;
  let fence = '';
  for (const match of source.matchAll(TOKENS)) {
    const { fence: marker, suffix, newline, opaque, stars } = match.groups;
    if (marker) {
      if (!fence) fence = marker;
      else if (marker[0] === fence[0] && marker.length >= fence.length && !suffix.trim()) fence = '';
    }
    if (marker || fence || newline || opaque?.includes('\n')) {
      start = -1;
      continue;
    }
    const index = match.index;
    if (stars !== '**' || escaped(source, index)) continue;
    const before = source.slice(Math.max(0, index - 2), index).match(/.$/su)?.[0] || ' ';
    const after = source.slice(index + 2, index + 4).match(/^./su)?.[0] || ' ';
    const beforeSpace = /\s/u.test(before), afterSpace = /\s/u.test(after);
    const beforePunctuation = /[\p{P}\p{S}]/u.test(before), afterPunctuation = /[\p{P}\p{S}]/u.test(after);
    // 中文解析常写成「**答案：**B」或把引号、行内公式紧贴开标记。
    const opens = !afterSpace && (!afterPunctuation || beforeSpace || beforePunctuation || /[\p{Ps}\p{Pi}$]/u.test(after));
    if (start >= 0 && !beforeSpace) {
      ranges.push({ start, end: index + 2 });
      start = -1;
    } else if (opens) {
      start = index;
    }
  }
  return ranges;
}

export function emphasisParts(source) {
  const parts = [];
  let cursor = 0;
  for (const { start, end } of emphasisRanges(source)) {
    if (cursor < start) parts.push({ text: source.slice(cursor, start), strong: false });
    parts.push({ text: source.slice(start + 2, end - 2), strong: true });
    cursor = end;
  }
  if (cursor < source.length) parts.push({ text: source.slice(cursor), strong: false });
  return parts;
}

export function plainEmphasis(source) {
  return emphasisParts(String(source ?? '')).map(part => part.text).join('');
}
