/**
 * 通知：toast(text, {kind:'info'|'ok'|'warn'|'error', actions:[{label,onClick}], duration}) → {el, close}。
 * 全站唯一一套：右下角堆叠（窄屏底部通栏），最多同时 3 条，同文同类合并；悬停或聚焦时暂停计时。
 * 容器是 aria-live 区域；error 用 role=alert。支持 popover 的浏览器把容器放进顶层，盖过对话框与旧弹层。
 */
import { html } from '../core/html.js';
import { toElement } from '../core/dom.js';
import { icon } from './icon.js';

const KIND_ICON = { info: 'info', ok: 'check-circle', warn: 'alert-triangle', error: 'alert-circle' };
export const TOAST_KINDS = Object.freeze(Object.keys(KIND_ICON));
const MAX_VISIBLE = 3;
let host = null;

export function toastMarkup(text, { kind = 'info', actions = [] } = {}) {
  const k = KIND_ICON[kind] ? kind : 'info';
  return html`<div class="ui-toast ui-toast--${k}" role="${k === 'error' ? 'alert' : 'status'}">
<span class="ui-toast__icon">${icon(KIND_ICON[k])}</span><div class="ui-toast__text">${text}</div>
${actions.length ? html`<div class="ui-toast__actions">${actions.map((a, i) => html`<button type="button" class="ui-btn ui-btn--sm ui-btn--ghost ui-toast__action" data-toast-act="${i}">${a.label}</button>`)}</div>` : ''}
<button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm ui-toast__close" data-toast-close aria-label="关闭通知">${icon('x')}</button>
</div>`;
}

function ensureHost(doc) {
  if (host && host.isConnected && host.ownerDocument === doc) return host;
  host = doc.createElement('section');
  host.className = 'ui-toaster';
  host.setAttribute('aria-live', 'polite');
  host.setAttribute('aria-label', '通知');
  if ('popover' in host) host.setAttribute('popover', 'manual');
  doc.body.append(host);
  return host;
}

function raise(h) {
  if (!h.hasAttribute('popover')) return;
  try { if (h.matches(':popover-open')) h.hidePopover(); h.showPopover(); } catch (_) { /* 顶层不可用时退回 z-index */ }
}

const alive = h => [...h.children].filter(n => !n.classList.contains('is-leaving'));

export function toast(text, options = {}) {
  const doc = options.document || document;
  const h = ensureHost(doc);
  const kind = KIND_ICON[options.kind] ? options.kind : 'info';
  const actions = Array.isArray(options.actions) ? options.actions.filter(a => a && a.label) : [];
  const message = String(text ?? '');
  const dup = alive(h).find(n => n.dataset.kind === kind && n.dataset.text === message && !n.querySelector('[data-toast-act]'));
  if (dup && !actions.length) {
    dup.__restart();
    dup.classList.remove('is-bump');
    void dup.offsetWidth;
    dup.classList.add('is-bump');
    return { el: dup, close: dup.__close };
  }
  const el = toElement(toastMarkup(message, { kind, actions }), doc);
  el.dataset.kind = kind;
  el.dataset.text = message;
  const duration = Number(options.duration) || (actions.length ? 6000 : kind === 'error' ? 5000 : 2600);
  let timer = null;
  let remaining = duration;
  let startedAt = 0;
  const close = () => {
    if (el.classList.contains('is-leaving')) return;
    clearTimeout(timer);
    el.classList.add('is-leaving');
    let gone = false;
    const remove = () => {
      if (gone) return;
      gone = true;
      el.remove();
      if (!h.children.length && h.hasAttribute('popover')) { try { h.hidePopover(); } catch (_) { /* 已关闭 */ } }
    };
    el.addEventListener('animationend', remove);
    setTimeout(remove, 400);
  };
  const start = () => { clearTimeout(timer); startedAt = Date.now(); timer = setTimeout(close, remaining); };
  const pause = () => { clearTimeout(timer); remaining = Math.max(800, remaining - (Date.now() - startedAt)); };
  el.__close = close;
  el.__restart = () => { remaining = duration; start(); };
  el.addEventListener('mouseenter', pause);
  el.addEventListener('mouseleave', start);
  el.addEventListener('focusin', pause);
  el.addEventListener('focusout', start);
  el.addEventListener('click', event => {
    const act = event.target.closest('[data-toast-act]');
    if (act) {
      close();
      const action = actions[Number(act.dataset.toastAct)];
      if (action && typeof action.onClick === 'function') action.onClick();
    } else if (event.target.closest('[data-toast-close]')) close();
  });
  h.append(el);
  raise(h);
  const live = alive(h);
  if (live.length > MAX_VISIBLE) live.slice(0, live.length - MAX_VISIBLE).forEach(n => n.__close());
  start();
  return { el, close };
}
