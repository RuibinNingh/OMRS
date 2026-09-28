/** 框选标注页的纯函数：坐标（统一 0–1）、拖动手势、沿用上一张、撤销栈、导航与筛选。不碰 DOM，node 直接测。 */
export const ROLES = Object.freeze({ question: '题目', answer: '答案' });
export const OTHER_ROLE = Object.freeze({ question: 'answer', answer: 'question' });
export const FILTERS = Object.freeze([
  { value: 'all', label: '全部' },
  { value: 'todo', label: '未完成' },
  { value: 'done', label: '已完成' },
]);
export const MIN_SIDE_PX = 6;
export const ZOOM_STEPS = Object.freeze([0.25, 0.33, 0.5, 0.67, 0.8, 1, 1.25, 1.5, 2, 3]);

const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
const round = value => Math.round(value * 1e6) / 1e6;

export function pointIn(clientX, clientY, bounds) {
  return { x: clamp((clientX - bounds.left) / bounds.width, 0, 1), y: clamp((clientY - bounds.top) / bounds.height, 0, 1) };
}

/** 画框 / 移动 / 八向缩放：start、point 为 0–1 坐标，original 为按下时的框。 */
export function dragBox(mode, start, point, original, handle = '') {
  const dx = point.x - start.x, dy = point.y - start.y;
  if (mode === 'draw') return { x: Math.min(start.x, point.x), y: Math.min(start.y, point.y), w: Math.abs(dx), h: Math.abs(dy) };
  if (mode === 'move') return { x: clamp(original.x + dx, 0, 1 - original.w), y: clamp(original.y + dy, 0, 1 - original.h), w: original.w, h: original.h };
  let { x, y, w, h } = original;
  const right = original.x + original.w, bottom = original.y + original.h;
  if (handle.includes('w')) { x = clamp(original.x + dx, 0, right - 0.002); w = right - x; }
  if (handle.includes('e')) w = clamp(original.w + dx, 0.002, 1 - original.x);
  if (handle.includes('n')) { y = clamp(original.y + dy, 0, bottom - 0.002); h = bottom - y; }
  if (handle.includes('s')) h = clamp(original.h + dy, 0.002, 1 - original.y);
  return { x, y, w, h };
}

/** 屏幕上小于 MIN_SIDE_PX 的新框视为误点。 */
export function tooSmall(box, displayWidth, displayHeight) {
  return box.w * displayWidth < MIN_SIDE_PX || box.h * displayHeight < MIN_SIDE_PX;
}

export const cleanBox = box => ({ role: ROLES[box.role] ? box.role : 'question', x: round(box.x), y: round(box.y), w: round(box.w), h: round(box.h) });

/** 沿用上一张：横向照搬；上部（y<0.35）的框按像素锚定顶部，其余按比例——长截图高度差异大，归一化 y 不能直接搬。 */
export function transferBoxes(from, to) {
  if (!from || !to) return [];
  const ratio = (Number(from.height) || 1) / (Number(to.height) || 1);
  return (from.boxes || []).map(box => {
    const top = box.y < 0.35;
    const y = top ? Math.min(0.95, box.y * ratio) : box.y;
    const h = top ? Math.min(1 - y, box.h * ratio) : Math.min(1 - y, box.h);
    return cleanBox({ ...box, y, h });
  }).filter(box => box.w > 0 && box.h > 0);
}

export function countRoles(boxes = []) {
  const counts = { question: 0, answer: 0 };
  for (const box of boxes) if (box.role in counts) counts[box.role] += 1;
  return counts;
}

/** 框的显示名：同角色按出现顺序编号，「题目 1」「答案 1」。 */
export function boxLabels(boxes = []) {
  const seen = { question: 0, answer: 0 };
  return boxes.map(box => { seen[box.role] = (seen[box.role] || 0) + 1; return `${ROLES[box.role] || box.role} ${seen[box.role]}`; });
}

export function filterImages(images = [], filter = 'all') {
  if (filter === 'todo' || filter === 'done') return images.filter(image => image.status === filter);
  return images;
}

export function summary(images = []) {
  const done = images.filter(image => image.status === 'done').length;
  return { total: images.length, done, todo: images.length - done };
}

/** 在 list 里从 current 走 step 步；到头停住。 */
export function stepId(list, current, step) {
  if (!list.length) return null;
  const index = list.findIndex(image => image.id === current);
  if (index < 0) return list[0].id;
  return list[clamp(index + step, 0, list.length - 1)].id;
}

/** current 之后的第一张未完成（绕回开头）；没有就返回 null。 */
export function nextTodo(images, current) {
  const index = images.findIndex(image => image.id === current);
  for (let i = 1; i <= images.length; i += 1) {
    const image = images[(index + i + images.length) % images.length];
    if (image && image.status !== 'done' && image.id !== current) return image.id;
  }
  return null;
}

export function zoomStep(zoom, direction) {
  if (direction === 0) return 1;
  if (direction > 0) return ZOOM_STEPS.find(step => step > zoom + 1e-6) ?? ZOOM_STEPS[ZOOM_STEPS.length - 1];
  return [...ZOOM_STEPS].reverse().find(step => step < zoom - 1e-6) ?? ZOOM_STEPS[0];
}

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

/** 每张图一条撤销栈：record(id, before) 在改动前存快照；undo / redo 传入当前框，返回要换上的框或 null。 */
export function createHistory(limit = 100) {
  const stacks = new Map();
  const stack = id => { if (!stacks.has(id)) stacks.set(id, { past: [], future: [] }); return stacks.get(id); };
  const copy = boxes => (boxes || []).map(box => ({ ...box }));
  return {
    record(id, before) {
      const s = stack(id);
      if (s.past.length && same(s.past[s.past.length - 1], before)) return;
      s.past.push(copy(before));
      if (s.past.length > limit) s.past.shift();
      s.future = [];
    },
    undo(id, current) {
      const s = stack(id);
      if (!s.past.length) return null;
      s.future.push(copy(current));
      return s.past.pop();
    },
    redo(id, current) {
      const s = stack(id);
      if (!s.future.length) return null;
      s.past.push(copy(current));
      return s.future.pop();
    },
    size: id => ({ past: stack(id).past.length, future: stack(id).future.length }),
  };
}
