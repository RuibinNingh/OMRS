/** 已校验的静态配图仅在图片上下文预览；源码不进入编辑器或页面DOM。 */
import { html } from '../../core/html.js';

export function draftSvgView(block) {
  const diagram = block.svg || {};
  return html`<div class="drf-block-image"><img class="md-img" src="${diagram.src || ''}" alt="${diagram.title || 'SVG配图'}"></div>
    <p class="drf-hint">SVG配图 · ${diagram.title || ''} · 图高 ${diagram.print_height_mm ?? '—'}mm${diagram.min_font_pt != null ? ` · 最小文字 ${diagram.min_font_pt.toFixed(1)}pt` : ''}</p>
    <p class="drf-hint">请核对图意、标注遮挡和信息密度；入库保留向量原件。</p>
    ${(diagram.warnings || []).map(warning => html`<p class="drf-hint">${warning}</p>`)}`;
}
