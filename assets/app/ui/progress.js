/**
 * 进度：原生 <progress>（无需行内样式）。progress({value, max, label, tone, size, meta})；value 为 null 时是不定进度。
 * spinner({label, size}) 用于按钮外的小范围等待。
 */
import { html, cls } from '../core/html.js';

export function progress({ value = null, max = 100, label = '进度', tone = 'accent', size = 'md', meta } = {}) {
  const bar = html`<progress class="${cls('ui-progress', tone !== 'accent' && `ui-progress--${tone}`, size !== 'md' && `ui-progress--${size}`)}" aria-label="${label}" max="${max}"${value == null ? '' : html` value="${value}"`}></progress>`;
  if (!meta) return bar;
  return html`<div class="ui-progress-field"><div class="ui-progress-field__meta"><span>${label}</span><span>${meta}</span></div>${bar}</div>`;
}

export function spinner({ label = '加载中', size = 'md' } = {}) {
  return html`<span class="${cls('ui-spinner', size !== 'md' && `ui-spinner--${size}`)}" role="status" aria-label="${label}"></span>`;
}
