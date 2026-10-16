/** 紧凑账号浮层：外部点击、Escape、键盘移动和记录子页焦点。 */
export function createAccountMenu(host, state, paint) {
  const doc = host.ownerDocument;
  const account = () => host.querySelector('#zyb-account');
  const trigger = () => account()?.querySelector('[data-arg="toggle"]');
  function close(restore = false) {
    if (!state.accountPanel) return;
    state.accountPanel = ''; paint();
    if (restore) trigger()?.focus({ preventScroll: true });
  }
  function show(page) {
    state.accountPanel = page === 'toggle' ? (state.accountPanel ? '' : 'main') : page;
    paint();
    const selector = state.accountPanel === 'records' ? '[data-arg="main"]' : '[data-arg="records"]';
    if (page === 'main' || page === 'records') account()?.querySelector(selector)?.focus({ preventScroll: true });
    else if (state.accountPanel) account()?.querySelector('.zyb-account-panel button:not(:disabled)')?.focus({ preventScroll: true });
    else trigger()?.focus({ preventScroll: true });
  }
  function onPointer(event) { if (state.accountPanel && !account()?.contains(event.target)) close(); }
  function onKey(event) {
    if (!state.accountPanel) return;
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); return; }
    if (!account()?.contains(event.target)) return;
    const items = [...account().querySelectorAll('.zyb-account-panel button:not(:disabled), .zyb-account-panel input:not(:disabled)')];
    if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const current = items.indexOf(doc.activeElement);
      const index = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
      items[index]?.focus({ preventScroll: true });
    }
  }
  function onFocus(event) { if (state.accountPanel && !account()?.contains(event.target)) close(); }
  doc.addEventListener('pointerdown', onPointer, true);
  doc.addEventListener('keydown', onKey, true);
  doc.addEventListener('focusin', onFocus);
  return { show, close, dispose() { close(); doc.removeEventListener('pointerdown', onPointer, true); doc.removeEventListener('keydown', onKey, true); doc.removeEventListener('focusin', onFocus); } };
}
