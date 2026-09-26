/**
 * 统计：stat({label, value, unit, delta, trend:'up'|'down'|'flat', hint, size:'md'|'lg'})；数字等宽。
 * size:'lg' 用 --text-display，全站只给仪表盘首屏一处用。
 */
import { html, cls } from '../core/html.js';
import { icon } from './icon.js';

export function stat({ label, value, unit, delta, trend = 'flat', hint, size = 'md' } = {}) {
  const arrow = trend === 'up' ? icon('chevron-up') : trend === 'down' ? icon('chevron-down') : '';
  return html`<div class="${cls('ui-stat', size === 'lg' && 'ui-stat--lg')}"><span class="ui-stat__label">${label}</span><span class="ui-stat__value">${value ?? '—'}${unit ? html`<span class="ui-stat__unit">${unit}</span>` : ''}</span>${delta != null ? html`<span class="ui-stat__delta ui-stat__delta--${trend}">${arrow}${delta}</span>` : ''}${hint ? html`<span class="ui-stat__hint">${hint}</span>` : ''}</div>`;
}
