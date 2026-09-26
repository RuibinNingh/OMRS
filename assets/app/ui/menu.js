/**
 * 菜单：openMenu(anchor, items, {label}) → Promise<选中项的 value（缺省为下标）| null>。
 * items: [{value, label, icon, hint, danger, disabled} | {divider:true}]
 * 键盘：↑↓ 移动（跳过禁用项）、Home/End、Enter/空格选择、Esc 关闭并把焦点还给触发元素、Tab 关闭。
 * 触发元素在对话框里时菜单挂进该对话框（否则会被 inert）；支持 popover 时进顶层，否则 fixed + --z-dropdown。
 */
import { html } from '../core/html.js';
import { toElement } from '../core/dom.js';
import { icon } from './icon.js';

let current = null;

export function menuMarkup(items, { label = '菜单', staticPreview = false } = {}) {
  return html`<div class="ui-menu${staticPreview ? ' is-static' : ''}" role="menu" aria-label="${label}">${items.map((it, i) => (it.divider
    ? html`<div class="ui-menu__divider" role="separator"></div>`
    : html`<button type="button" class="ui-menu__item${it.danger ? ' is-danger' : ''}${it.hover ? ' is-hover' : ''}" role="menuitem" data-menu-index="${i}" tabindex="-1"${it.disabled ? html` aria-disabled="true"` : ''}>${it.icon ? icon(it.icon) : ''}<span class="ui-menu__label">${it.label}</span>${it.hint ? html`<span class="ui-menu__hint">${it.hint}</span>` : ''}</button>`))}</div>`;
}

function place(el, anchor) {
  const win = anchor.ownerDocument.defaultView;
  const a = anchor.getBoundingClientRect();
  const m = el.getBoundingClientRect();
  let top = a.bottom + 4;
  if (top + m.height > win.innerHeight - 8 && a.top - 4 - m.height > 8) top = a.top - 4 - m.height;
  let left = a.left;
  if (left + m.width > win.innerWidth - 8) left = Math.max(8, a.right - m.width);
  el.style.setProperty('--menu-x', `${Math.round(left)}px`);
  el.style.setProperty('--menu-y', `${Math.round(top)}px`);
}

export function closeMenu() { current?.finish(null); }

export function openMenu(anchor, items, options = {}) {
  if (current && current.anchor === anchor) { closeMenu(); return Promise.resolve(null); }
  closeMenu();
  const doc = anchor.ownerDocument;
  const win = doc.defaultView;
  const el = toElement(menuMarkup(items, options), doc);
  el.classList.add('is-floating');
  if ('popover' in el) el.setAttribute('popover', 'manual');
  (anchor.closest('dialog[open]') || doc.body).append(el);
  if (el.hasAttribute('popover')) { try { el.showPopover(); } catch (_) { /* 退回 z-index */ } }
  place(el, anchor);
  anchor.setAttribute('aria-expanded', 'true');
  const enabled = () => [...el.querySelectorAll('.ui-menu__item:not([aria-disabled="true"])')];
  return new Promise(resolve => {
    const state = { anchor, finish: null };
    const onKey = event => {
      const list = enabled();
      const i = list.indexOf(doc.activeElement);
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); state.finish(null); }
      else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        if (list.length) list[(i + (event.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length].focus();
      } else if (event.key === 'Home' || event.key === 'End') { event.preventDefault(); list[event.key === 'Home' ? 0 : list.length - 1]?.focus(); }
      else if (event.key === 'Tab') state.finish(null, false);
    };
    const onDown = event => { if (!el.contains(event.target) && !anchor.contains(event.target)) state.finish(null, false); };
    const onResize = () => state.finish(null, false);
    state.finish = (value, restoreFocus = true) => {
      if (current !== state) return;
      current = null;
      doc.removeEventListener('pointerdown', onDown, true);
      doc.removeEventListener('keydown', onKey, true);
      win.removeEventListener('resize', onResize);
      anchor.setAttribute('aria-expanded', 'false');
      el.remove();
      if (restoreFocus && options.restoreFocus !== false) anchor.focus({ preventScroll: true });
      resolve(value);
    };
    el.addEventListener('click', event => {
      const item = event.target.closest('[data-menu-index]');
      if (!item || item.getAttribute('aria-disabled') === 'true') return;
      const index = Number(item.dataset.menuIndex);
      state.finish(items[index].value ?? index);
    });
    current = state;
    doc.addEventListener('pointerdown', onDown, true);
    doc.addEventListener('keydown', onKey, true);
    win.addEventListener('resize', onResize);
    enabled()[0]?.focus({ preventScroll: true });
  });
}
