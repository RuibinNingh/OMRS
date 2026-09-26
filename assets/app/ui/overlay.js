/**
 * 模态层底座（dialog / drawer 共用）：<dialog>.showModal() 进浏览器顶层，天然盖过旧代码 z-index 999 的弹层，
 * 背景自动 inert（焦点陷阱）。本文件补上：Esc 与遮罩关闭、Enter 确认、关闭动画、焦点还给触发元素、背景滚动锁定。
 * Esc 在捕获阶段拦下并 stopPropagation，旧代码挂在 document 上的 Esc 监听不会顺带关掉下层弹层（与旧 uiDialog 一致）。
 *
 * - dismissible 可以是函数：每次 Esc / 点遮罩时再问（Markdown 编辑器有未保存修改时返回 false）。
 * - onEnter：Enter（不在多行文本、按钮、链接上）或 Ctrl / ⌘ + Enter（任何位置，含多行文本）时调用。
 * - returnFocus()：关闭后优先把焦点交给它返回的元素（题目弹窗翻页后交给最后看的那题的行），否则还给打开前的元素。
 * - 客人（hostGuest）：旧浮层（标记选择器、选板浮层、标记管理）叠在模态对话框上时必须放进对话框里，否则被 inert。
 *   登记后：Esc / Enter 先让给客人（escape:true 的由这里代为关闭），点遮罩只关客人不关对话框，对话框关闭时先关客人。
 */
const stack = [];

const liveGuests = entry => [...entry.guests].filter(guest => guest.node.isConnected);
const lastGuest = entry => liveGuests(entry).pop() || null;

function onKey(event) {
  const top = stack[stack.length - 1];
  if (!top) return;
  const guest = lastGuest(top);
  if (guest) {
    if (event.key === 'Escape' && guest.escape) {
      event.preventDefault();
      event.stopPropagation();
      guest.close?.();
    }
    return;   // 其余按键交给客人自己的监听（输入框、方向键、Enter 选中）
  }
  if (event.key === 'Escape') {
    event.preventDefault();
    event.stopPropagation();
    if (top.canDismiss()) top.close(false);
    return;
  }
  if (event.key !== 'Enter' || !top.onEnter || event.isComposing || !top.el.contains(event.target)) return;
  const mod = event.ctrlKey || event.metaKey;
  if (mod || !event.target.closest('textarea, button, a, [contenteditable="true"]')) {
    event.preventDefault();
    top.onEnter();
  }
}

export const openCount = () => stack.length;
/** 最上层模态对话框的元素（没有则 null）。 */
export const topModal = () => stack[stack.length - 1]?.el || null;
/** 最上层模态对话框里是否有叠着的客人浮层（题目弹窗的 ←/→ 翻页据此让位）。 */
export const guestOpen = () => { const top = stack[stack.length - 1]; return !!(top && lastGuest(top)); };

/**
 * 把旧浮层 node 放进最上层模态对话框（没有对话框时放进 body），返回宿主元素。
 * close：宿主关闭或（escape 为真时）按 Esc 时调用，负责移除 node 与解绑；releaseGuest(node) 在浮层自行关闭时注销。
 */
export function hostGuest(node, { close, escape = false } = {}) {
  const doc = node.ownerDocument;
  const top = stack[stack.length - 1];
  const host = top && top.el.isConnected && !top.closing ? top.el : doc.body;
  const opener = doc.activeElement;
  host.append(node);
  if (host !== doc.body) top.guests.add({ node, close, escape, opener });
  return host;
}

/** 客人自行关闭（已移除节点）时注销；焦点随节点丢失时还给打开它的元素（对话框里的「标记」「加入展示板」按钮）。 */
export function releaseGuest(node) {
  stack.forEach(entry => entry.guests.forEach(guest => {
    if (guest.node !== node) return;
    entry.guests.delete(guest);
    const doc = node.ownerDocument;
    const active = doc.activeElement;
    const lost = !active || active === doc.body || node.contains(active);
    if (!entry.closing && lost && guest.opener?.isConnected && entry.el.contains(guest.opener)) guest.opener.focus({ preventScroll: true });
  }));
}

export function openModal(el, { dismissible = true, onEnter, onClose, initialFocus, returnFocus } = {}) {
  const doc = el.ownerDocument;
  const opener = doc.activeElement;
  let settled = false;
  const entry = {
    el, onEnter, close, guests: new Set(),
    canDismiss: () => (typeof dismissible === 'function' ? !!dismissible() : !!dismissible),
  };

  function close(result) {
    if (settled) return;
    settled = true;
    entry.closing = true;
    liveGuests(entry).forEach(guest => { try { guest.close?.(); } catch (error) { console.error('[ui/overlay] 关闭客人浮层出错', error); } });
    entry.guests.clear();
    const i = stack.indexOf(entry);
    if (i >= 0) stack.splice(i, 1);
    if (!stack.length) {
      doc.removeEventListener('keydown', onKey, true);
      doc.documentElement.classList.remove('ui-scroll-lock');
    }
    onClose?.(result);
    el.classList.add('is-closing');
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      if (el.open && typeof el.close === 'function') el.close();
      el.remove();
      let target = null;
      try { target = typeof returnFocus === 'function' ? returnFocus() : null; } catch (error) { target = null; }
      if (!(target && target.isConnected)) target = opener;
      if (target && target.isConnected && typeof target.focus === 'function') target.focus({ preventScroll: true });
    };
    el.addEventListener('animationend', event => { if (event.target === el) finish(); });
    setTimeout(finish, 320);
  }

  // 按下时就判定：选板浮层在捕获阶段关自己，等到 click 时客人已经不在了
  let downOnScrim = false;
  el.addEventListener('mousedown', event => { downOnScrim = event.target === el && !lastGuest(entry); });
  el.addEventListener('click', event => {
    if (event.target === el && downOnScrim && entry.canDismiss()) close(false);
    downOnScrim = false;
  });
  el.addEventListener('cancel', event => { event.preventDefault(); if (!lastGuest(entry) && entry.canDismiss()) close(false); });

  if (!el.isConnected) doc.body.append(el);
  if (!stack.length) {
    doc.addEventListener('keydown', onKey, true);
    doc.documentElement.classList.add('ui-scroll-lock');
  }
  stack.push(entry);
  if (typeof el.showModal === 'function') el.showModal();
  else { el.setAttribute('open', ''); el.classList.add('is-fallback'); }

  const target = (initialFocus && el.querySelector(initialFocus))
    || el.querySelector('[autofocus], input:not([type=hidden]):not(:disabled), select, textarea')
    || el.querySelector('[data-dialog-ok], button:not(:disabled)');
  if (target) {
    target.focus({ preventScroll: true });
    if (target.tagName === 'INPUT' && typeof target.select === 'function') target.select();
  }
  return entry;
}
