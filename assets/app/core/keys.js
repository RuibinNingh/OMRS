/**
 * 快捷键注册表：registerKeys(scope, { j: fn, 'shift+tab': fn, 'mod+k': fn })，返回注销函数。
 * setScope(pageId) 由外壳在切页时调用，只有当前页与 'global' 的快捷键生效；document 上只绑一个 keydown 监听。
 * 键名：字母小写、可打印字符原样（'?'、'/'）、其余用 event.key 的小写（'escape'、'arrowdown'、'enter'），空格写 'space'；
 * 修饰键前缀 mod+（Ctrl 或 ⌘）、alt+、shift+（只用于不可打印键）。
 * 默认在输入框里、或有对话框 / 旧弹层打开时不触发；登记为 { handler, inInput: true, inDialog: true } 可放开。
 * 处理函数返回 false 表示没处理，继续交给下一层（当前页 → global）。
 */
const scopes = new Map();
let current = null;
let bound = false;

export function normalizeCombo(combo) {
  const parts = String(combo).toLowerCase().split('+').map(p => p.trim()).filter(Boolean);
  const key = parts.pop() || '';
  const mods = ['mod', 'alt', 'shift'].filter(m => parts.includes(m) || (m === 'mod' && (parts.includes('ctrl') || parts.includes('meta'))));
  return [...mods, key === ' ' ? 'space' : key].join('+');
}

export function comboOf(event) {
  const printable = event.key.length === 1;
  const key = event.key === ' ' ? 'space' : (printable ? event.key.toLowerCase() : event.key.toLowerCase());
  const mods = [];
  if (event.ctrlKey || event.metaKey) mods.push('mod');
  if (event.altKey) mods.push('alt');
  if (event.shiftKey && !printable) mods.push('shift');
  return [...mods, key].join('+');
}

const typing = target => !!target?.closest?.('input, textarea, select, [contenteditable=""], [contenteditable="true"]');
const dialogOpen = doc => !!doc.querySelector('dialog[open]:not(.is-closing), .modal-overlay.open');   // 退场动画中的对话框不挡快捷键

function onKey(event) {
  if (event.defaultPrevented || event.isComposing) return;
  const combo = comboOf(event);
  const doc = event.target?.ownerDocument || document;
  for (const scope of [current, 'global']) {
    const entry = scope && scopes.get(scope)?.get(combo);
    if (!entry) continue;
    if (typing(event.target) && !entry.inInput) continue;
    if (dialogOpen(doc) && !entry.inDialog) continue;
    if (entry.handler(event) === false) continue;
    event.preventDefault();
    return;
  }
}

export function bindKeys(doc = document) {
  if (bound) return;
  bound = true;
  doc.addEventListener('keydown', onKey);
}

export function registerKeys(scope, map) {
  if (!scopes.has(scope)) scopes.set(scope, new Map());
  const table = scopes.get(scope);
  const combos = Object.entries(map).map(([combo, value]) => {
    const entry = typeof value === 'function' ? { handler: value } : value;
    const name = normalizeCombo(combo);
    table.set(name, entry);
    return name;
  });
  return () => combos.forEach(name => table.delete(name));
}

export function setScope(scope) { current = scope; }
export const currentScope = () => current;
