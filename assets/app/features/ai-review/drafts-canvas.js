/** 草稿画布适配：只向共用画布提供展示图、区域和回调，不进入收件箱 store。 */
import { createCanvasController } from '../../domain/image-crop/process-canvas.js';
import { imageSha, imageUrl } from './drafts-state.js';
import { loadImage, previewSize, boxKey } from '../../domain/image-crop/crop.js';

const roleOf = section => section === '答案' ? 'answer' : 'question';
const sectionOf = role => role === 'answer' ? '答案' : '题目';

export function draftCanvasItem(draft, value, training, sha, mode = 'body', suggestions = []) {
  const source = (draft?.source_images || []).find(image => imageSha(image) === sha);
  if (!source) return null;
  const task = (draft.training_tasks || []).find(row => row.image_sha === sha);
  const rows = mode === 'training'
    ? (training?.[task?.id] || []).map(box => ({ id: box.id || box._key, role: roleOf(box.section),
      origin: box.box_origin || 'manual', ai_box: box.ai_box, ...box.box, target: 'training', taskId: task.id }))
    : (value?.blocks || []).filter(block => block.kind === 'image' && block.image_sha === sha && block.box)
      .map(block => ({ id: block.id || block._key, role: roleOf(block.section), origin: block.box_origin || 'manual',
        ai_box: block.ai_box, ...block.box, target: 'body' }));
  return { id: sha, file: source.ref || '来源截图', width: source.width, height: source.height,
    regions: rows, suggestions };
}

export function regionSection(region) { return sectionOf(region.role); }

export async function paintDraftCrops(root, value) {
  for (const canvas of root.querySelectorAll('canvas[data-draft-crop]')) {
    const block = (value?.blocks || []).find(row => (row.id || row._key) === canvas.dataset.draftCrop);
    if (!block?.box) continue;
    const key = `${block.image_sha}:${boxKey(block.box)}`;
    if (canvas.dataset.painted === key) continue;
    canvas.dataset.painted = key;
    try {
      const image = await loadImage({ id: block.image_sha }, imageUrl(block.image_sha));
      if (!canvas.isConnected) continue;
      const size = previewSize(block.box, image.naturalWidth, image.naturalHeight, 520);
      canvas.width = size.width; canvas.height = size.height;
      canvas.getContext('2d').drawImage(image,
        block.box.x * image.naturalWidth, block.box.y * image.naturalHeight, size.sw, size.sh,
        0, 0, size.width, size.height);
    } catch (_) { delete canvas.dataset.painted; }
  }
}

export function createDraftCanvas(root, canvasState, { afterEdit, createRegion, canEdit, onSelect }) {
  const controller = createCanvasController(root, () => canvasState, afterEdit, {
    stageSelector: '#drf-stage-img', zoomSelector: '#drf-canvas-zoom', filenameSelector: '#drf-canvas-file',
    imageId: 'drf-stage-src', maskId: 'drf-cut-mask', imageUrl: item => imageUrl(item.id),
    current: data => data.item, createRegion, canEdit, onSelect,
    onFinish({ item, region }) {
      // MCP 全幅原图经人工改为局部框后，来源应随范围改为人工框选。
      if (region?.origin === 'original' && (region.x !== 0 || region.y !== 0 || region.w !== 1 || region.h !== 1)) {
        region.origin = 'manual';
      }
      // 重画同一块时保留最后完成的新框；画得过小则旧框仍在。
      const seen = new Set();
      item.regions = [...item.regions].reverse().filter(row => {
        if (seen.has(row.id)) return false;
        seen.add(row.id); return true;
      }).reverse();
    },
  });
  const namespace = 'http://www.w3.org/2000/svg';
  function paint() {
    controller.paint();
    const overlay = root.querySelector('#drf-stage-img .crp-overlay');
    const item = canvasState.item;
    if (!overlay || !item?.suggestions?.length) return;
    for (const [index, suggestion] of item.suggestions.entries()) {
      const box = root.ownerDocument.createElementNS(namespace, 'rect');
      box.setAttribute('class', 'drf-suggestion');
      box.setAttribute('x', String(suggestion.x * item.width));
      box.setAttribute('y', String(suggestion.y * item.height));
      box.setAttribute('width', String(suggestion.w * item.width));
      box.setAttribute('height', String(suggestion.h * item.height));
      box.setAttribute('aria-label', `AI 候选框 ${index + 1}`);
      overlay.append(box);
    }
  }
  return { paint, dispose: controller.dispose };
}
