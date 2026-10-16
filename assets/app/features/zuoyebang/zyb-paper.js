/** 复用 OMRS 原图画布；只调整本次核对范围，不改变上游候选与位置关联。 */
import { createCanvasController } from '../../domain/image-crop/process-canvas.js';
import { regionBounds, searchRegions } from './zyb-state.js';

export function createPaper(host, state, { select, changed }) {
  const stage = host.querySelector('#zyb-paper');
  const data = { item: null, selR: null, dragging: false };
  let key = '', alive = true;
  const control = createCanvasController(host, () => data, () => {
    for (const region of data.item?.regions || []) {
      state.boxes[region.index] = { x: region.x * data.item.width, y: region.y * data.item.height,
        width: region.w * data.item.width, height: region.h * data.item.height };
    }
    changed();
  }, {
    stageSelector: '#zyb-paper', imageId: 'zyb-paper-image', maskId: 'zyb-cut-mask', current: value => value.item,
    imageUrl: item => item.url, createRegion: () => null,
    canEdit: () => state.adjusting && !state.busy && !state.job,
  });
  // 未进入调整模式时点框只选择；跨题切换统一经过页面的异步保护。
  function pointer(event) {
    const hit = event.target.closest('[data-rid]');
    if (state.adjusting && hit && Number(hit.dataset.rid) !== state.region) {
      event.stopImmediatePropagation(); void select(Number(hit.dataset.rid));
    }
  }
  function click(event) {
    const hit = event.target.closest('[data-rid]');
    if (hit && !state.adjusting) void select(Number(hit.dataset.rid));
  }
  stage.addEventListener('pointerdown', pointer, true);
  stage.addEventListener('click', click);
  function paint() {
    if (!alive || data.dragging) return;
    const image = state.search?.image;
    const next = JSON.stringify([state.search?.id, image, state.boxes, state.region, state.showBoxes, state.adjusting, stage.clientWidth]);
    if (next === key) return;
    key = next;
    data.item = image ? { id: state.search.id, file: '搜题原图', url: image.url, width: image.width, height: image.height,
      regions: state.showBoxes ? searchRegions(state).filter(row => regionBounds(state, row.index)).map(row => {
        const box = regionBounds(state, row.index);
        return { id: String(row.index), index: row.index, card: row.index + 1, role: 'question',
          x: box.x / image.width, y: box.y / image.height, w: box.width / image.width, h: box.height / image.height };
      }) : [] } : null;
    data.selR = state.adjusting && state.region != null ? String(state.region) : null;
    stage.classList.toggle('is-adjusting', state.adjusting);
    control.paint();
    stage.querySelector('img')?.classList.add('zyb-source-image');
    stage.querySelectorAll('.crp-box').forEach(box => box.classList.toggle('is-selected', Number(box.dataset.rid) === state.region));
    if (!image) return;
    const scale = image.width / Math.max(1, stage.clientWidth);
    stage.querySelectorAll('.crp-label').forEach(label => {
      const index = Number(label.parentElement.dataset.rid), box = regionBounds(state, index);
      label.textContent = String(searchRegions(state).findIndex(row => row.index === index) + 1).padStart(2, '0');
      label.setAttribute('x', '0'); label.setAttribute('y', '0');
      label.setAttribute('transform', `translate(${box.x + 7 * scale} ${box.y + 18 * scale}) scale(${scale})`);
    });
  }
  const resize = new ResizeObserver(paint);
  resize.observe(stage);
  return { paint, dispose() { alive = false; resize.disconnect(); control.dispose(); stage.removeEventListener('pointerdown', pointer, true); stage.removeEventListener('click', click); } };
}
