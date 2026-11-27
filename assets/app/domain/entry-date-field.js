import { html } from '../core/html.js';
import { button } from '../ui/button.js';
import { field, input } from '../ui/field.js';
import { select } from '../ui/select.js';
import { ENTRY_DATE_OPTIONS, entryDateDraft, entryDateError, entryDateOf } from './entry-date.js';

export function entryDateField({ id, action, filters, draft }) {
  const bounds = entryDateDraft(filters, draft);
  const error = bounds && entryDateError(bounds);
  const errorId = `${id}-error`;
  const dateField = (key, label) => {
    const inputId = `${id}-${key}`;
    return html`<div data-change="${action}" data-arg="${key}">${field({ label, id: inputId, control: input({
      id: inputId, type: 'date', value: bounds[key], invalid: !!error, describedBy: error ? errorId : undefined,
    }) })}</div>`;
  };
  return html`<div class="entry-date-field" data-key="${id}">
    <div class="entry-date-field__mode" data-change="${action}" data-arg="mode">${field({ id, label: '录入日期',
      control: select({ id, value: bounds ? 'custom' : filters.entryDateMode, options: ENTRY_DATE_OPTIONS }) })}</div>
    ${bounds ? html`<div class="entry-date-field__bounds">${dateField('from', '开始日期')}${dateField('to', '结束日期')}</div>
      ${error ? html`<p id="${errorId}" class="ui-field__error" role="alert">${error}</p>` : ''}
      ${button({ label: '应用日期', action, arg: 'apply', size: 'sm', disabled: !!error || (!bounds.from && !bounds.to) })}` : ''}
  </div>`;
}

export function entryDateMeta(item) {
  const day = entryDateOf(item);
  return html`录入日期 ${day ? html`<time datetime="${day}">${day}</time>` : '—'}`;
}
