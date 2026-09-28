/**
 * 标注画布：原图 + SVG 框层 + 十字准线。坐标 0–1，SVG viewBox 用原图像素，线宽不随缩放变。
 * 手势：空白处拖动画框（Shift 画另一种角色），拖框移动，拖选中框的八个把手缩放；拖到滚动区边缘时自动滚动（长截图）。
 * Ctrl / ⌘ + 滚轮缩放。框在拖动中原地改，松手后交给 store.commitGesture 记撤销并保存。
 */
import { html } from '../../core/html.js';
import { render } from '../../core/dom.js';
import { OTHER_ROLE, boxLabels, dragBox, pointIn, tooSmall } from './state.js';

const rawUrl = id => `/api/annotate/raw?id=${encodeURIComponent(id)}`;
const EDGE = 40;
const HANDLES = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

/** 自动滚动速度（像素 / 帧）：进入边缘 EDGE 像素开始滚，越往外越快，拖出窗口最快约 90。 */
export function edgeSpeed(pos, low, high) {
  const depth = pos < low + EDGE ? low + EDGE - pos : pos > high - EDGE ? pos - (high - EDGE) : 0;
  return depth ? Math.sign(pos - (low + high) / 2) * Math.round(Math.min(90, 6 + depth * 0.7)) : 0;
}

function handlePoints(box, width, height) {
  const x0 = box.x * width, x1 = (box.x + box.w) * width, y0 = box.y * height, y1 = (box.y + box.h) * height;
  const xm = (x0 + x1) / 2, ym = (y0 + y1) / 2;
  const at = { nw: [x0, y0], n: [xm, y0], ne: [x1, y0], e: [x1, ym], se: [x1, y1], s: [xm, y1], sw: [x0, y1], w: [x0, ym] };
  return HANDLES.map(h => [h, ...at[h]]);
}

/** 框层 SVG：scale = 原图像素 / 屏幕像素，用来把把手、字号换算成固定的屏幕尺寸。 */
export function overlayView(image, sel, scale) {
  const width = Math.max(1, Number(image.width) || 1), height = Math.max(1, Number(image.height) || 1);
  const labels = boxLabels(image.boxes);
  const font = 12 * scale, pad = 4 * scale;
  return html`<svg class="an-overlay" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="框位">
    ${image.boxes.map((box, i) => html`<g class="an-box an-box--${box.role}${sel === i ? ' is-selected' : ''}">
      <rect class="an-box__rect" data-i="${i}" x="${box.x * width}" y="${box.y * height}" width="${box.w * width}" height="${box.h * height}"></rect>
      <text class="an-box__label" x="${box.x * width + pad}" y="${box.y * height + font + pad}" font-size="${font}">${labels[i]}</text>
    </g>`)}
    ${sel != null && image.boxes[sel] ? handlePoints(image.boxes[sel], width, height).map(([h, x, y]) => html`<rect class="an-handle" data-h="${h}" x="${x - 5 * scale}" y="${y - 5 * scale}" width="${10 * scale}" height="${10 * scale}"></rect>`) : ''}
  </svg>`;
}

export function createCanvas(root, store) {
  const scroll = root.querySelector('#an-scroll');
  const canvas = root.querySelector('#an-canvas');
  let shown = null;
  let shownZoom = null;
  let gesture = null;
  let frame = 0;
  let layer = null, guides = null, img = null;

  const image = () => store.current();
  const fitWidth = () => {
    const style = getComputedStyle(scroll);
    return Math.max(160, scroll.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight));
  };
  const displayWidth = () => Math.round(fitWidth() * store.state.zoom);

  function mount(current) {
    render(canvas, html`<img class="an-img" src="${rawUrl(current.id)}" alt="${current.file || ''}" width="${current.width}" height="${current.height}" draggable="false">
      <div class="an-layer"></div>
      <svg class="an-guides" viewBox="0 0 ${current.width} ${current.height}" preserveAspectRatio="none" aria-hidden="true"><line class="an-guide" x1="0" x2="0" y1="0" y2="0"></line><line class="an-guide" x1="0" x2="0" y1="0" y2="0"></line></svg>`);
    layer = canvas.querySelector('.an-layer');
    guides = canvas.querySelectorAll('.an-guide');
    img = canvas.querySelector('.an-img');
    shown = current.id;
    scroll.scrollTop = 0;
    scroll.scrollLeft = 0;
  }

  function paint() {
    const current = image();
    canvas.hidden = !current;
    if (!current) { shown = null; render(canvas, html``); return; }
    const zoomChanged = shownZoom !== null && shownZoom !== store.state.zoom && shown === current.id;
    const centre = zoomChanged ? (scroll.scrollTop + scroll.clientHeight / 2) / Math.max(1, scroll.scrollHeight) : 0;
    if (shown !== current.id) mount(current);
    // 显示尺寸写在 <img> 的 width / height 属性上（不用行内样式），画框层按画布铺满
    const width = displayWidth();
    img.setAttribute('width', width);
    img.setAttribute('height', Math.round(width * current.height / Math.max(1, current.width)));
    if (zoomChanged) scroll.scrollTop = centre * scroll.scrollHeight - scroll.clientHeight / 2;
    shownZoom = store.state.zoom;
    render(layer, overlayView(current, store.state.sel, current.width / Math.max(1, width)));
  }

  const zoomPct = () => { const current = image(); return current ? Math.round(displayWidth() / current.width * 100) : 100; };

  function point(clientX, clientY) { return pointIn(clientX, clientY, img.getBoundingClientRect()); }

  function crosshair(clientX, clientY) {
    const current = image();
    if (!current || !guides) return;
    const p = point(clientX, clientY);
    const x = p.x * current.width, y = p.y * current.height;
    guides[0].setAttribute('x1', x); guides[0].setAttribute('x2', x); guides[0].setAttribute('y1', 0); guides[0].setAttribute('y2', current.height);
    guides[1].setAttribute('y1', y); guides[1].setAttribute('y2', y); guides[1].setAttribute('x1', 0); guides[1].setAttribute('x2', current.width);
  }

  function apply() {
    const current = image();
    if (!gesture || !current) return;
    const box = current.boxes[gesture.index];
    if (!box) return;
    Object.assign(box, dragBox(gesture.mode, gesture.start, point(gesture.clientX, gesture.clientY), gesture.original, gesture.handle));
    paint();
  }

  function autoscroll() {
    frame = 0;
    if (!gesture) return;
    const bounds = scroll.getBoundingClientRect();
    const dy = edgeSpeed(gesture.clientY, bounds.top, bounds.bottom);
    const dx = edgeSpeed(gesture.clientX, bounds.left, bounds.right);
    if (dx || dy) {
      scroll.scrollTop += dy;
      scroll.scrollLeft += dx;
      apply();
      crosshair(gesture.clientX, gesture.clientY);
    }
    frame = requestAnimationFrame(autoscroll);
  }

  function onDown(event) {
    const current = image();
    if (!current || event.button !== 0 || !img) return;
    const start = point(event.clientX, event.clientY);
    const before = current.boxes.map(box => ({ ...box }));
    const handle = event.target.closest('[data-h]')?.dataset.h || '';
    const hit = event.target.closest('[data-i]');
    let index = handle ? store.state.sel : hit ? Number(hit.dataset.i) : -1;
    let mode = handle ? 'resize' : hit ? 'move' : 'draw';
    if (mode === 'draw') {
      const role = event.shiftKey ? OTHER_ROLE[store.state.role] : store.state.role;
      current.boxes.push({ role, x: start.x, y: start.y, w: 0, h: 0 });
      index = current.boxes.length - 1;
    }
    if (index == null || index < 0) return;
    store.state.sel = index;
    store.state.picked = mode !== 'draw';
    gesture = { mode, index, start, before, original: { ...current.boxes[index] }, handle, clientX: event.clientX, clientY: event.clientY };
    canvas.setPointerCapture(event.pointerId);
    canvas.classList.add('is-dragging');
    paint();
    store.emit();
    frame = frame || requestAnimationFrame(autoscroll);
    event.preventDefault();
  }

  function onMove(event) {
    crosshair(event.clientX, event.clientY);
    if (!gesture) return;
    gesture.clientX = event.clientX; gesture.clientY = event.clientY;
    apply();
  }

  function onUp() {
    if (!gesture) return;
    const current = image();
    const { mode, index, before } = gesture;
    gesture = null;
    cancelAnimationFrame(frame); frame = 0;
    canvas.classList.remove('is-dragging');
    if (!current) return;
    if (mode === 'draw' && tooSmall(current.boxes[index], img.clientWidth, img.clientHeight)) {
      current.boxes.splice(index, 1);
      store.state.sel = null;
    }
    store.commitGesture(before);
  }

  function onWheel(event) {
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    store.zoom(event.deltaY < 0 ? 1 : -1);
  }

  const onEnter = () => canvas.classList.add('is-pointing');
  const onLeave = () => { if (!gesture) canvas.classList.remove('is-pointing'); };
  const onResize = () => paint();
  canvas.addEventListener('pointerdown', onDown);
  canvas.addEventListener('pointermove', onMove);
  canvas.addEventListener('pointerup', onUp);
  canvas.addEventListener('pointercancel', onUp);
  canvas.addEventListener('pointerenter', onEnter);
  canvas.addEventListener('pointerleave', onLeave);
  scroll.addEventListener('wheel', onWheel, { passive: false });
  window.addEventListener('resize', onResize);

  return {
    paint, zoomPct,
    busy: () => !!gesture,
    /** Esc：拖动中就撤掉这次手势。 */
    cancel() {
      if (!gesture) return false;
      const current = image();
      if (current) current.boxes = gesture.before;
      gesture = null; canvas.classList.remove('is-dragging');
      store.state.sel = null; store.emit();
      return true;
    },
    dispose() {
      canvas.removeEventListener('pointerdown', onDown); canvas.removeEventListener('pointermove', onMove);
      canvas.removeEventListener('pointerup', onUp); canvas.removeEventListener('pointercancel', onUp);
      canvas.removeEventListener('pointerenter', onEnter); canvas.removeEventListener('pointerleave', onLeave); scroll.removeEventListener('wheel', onWheel);
      window.removeEventListener('resize', onResize);
    },
  };
}
