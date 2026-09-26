/**
 * 抽屉：openDrawer({title, body, content, footer, side:'right'|'left', onClose}) → {el, body, close}。
 * 与 dialog 共用 overlay.js（焦点陷阱、Esc、遮罩关闭、滚动锁定）；窄屏（≤760px）自动变成底部面板。
 */
import { html } from '../core/html.js';
import { toElement } from '../core/dom.js';
import { icon } from './icon.js';
import { openModal } from './overlay.js';
import { bodyMarkup } from './dialog.js';

let seq = 0;

export function openDrawer(spec = {}) {
  const id = `ui-drw-${++seq}`;
  const side = spec.side === 'left' ? 'left' : 'right';
  const el = toElement(html`<dialog class="ui-drawer ui-drawer--${side}" aria-labelledby="${id}-t">
<div class="ui-drawer__panel">
<header class="ui-drawer__head"><h2 class="ui-drawer__title" id="${id}-t">${spec.title || ''}</h2><button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm" data-drawer-close aria-label="关闭">${icon('x')}</button></header>
<div class="ui-drawer__body">${bodyMarkup(spec.body)}</div>
${spec.footer ? html`<footer class="ui-drawer__foot">${spec.footer}</footer>` : ''}
</div></dialog>`);
  const body = el.querySelector('.ui-drawer__body');
  if (spec.content instanceof Node) body.append(spec.content);
  const entry = openModal(el, { initialFocus: spec.focus || '[data-drawer-close]', onClose: result => spec.onClose?.(result) });
  el.addEventListener('click', event => { if (event.target.closest('[data-drawer-close]')) entry.close(false); });
  return { el, body, close: result => entry.close(result) };
}
