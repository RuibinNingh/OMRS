/**
 * 开关：原生 checkbox + role="switch"，键盘空格切换；switchControl({id, label, checked, disabled, state})。
 */
import { html, cls } from '../core/html.js';

export function switchControl({ id, label = '', checked = false, disabled = false, state } = {}) {
  return html`<label class="${cls('ui-switch', disabled && 'is-disabled', state && `is-${state}`)}"><input class="ui-switch__input" type="checkbox" role="switch" id="${id}"${checked ? html` checked` : ''}${disabled ? html` disabled` : ''}><span class="ui-switch__track" aria-hidden="true"></span><span class="ui-switch__label">${label}</span></label>`;
}
