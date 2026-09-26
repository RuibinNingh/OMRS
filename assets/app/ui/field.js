/**
 * 表单字段：field({label, id, hint, error, required, control, inline}) 统一 label、提示、错误的位置；
 * input({...}) / textarea({...}) 产出控件。错误时控件应带 invalid:true，读屏经 aria-describedby 读到错误文字。
 */
import { html, cls } from '../core/html.js';

export function field({ label, id, hint, error, required = false, control, inline = false } = {}) {
  return html`<div class="${cls('ui-field', error && 'is-invalid', inline && 'ui-field--inline')}">
${label ? html`<label class="ui-field__label" for="${id}">${label}${required ? html`<span class="ui-field__req" aria-hidden="true">*</span>` : ''}</label>` : ''}
${control}
${error ? html`<p class="ui-field__error" id="${id}-msg" role="alert">${error}</p>` : hint ? html`<p class="ui-field__hint" id="${id}-msg">${hint}</p>` : ''}
</div>`;
}

const common = ({ id, name, invalid, disabled, readonly, describedBy, state, label }) => html` id="${id}"${name ? html` name="${name}"` : ''}${label ? html` aria-label="${label}"` : ''}${invalid ? html` aria-invalid="true"` : ''}${describedBy ? html` aria-describedby="${describedBy}"` : ''}${disabled ? html` disabled` : ''}${readonly ? html` readonly` : ''}${state ? html` data-state="${state}"` : ''}`;

export function input(o = {}) {
  const c = cls('ui-input', o.size && o.size !== 'md' && `ui-input--${o.size}`, o.state && `is-${o.state}`);
  return html`<input class="${c}" type="${o.type || 'text'}" value="${o.value ?? ''}" placeholder="${o.placeholder || ''}"${common(o)}>`;
}

export function textarea(o = {}) {
  const c = cls('ui-textarea', o.state && `is-${o.state}`);
  return html`<textarea class="${c}" rows="${o.rows || 4}" placeholder="${o.placeholder || ''}"${common(o)}>${o.value ?? ''}</textarea>`;
}
