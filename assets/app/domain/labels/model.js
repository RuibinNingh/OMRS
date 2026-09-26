/**
 * 标记定义与选择器 / 管理的数据部分（纯函数，node 可测）：排序、增改、选择器候选、最近使用、快速区、下一个颜色、
 * 批量增删、管理表单规范化。选择器浮层、管理弹层的 DOM 与写接口仍在旧 labels.js，经过渡桥 installLabelsBridge 调这里。
 */
import { hexKey, hexOf } from './color.js';

export const RECENT_KEY = 'omrs-label-recent';
const zh = (a, b) => String(a).localeCompare(String(b), 'zh-CN');
const arr = list => (Array.isArray(list) ? list : []);

export const sortLabels = list => [...arr(list)].sort((a, b) => (a.order || 0) - (b.order || 0) || zh(a.name, b.name));

/** 按 id 或名称替换（没有就加），再排序。 */
export function upsertLabel(list, label) {
  if (!label || !label.name) return sortLabels(list);
  return sortLabels([...arr(list).filter(item => item.id !== label.id && item.name !== label.name), label]);
}

/** 选择器候选：按输入过滤未归档定义（不分大小写）；输入非空且没有同名定义时给出「新建」。 */
export function pickerOptions(list, query) {
  const raw = String(query || '').trim();
  const needle = raw.toLowerCase();
  const all = arr(list);
  const matches = all.filter(label => !label.archived && (!needle || String(label.name).toLowerCase().includes(needle)));
  return { raw, create: raw && !all.some(label => label.name === raw) ? raw : '', matches };
}

/** 最近使用（localStorage，键名沿用旧版）：只留仍存在的标记。 */
export function readRecent(storage, list) {
  try {
    const names = JSON.parse(storage?.getItem(RECENT_KEY) || '[]');
    return Array.isArray(names) ? names.filter(name => arr(list).some(item => item.name === name)) : [];
  } catch (error) { return []; }
}

export function touchRecent(storage, names, list) {
  const next = [...new Set([...arr(names), ...readRecent(storage, list)])].slice(0, 6);
  try { storage?.setItem(RECENT_KEY, JSON.stringify(next)); } catch (error) { /* 隐私模式或存储已满 */ }
  return next;
}

/** 快速区：最近使用在前，其余定义补齐到 limit 个（调用方再去掉已选的）。 */
export function quickList(list, recent, limit = 4) {
  const defs = arr(list);
  const rest = defs.filter(item => !arr(recent).includes(item.name)).map(item => item.name);
  return [...arr(recent), ...rest].slice(0, limit).map(name => defs.find(item => item.name === name) || { name, color: '' });
}

/** 新标记的颜色：第一个没人用的预设色；全用过则按数量轮换。presets 为 '#rrggbb' 列表（color.js 的 presetColors()）。 */
export function nextColor(list, presets) {
  const keys = arr(presets).map(hexKey).filter(Boolean);
  if (!keys.length) return '';
  const used = new Set(arr(list).map(item => hexKey(item.color)));
  return hexOf(keys.find(key => !used.has(key)) || keys[arr(list).length % keys.length]);
}

/** 批量增删后各题的标记：{ uid: labels }（只含 uids 里的题；先加后删，去重，保持原顺序）。 */
export function applyBatch(items, uids, add = [], remove = []) {
  const wanted = new Set(arr(uids));
  const drop = new Set(arr(remove));
  const out = {};
  arr(items).forEach(item => {
    if (wanted.has(item.uid)) out[item.uid] = [...new Set([...arr(item.labels), ...arr(add)])].filter(label => !drop.has(label));
  });
  return out;
}

/** 管理表单：名称去空白；颜色规范成 '#rrggbb'（不合法用 fallback）；调度加成钳到 0–1。 */
export function formValues({ name, color, bonus } = {}, fallback = '') {
  const value = Number(bonus);
  return {
    name: String(name || '').trim(),
    color: hexOf(hexKey(color)) || fallback,
    priority_bonus: Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0)),
  };
}
