/**
 * 标签：tag({label, tone:'neutral'|'accent'|'success'|'warning'|'danger'|'info', icon, removable, removeAction})
 * 只做展示；可移除时带一个 data-action 按钮，由调用方处理。
 */
import { html, cls } from '../core/html.js';
import { icon as svg } from './icon.js';

export function tag({ label = '', tone = 'neutral', icon, removable = false, removeAction = '', title } = {}) {
  return html`<span class="${cls('ui-tag', tone !== 'neutral' && `ui-tag--${tone}`)}"${title ? html` title="${title}"` : ''}>${icon ? svg(icon) : ''}<span class="ui-tag__label">${label}</span>${removable ? html`<button type="button" class="ui-tag__remove" aria-label="移除 ${label}"${removeAction ? html` data-action="${removeAction}"` : ''}>${svg('x')}</button>` : ''}</span>`;
}
