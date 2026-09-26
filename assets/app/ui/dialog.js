/**
 * 对话框：dialog(spec) → Promise<{ok, values}>；confirm(title, o) → Promise<boolean>；prompt(title, value, o) → Promise<string|null>。
 * spec: {title, hint, body, content, okText, cancelText, danger, focus, size:'sm'|'md'|'lg'|'xl', dismissible, hideCancel,
 *        id, onOpen(el), onOk(values, el) → Promise<boolean>, returnFocus()}
 * body 可为 html`` 结果，或旧代码传入的、已由调用方转义的 HTML 字符串（过渡期兼容）；content 为 DOM 节点。
 * values 按 id 收集对话框内 input/select/textarea（复选、单选取 checked），与旧 uiDialog 相同。
 * onOk：点「确定」/ Enter / Ctrl+Enter 时先等它（按钮 aria-busy 并禁用）；返回 false 或抛错则留在对话框里（如保存失败），否则关闭。
 * dismissible 可为函数（见 ui/overlay.js）。
 */
import { html, raw, isHtml } from '../core/html.js';
import { toElement } from '../core/dom.js';
import { icon } from './icon.js';
import { openModal } from './overlay.js';

let seq = 0;

export function bodyMarkup(body) {
  if (body == null || body === '') return '';
  if (isHtml(body)) return body;
  return typeof body === 'string' ? raw(body) : '';
}

function collect(el) {
  const values = {};
  el.querySelectorAll('input, select, textarea').forEach(node => {
    if (node.id) values[node.id] = (node.type === 'checkbox' || node.type === 'radio') ? node.checked : node.value;
  });
  return values;
}

export function dialog(spec = {}) {
  return new Promise(resolve => {
    const id = `ui-dlg-${++seq}`;
    const size = ['sm', 'md', 'lg', 'xl'].includes(spec.size) ? spec.size : 'sm';
    const el = toElement(html`<dialog class="ui-dialog ui-dialog--${size}${spec.danger ? ' is-danger' : ''}"${spec.id ? html` id="${spec.id}"` : ''} aria-labelledby="${id}-t"${spec.hint ? html` aria-describedby="${id}-h"` : ''}>
<div class="ui-dialog__panel">
<header class="ui-dialog__head"><h2 class="ui-dialog__title" id="${id}-t">${spec.title || ''}</h2><button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm ui-dialog__close" data-dialog-cancel aria-label="关闭">${icon('x')}</button></header>
${spec.hint ? html`<p class="ui-dialog__hint" id="${id}-h">${spec.hint}</p>` : ''}
<div class="ui-dialog__body">${bodyMarkup(spec.body)}</div>
<footer class="ui-dialog__foot">${spec.hideCancel ? '' : html`<button type="button" class="ui-btn" data-dialog-cancel>${spec.cancelText || '取消'}</button>`}<button type="button" class="ui-btn ${spec.danger ? 'ui-btn--danger' : 'ui-btn--primary'}" data-dialog-ok>${spec.okText || '确定'}</button></footer>
</div></dialog>`);
    if (spec.content instanceof Node) el.querySelector('.ui-dialog__body').append(spec.content);
    const initialFocus = spec.focus || (spec.danger ? '.ui-dialog__foot [data-dialog-cancel]' : null);
    const okButton = el.querySelector('.ui-dialog__foot [data-dialog-ok]');
    let busy = false;
    async function accept() {
      if (busy) return;
      if (typeof spec.onOk !== 'function') { entry.close(true); return; }
      busy = true;
      okButton.disabled = true;
      okButton.setAttribute('aria-busy', 'true');
      let done = false;
      try { done = (await spec.onOk(collect(el), el)) !== false; } catch (error) { console.error('[ui/dialog] onOk 出错', error); }
      busy = false;
      okButton.disabled = false;
      okButton.removeAttribute('aria-busy');
      if (done) entry.close(true);
    }
    const entry = openModal(el, {
      dismissible: typeof spec.dismissible === 'function' ? spec.dismissible : spec.dismissible !== false,
      initialFocus,
      returnFocus: spec.returnFocus,
      onEnter: accept,
      onClose: ok => resolve({ ok: ok === true, values: collect(el) }),
    });
    el.addEventListener('click', event => {
      if (event.target.closest('[data-dialog-ok]')) accept();
      else if (event.target.closest('[data-dialog-cancel]')) entry.close(false);
    });
    spec.onOpen?.(el);
  });
}

/** 关掉某个 dialog() 打开的对话框（按元素）；供旧代码的 closeXxx() 过渡入口用。 */
export function closeDialog(el, ok = false) {
  if (el?.open) el.querySelector(ok ? '.ui-dialog__foot [data-dialog-ok]' : '[data-dialog-cancel]')?.click();
}

export async function confirm(title, options = {}) {
  const result = await dialog({
    title, hint: options.hint, body: options.body, danger: !!options.danger,
    okText: options.okText || '确定', cancelText: options.cancelText || '取消',
  });
  return result.ok;
}

export async function prompt(title, value = '', options = {}) {
  const id = `ui-prompt-${++seq}`;
  const result = await dialog({
    title, hint: options.hint, okText: options.okText, focus: `#${id}`,
    body: html`<input class="ui-input" id="${id}" value="${value ?? ''}" placeholder="${options.placeholder || ''}" maxlength="${options.maxLength || 120}" autocomplete="off">`,
  });
  return result.ok ? String(result.values[id] || '').trim() : null;
}
