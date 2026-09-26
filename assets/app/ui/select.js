/**
 * 选择框：保留原生 <select>（可访问性最好），统一外观与三档高度；修掉旧页 select 文字被裁切（D3）。
 * select({id, options:[{value,label,disabled}|string], value, size, invalid, disabled, label})
 */
import { html, cls } from '../core/html.js';

export function select({ id, options = [], value, size = 'md', invalid = false, disabled = false, label, state } = {}) {
  const c = cls('ui-select', size !== 'md' && `ui-select--${size}`, state && `is-${state}`);
  return html`<select class="${c}" id="${id}"${label ? html` aria-label="${label}"` : ''}${invalid ? html` aria-invalid="true"` : ''}${disabled ? html` disabled` : ''}>${options.map(o => {
    const opt = typeof o === 'object' ? o : { value: o, label: o };
    return html`<option value="${opt.value}"${String(opt.value) === String(value) ? html` selected` : ''}${opt.disabled ? html` disabled` : ''}>${opt.label}</option>`;
  })}</select>`;
}
