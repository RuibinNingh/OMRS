/** 框选坐标和区域派生状态；坐标统一为 0–1，页面尺寸只用于手势判定。 */
export const ROLES = Object.freeze({ question: '题目', answer: '答案', ignore: '忽略' });

export function newRegion(card, role, x, y, w, h, extra = {}, makeId = () => `r_${Math.random().toString(36).slice(2, 10)}`) {
  return {
    id: makeId(), card, role, x, y, w, h, origin: 'manual', conf: null, ai_box: null,
    convert: 'auto', text: null, text_status: 'none', judge: null, judge_overridden: false, ...extra,
  };
}

export function hasExtraction(region) {
  return !!region.judge && !['running', 'stale', 'error'].includes(region.text_status);
}

export function groupCards(item) {
  const groups = new Map();
  for (const region of item?.regions || []) {
    const card = Number(region.card) || 1;
    if (!groups.has(card)) groups.set(card, []);
    groups.get(card).push(region);
  }
  return [...groups].sort(([a], [b]) => a - b);
}

export function statusAfterEdit(item) {
  if (item.status === 'ready') return item.regions?.length ? 'boxed' : 'pending';
  if (item.regions?.length && item.status === 'pending') return 'boxed';
  if (!item.regions?.length && item.status === 'boxed') return 'pending';
  return item.status;
}

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));

export function pointInImage(clientX, clientY, bounds) {
  return { x: clamp((clientX - bounds.left) / bounds.width, 0, 1),
    y: clamp((clientY - bounds.top) / bounds.height, 0, 1) };
}

export function draggedBox(mode, start, point, original, handle = '') {
  const dx = point.x - start.x, dy = point.y - start.y;
  if (mode === 'draw') return { x: Math.min(start.x, point.x), y: Math.min(start.y, point.y),
    w: Math.abs(dx), h: Math.abs(dy) };
  if (mode === 'move') return { x: clamp(original.x + dx, 0, 1 - original.w),
    y: clamp(original.y + dy, 0, 1 - original.h), w: original.w, h: original.h };
  let { x, y, w, h } = original;
  if (handle.includes('w')) { x = Math.min(original.x + original.w - .01, original.x + dx); w = original.x + original.w - x; }
  if (handle.includes('e')) w = Math.max(.01, original.w + dx);
  if (handle.includes('n')) { y = Math.min(original.y + original.h - .01, original.y + dy); h = original.y + original.h - y; }
  if (handle.includes('s')) h = Math.max(.01, original.h + dy);
  x = Math.max(0, x); y = Math.max(0, y);
  return { x, y, w: Math.min(1 - x, w), h: Math.min(1 - y, h) };
}
