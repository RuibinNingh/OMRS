/* 仅局部适配不可断开的公式与宽表格；正文始终保持手机字号，不裁掉内容。 */
window.omrsFitPaper = paper => {
  const contentWidth = el => {
    const style = getComputedStyle(el);
    return el.getBoundingClientRect().width - ['paddingLeft', 'paddingRight', 'borderLeftWidth', 'borderRightWidth']
      .reduce((sum, key) => sum + (parseFloat(style[key]) || 0), 0);
  };
  const availableWidth = el => {
    for (let parent = el.parentElement; parent; parent = parent.parentElement) {
      if (parent === paper || !['inline', 'contents'].includes(getComputedStyle(parent).display)) return contentWidth(parent);
    }
    return contentWidth(paper);
  };
  const extent = el => {
    const box = el.getBoundingClientRect();
    let width = [...el.querySelectorAll('*')].reduce((width, child) =>
      Math.max(width, child.getBoundingClientRect().right - box.left), box.width);
    // 旧nobr公式的文字可能超出带固定宽度的span，元素矩形本身不会反映它。
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT), range = document.createRange();
    while (walker.nextNode()) {
      range.selectNodeContents(walker.currentNode);
      width = Math.max(width, range.getBoundingClientRect().right - box.left);
    }
    return width;
  };
  const fit = (el, formula) => {
    const available = availableWidth(el);
    if (extent(el) <= available) return false;
    // zoom参与Chromium布局，缩放后的高度会留在文档流中，后续段落不会重叠。
    if (formula) {
      el.style.display = 'inline-block';
      el.style.width = 'max-content';
      el.style.maxWidth = 'none';
    }
    const style = getComputedStyle(el);
    const margins = (parseFloat(style.marginLeft) || 0) + (parseFloat(style.marginRight) || 0);
    el.style.zoom = Math.min(1, Math.max(1, available - 1) / (extent(el) + margins));
    return true;
  };
  // 表内公式跟整张表一起适配，保留行列关系，避免重复缩放。
  const formulas = [...paper.querySelectorAll('mjx-container, .math')]
    .filter(el => !el.closest('table') && !el.parentElement.closest('mjx-container, .math'));
  const tables = [...paper.querySelectorAll('table')].filter(el => !el.parentElement.closest('table'));
  return { fitted_formulas: formulas.filter(el => fit(el, true)).length,
    fitted_tables: tables.filter(el => fit(el, false)).length };
};
