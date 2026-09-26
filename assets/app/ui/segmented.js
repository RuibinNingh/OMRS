/**
 * 分段控件：一组原生 radio（方向键切换由浏览器处理）。segmented({name, label, options:[{value,label,icon,disabled}], value, size})
 */
import { html, cls } from '../core/html.js';
import { icon } from './icon.js';

export function segmented({ name, label = '', options = [], value, size = 'md', disabled = false, state } = {}) {
  return html`<div class="${cls('ui-segmented', size !== 'md' && `ui-segmented--${size}`, state && `is-${state}`)}" role="radiogroup" aria-label="${label}">${options.map(o => html`<label class="ui-segmented__item"><input class="ui-segmented__input" type="radio" name="${name}" value="${o.value}"${String(o.value) === String(value) ? html` checked` : ''}${disabled || o.disabled ? html` disabled` : ''}><span class="ui-segmented__label">${o.icon ? icon(o.icon) : ''}${o.label}</span></label>`)}</div>`;
}
