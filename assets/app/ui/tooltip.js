/**
 * 提示：元素写 data-tooltip="文字"，页面调用一次 bindTooltips(document)。悬停 500ms 或键盘聚焦时显示，
 * 移出、失焦、滚动或 Esc 隐藏；显示期间给目标挂 aria-describedby。全站只有一个 .ui-tooltip 元素。
 */
let tip = null;
let owner = null;
let timer = null;

function ensure(doc) {
  if (tip && tip.isConnected && tip.ownerDocument === doc) return tip;
  tip = doc.createElement('div');
  tip.className = 'ui-tooltip';
  tip.id = 'ui-tooltip';
  tip.setAttribute('role', 'tooltip');
  if ('popover' in tip) tip.setAttribute('popover', 'manual');
  doc.body.append(tip);
  return tip;
}

export function showTooltip(target) {
  const text = target.getAttribute('data-tooltip');
  if (!text) return null;
  const doc = target.ownerDocument;
  const el = ensure(doc);
  const container = target.closest('dialog[open]') || doc.body;
  if (el.parentNode !== container) container.append(el);
  el.textContent = text;
  if (owner && owner !== target) owner.removeAttribute('aria-describedby');
  owner = target;
  target.setAttribute('aria-describedby', el.id);
  if (el.hasAttribute('popover')) { try { if (el.matches(':popover-open')) el.hidePopover(); el.showPopover(); } catch (_) { /* 退回 z-index */ } }
  el.classList.add('is-visible');
  const a = target.getBoundingClientRect();
  const m = el.getBoundingClientRect();
  const vw = doc.defaultView.innerWidth;
  let top = a.top - m.height - 6;
  const below = top < 4;
  if (below) top = a.bottom + 6;
  const left = Math.min(Math.max(4, a.left + a.width / 2 - m.width / 2), vw - m.width - 4);
  el.style.setProperty('--tip-x', `${Math.round(left)}px`);
  el.style.setProperty('--tip-y', `${Math.round(top)}px`);
  el.classList.toggle('is-below', below);
  return el;
}

export function hideTooltip() {
  clearTimeout(timer);
  if (!tip) return;
  tip.classList.remove('is-visible');
  if (tip.hasAttribute('popover')) { try { tip.hidePopover(); } catch (_) { /* 已隐藏 */ } }
  if (owner) { owner.removeAttribute('aria-describedby'); owner = null; }
}

export function bindTooltips(root = document, { delay = 500 } = {}) {
  if (root.__uiTooltips) return;
  root.__uiTooltips = true;
  const schedule = (target, wait) => { clearTimeout(timer); timer = setTimeout(() => showTooltip(target), wait); };
  root.addEventListener('pointerover', event => {
    const target = event.target.closest?.('[data-tooltip]');
    if (target && target !== owner) schedule(target, delay);
  });
  root.addEventListener('pointerout', event => {
    const target = event.target.closest?.('[data-tooltip]');
    if (target && !(event.relatedTarget && target.contains(event.relatedTarget))) hideTooltip();
  });
  root.addEventListener('focusin', event => {
    const target = event.target.closest?.('[data-tooltip]');
    if (target && target.matches(':focus-visible')) schedule(target, 0);
  });
  root.addEventListener('focusout', hideTooltip);
  root.addEventListener('keydown', event => { if (event.key === 'Escape' && owner) hideTooltip(); }, true);
  root.addEventListener('scroll', hideTooltip, true);
}
