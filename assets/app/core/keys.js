/**
 * 快捷键注册表：registerKeys(scope, { j: fn, 'shift+tab': fn, 'mod+k': fn })，返回注销函数。
 * setScope(pageId) 由外壳在切页时调用，只有当前页与 'global' 的快捷键生效；document 上只绑一个 keydown 监听。
 * 键名：字母小写、可打印字符原样（'?'、'/'）、其余用 event.key 的小写（'escape'、'arrowdown'、'enter'），空格写 'space'；
 * 修饰键前缀 mod+（Ctrl 或 ⌘）、alt+、shift+（只用于不可打印键）。
 * 默认在输入框里、或有对话框 / 旧弹层打开时不触发；登记为 { handler, inInput: true, inDialog: true } 可放开。
 * 处理函数返回 false 表示没处理，继续交给下一层（当前页 → global）。
 *
 * 浮层键盘层 pushKeyLayer(map)：浮层（选板浮层等）打开时压一层，返回弹出函数。只有最上面一层生效，并且先于当前页与 global；
 * 层内的键在输入框里、对话框里都生效（浮层自己就是最上面的东西）。键名同上，另可登记 'any'：表里没有的键都交给它。
 * 层默认独占（modal）：层没处理的键也不再往下传给页面与 global——浮层开着时，按 V / N 之类不会触发背后页面的快捷键；
 * 没处理的键不 preventDefault，照常输入文字、Tab 移焦点。{ modal: false } 时没处理的键照常往下传。
 * 叠在 ui/dialog 上的浮层，Esc 由 ui/overlay 在捕获阶段代关（hostGuest 的 escape:true），到不了这里。
 */
const scopes = new Map();
const layers = [];
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
  const layer = layers[layers.length - 1];
  if (layer) {
    const entry = layer.table.get(combo) || layer.any;
    if (entry && entry.handler(event) !== false) { event.preventDefault(); return; }
    if (layer.modal) return;
  }
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

/** 压一层浮层键盘表（见文件头），返回弹出函数；重复调用弹出函数无副作用。 */
export function pushKeyLayer(map, { modal = true } = {}) {
  const layer = { table: new Map(), any: null, modal };
  Object.entries(map).forEach(([combo, value]) => {
    const entry = typeof value === 'function' ? { handler: value } : value;
    if (combo === 'any') layer.any = entry;
    else layer.table.set(normalizeCombo(combo), entry);
  });
  layers.push(layer);
  return () => { const i = layers.indexOf(layer); if (i >= 0) layers.splice(i, 1); };
}

/** 当前压着的浮层键盘层数（测试与调试用）。 */
export const keyLayerCount = () => layers.length;

export function setScope(scope) { current = scope; }
export const currentScope = () => current;
