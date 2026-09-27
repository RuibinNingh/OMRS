/** 框选画布：原图与 SVG 坐标框留在 data-morph="skip" 子树，指针只由此控制器处理。 */
import { html } from '../../core/html.js';
import { render } from '../../core/dom.js';
import { draggedBox, newRegion, pointInImage, ROLES } from './process-state.js';

const rawUrl = id => `/api/inbox/raw?id=${encodeURIComponent(id)}`;

function handles(region, width, height, radius) {
  const x0 = region.x * width, x1 = (region.x + region.w) * width;
  const y0 = region.y * height, y1 = (region.y + region.h) * height;
  return [['nw', x0, y0], ['n', (x0 + x1) / 2, y0], ['ne', x1, y0],
    ['e', x1, (y0 + y1) / 2], ['se', x1, y1], ['s', (x0 + x1) / 2, y1],
    ['sw', x0, y1], ['w', x0, (y0 + y1) / 2]].map(([direction, x, y]) => html`
      <circle class="crp-handle" data-rid="${region.id}" data-h="${direction}" cx="${x}" cy="${y}" r="${radius}"></circle>`);
}

export function canvasView(item, selectedId = '', displayWidth = 600) {
  if (!item) return html``;
  const width = Math.max(1, Number(item.width) || 1);
  const height = Math.max(1, Number(item.height) || 1);
  const regions = item.regions || [];
  const radius = Math.max(2, 5 * width / Math.max(1, displayWidth));
  const labelOffset = 14 * width / Math.max(1, displayWidth);
  const multi = new Set(regions.map(region => region.card)).size > 1;
  return html`<img id="ib-stage-src" src="${rawUrl(item.id)}" alt="${item.file || ''}" width="${width}" height="${height}" draggable="false">
    <svg class="crp-cut" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
      <defs><mask id="crp-cut-mask"><rect width="100%" height="100%" fill="white"></rect>${regions.map(region => html`<rect x="${region.x * width}" y="${region.y * height}" width="${region.w * width}" height="${region.h * height}" fill="black"></rect>`)}</mask></defs>
      ${regions.length ? html`<rect class="crp-cut__shade" width="100%" height="100%" mask="url(#crp-cut-mask)"></rect>` : ''}
    </svg>
    <svg class="crp-overlay" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-label="图片框位">
      ${regions.map(region => html`<g data-rid="${region.id}">
        <rect class="crp-box${selectedId === region.id ? ' is-selected' : ''}" data-rid="${region.id}" data-role="${region.role}" x="${region.x * width}" y="${region.y * height}" width="${region.w * width}" height="${region.h * height}"></rect>
        <text class="crp-label" x="${region.x * width + radius}" y="${Math.max(labelOffset, region.y * height + labelOffset)}">${ROLES[region.role] || region.role}${multi ? ` · 题卡${region.card}` : ''}${region.origin === 'ai' ? ` · AI ${(region.conf ?? 0).toFixed(2)}` : region.origin === 'ai_edited' ? ' · AI 已调' : ''}</text>
        ${selectedId === region.id ? handles(region, width, height, radius) : ''}
      </g>`) }
    </svg>`;
}

export function createCanvasController(root, state, afterEdit) {
  const stage = root.querySelector('#ib-stage-img');
  const zoom = root.querySelector('#ib-pc-zoom');
  let gesture = null;

  function current() { const data = state(); return data.items.find(item => item.id === data.cur) || null; }
  function paint() {
    const data = state();
    const item = current();
    stage.classList.toggle('is-tall', !!item && item.height / item.width > 1.6);
    render(stage, canvasView(item, data.selR, stage.clientWidth || 600));
    zoom.textContent = item ? `${Math.round(stage.clientWidth / item.width * 100)}%` : '';
    root.querySelector('#ib-pc-fname').textContent = item ? `${item.file} · ${item.width}×${item.height}` : '';
  }
  function pointer(event) { const bounds = stage.getBoundingClientRect(); return pointInImage(event.clientX, event.clientY, bounds); }
  function finish() {
    if (!gesture) return;
    const data = state(); const item = current(); const { mode, region } = gesture;
    if (item && mode === 'draw' && (region.w * stage.clientWidth < 8 || region.h * stage.clientHeight < 8)) {
      item.regions = item.regions.filter(row => row !== region); data.selR = null;
    } else if (item && mode !== 'draw') {
      if (region.origin === 'ai') region.origin = 'ai_edited';
      if (region.text_status === 'done') region.text_status = 'stale';
    }
    gesture = null; data.dragging = false;
    afterEdit();
  }
  function onDown(event) {
    const data = state(); const item = current();
    if (!item || event.button !== 0) return;
    const start = pointer(event);
    const hit = event.target.closest('[data-rid]');
    const handle = event.target.closest('[data-h]');
    let region = hit && item.regions.find(row => row.id === hit.dataset.rid);
    const mode = region ? (handle ? 'resize' : 'move') : 'draw';
    if (!region) { region = newRegion(data.drawCard, data.drawRole, start.x, start.y, 0, 0); item.regions.push(region); }
    data.selR = region.id; data.dragging = true;
    gesture = { mode, region, start, original: { ...region }, handle: handle?.dataset.h || '' };
    stage.setPointerCapture(event.pointerId);
    paint(); event.preventDefault();
  }
  function onMove(event) {
    if (!gesture) return;
    Object.assign(gesture.region, draggedBox(gesture.mode, gesture.start, pointer(event), gesture.original, gesture.handle));
    paint();
  }
  stage.addEventListener('pointerdown', onDown);
  stage.addEventListener('pointermove', onMove);
  stage.addEventListener('pointerup', finish);
  stage.addEventListener('pointercancel', finish);
  return { paint, dispose() {
    stage.removeEventListener('pointerdown', onDown); stage.removeEventListener('pointermove', onMove);
    stage.removeEventListener('pointerup', finish); stage.removeEventListener('pointercancel', finish);
  } };
}
