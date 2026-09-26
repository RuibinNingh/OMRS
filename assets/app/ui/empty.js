/**
 * 空状态：empty({icon, title, hint, action:{label, action, variant}, compact, bordered})。
 * 必须说明「为什么是空的」（title）和「下一步做什么」（hint + 一个主操作）。取代各页零散的 empty 类（D5）。
 */
import { html, cls } from '../core/html.js';
import { icon as svg } from './icon.js';
import { button } from './button.js';

export function empty({ icon = 'inbox', title = '', hint = '', action, compact = false, bordered = false } = {}) {
  return html`<div class="${cls('ui-empty', compact && 'ui-empty--compact', bordered && 'ui-empty--bordered')}"><span class="ui-empty__icon">${svg(icon)}</span><p class="ui-empty__title">${title}</p>${hint ? html`<p class="ui-empty__hint">${hint}</p>` : ''}${action ? html`<div class="ui-empty__action">${button({ variant: 'primary', ...action })}</div>` : ''}</div>`;
}
