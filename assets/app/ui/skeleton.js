/**
 * 骨架屏：skeleton({lines, avatar, block})；showAfter(el, ms=300) 让加载占位超过 300ms 才出现，
 * 避免「加载中…」一闪而过；返回取消函数（数据先到时调用）。
 */
import { html } from '../core/html.js';

export function skeleton({ lines = 3, avatar = false, block = false, label = '加载中' } = {}) {
  const rows = Array.from({ length: Math.max(1, lines) }, () => html`<span class="ui-skeleton__line"></span>`);
  return html`<div class="ui-skeleton" role="status" aria-label="${label}">${block ? html`<span class="ui-skeleton__block"></span>` : ''}${avatar ? html`<div class="ui-skeleton__row"><span class="ui-skeleton__circle"></span><span class="ui-skeleton__line"></span></div>` : ''}${rows}</div>`;
}

export function showAfter(el, ms = 300) {
  el.hidden = true;
  const timer = setTimeout(() => { el.hidden = false; }, ms);
  return () => clearTimeout(timer);
}
