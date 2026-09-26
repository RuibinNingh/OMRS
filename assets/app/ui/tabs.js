/**
 * 标签页：tabs({label, items:[{id,label,badge,panel,disabled}], value, idPrefix}) 产出 role=tablist；
 * bindTabs(list) 处理点击与 ←/→/Home/End（自动激活），维护 aria-selected、tabindex，按 aria-controls 切换面板 hidden，
 * 并在 tablist 上派发 'ui-tabs:change'（detail.id）。
 */
import { html } from '../core/html.js';

export function tabs({ label = '', items = [], value, idPrefix = 'tab' } = {}) {
  return html`<div class="ui-tabs" role="tablist" aria-label="${label}">${items.map(it => {
    const on = it.id === value;
    return html`<button type="button" class="ui-tabs__tab${it.state ? ` is-${it.state}` : ''}" role="tab" id="${idPrefix}-${it.id}" data-tab="${it.id}" aria-selected="${on ? 'true' : 'false'}" tabindex="${on ? '0' : '-1'}"${it.panel ? html` aria-controls="${it.panel}"` : ''}${it.disabled ? html` disabled` : ''}>${it.label}${it.badge != null ? html`<span class="ui-badge">${it.badge}</span>` : ''}</button>`;
  })}</div>`;
}

export function selectTab(list, tab) {
  for (const t of list.querySelectorAll('[role="tab"]')) {
    const on = t === tab;
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
    const panelId = t.getAttribute('aria-controls');
    const panel = panelId && list.ownerDocument.getElementById(panelId);
    if (panel) panel.hidden = !on;
  }
  list.dispatchEvent(new CustomEvent('ui-tabs:change', { bubbles: true, detail: { id: tab.dataset.tab } }));
}

export function bindTabs(list) {
  list.addEventListener('click', event => {
    const tab = event.target.closest('[role="tab"]');
    if (tab && !tab.disabled && list.contains(tab)) selectTab(list, tab);
  });
  list.addEventListener('keydown', event => {
    const all = [...list.querySelectorAll('[role="tab"]:not([disabled])')];
    const i = all.indexOf(event.target);
    if (i < 0) return;
    const next = { ArrowRight: all[(i + 1) % all.length], ArrowLeft: all[(i - 1 + all.length) % all.length], Home: all[0], End: all[all.length - 1] }[event.key];
    if (!next) return;
    event.preventDefault();
    next.focus();
    selectTab(list, next);
  });
  return list;
}
