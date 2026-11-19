/** 离线导出复用网页的双星号识别；正文用文本节点拼装。 */
const EXPORT_MATH = /(\$\$[\s\S]+?\$\$|\$[^$\n]+\$)/g;

function appendExportText(parent, text) {
  for (const part of emphasisParts(String(text ?? ''))) {
    const target = part.strong ? document.createElement('strong') : parent;
    for (const value of part.text.split(EXPORT_MATH)) {
      if (!value) continue;
      if (!value.startsWith('$') || !value.endsWith('$') || value.length < 3) {
        target.append(document.createTextNode(value));
        continue;
      }
      const display = value.startsWith('$$') && value.endsWith('$$');
      const width = display ? 2 : 1;
      const latex = value.slice(width, -width);
      const span = document.createElement('span');
      span.className = display ? 'math display' : 'math';
      span.textContent = latex;
      if (typeof window.katex?.render === 'function') {
        try {
          window.katex.render(latex, span, { displayMode: display, throwOnError: false, strict: 'ignore', trust: false, output: 'html' });
        } catch (error) { span.textContent = latex; }
      }
      target.append(span);
    }
    if (part.strong) {
      target.className = 'md-strong';
      parent.append(target);
    }
  }
}

function exportFormulaBreaks(source) {
  const ranges = emphasisRanges(source);
  return Array.from(source.matchAll(EXPORT_MATH), match => {
    const cut = match.index;
    const range = ranges.find(({ start, end }) => start < cut && cut < end - 2);
    if (!range) return [source.slice(0, cut), source.slice(cut)];

    // 断在加粗区间时，两段各保留完整标记。公式紧贴开标记时一起移到下一栏。
    const left = source.slice(range.start + 2, cut).trimEnd();
    if (!left) return [source.slice(0, range.start), source.slice(range.start)];
    const prefix = source.slice(0, range.start + 2) + left + '**' + source.slice(range.start + 2 + left.length, cut);
    return [prefix, '**' + source.slice(cut)];
  }).reverse();
}
