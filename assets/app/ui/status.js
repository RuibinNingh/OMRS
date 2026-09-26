/**
 * 局部状态：status({tone:'neutral'|'info'|'success'|'warning'|'danger', text, block})——错误显示在出错位置，
 * 全局错误才用 toast。取代旧代码用行内样式颜色充当状态提示的写法（D11）。
 */
import { html, cls } from '../core/html.js';
import { icon } from './icon.js';

const ICON = { info: 'info', success: 'check-circle', warning: 'alert-triangle', danger: 'alert-circle' };

export function status({ tone = 'neutral', text = '', block = false } = {}) {
  const live = tone === 'danger' ? 'alert' : 'status';
  return html`<p class="${cls('ui-status', tone !== 'neutral' && `ui-status--${tone}`, block && 'ui-status--block')}" role="${live}">${ICON[tone] ? icon(ICON[tone]) : ''}<span class="ui-status__text">${text}</span></p>`;
}

export function dot(tone = 'neutral', label = '') {
  return html`<span class="${cls('ui-dot', tone !== 'neutral' && `ui-dot--${tone}`)}"${label ? html` role="img" aria-label="${label}"` : html` aria-hidden="true"`}></span>`;
}
