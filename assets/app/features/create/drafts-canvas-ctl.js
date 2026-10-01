/** 草稿画布控制：正文框与训练框只更新本地编辑值，保存由草稿控制器显式执行。 */
import { createDraftCanvas, draftCanvasItem, regionSection } from './drafts-canvas.js';
import { newRegion } from './process-state.js';
import { imageSha, latestDetectResult } from './drafts-state.js';

export function createDraftCanvasControl(host, state, { markChanged, paint, block }) {
  const data = { item: null, selR: null, drawRole: 'question', drawCard: 1, dragging: false };
  let controller = null;
  let stage = null;
  let nextTrainingBox = 0;

  function refresh() {
    const detected = latestDetectResult(state.draft, state.job, state.canvasSha);
    data.item = draftCanvasItem(state.draft, state.value, state.training, state.canvasSha, state.canvasMode,
      detected?.job.revision === state.draft?.revision && detected.result?.status === 'suggested'
        ? detected.result.candidates || [] : []);
    data.selR = state.canvasMode === 'body' ? state.selectedBlock : null;
    data.drawRole = state.drawSection === '答案' ? 'answer' : 'question';
    controller?.paint();
  }
  function changed() {
    const item = data.item;
    if (!item || !state.value) return;
    if (state.canvasMode === 'training') {
      const task = (state.draft.training_tasks || []).find(row => row.image_sha === state.canvasSha);
      if (!task) return;
      state.training[task.id] = item.regions.map(row => ({ ...(row.id?.startsWith('tb_') ? { id: row.id } : { _key: row.id }),
        task_id: task.id, section: regionSection(row), box: { x: row.x, y: row.y, w: row.w, h: row.h },
        box_origin: row.origin || 'manual', ai_box: row.ai_box || null }));
    } else {
      for (const row of state.value.blocks.filter(row => row.kind === 'image' && row.image_sha === state.canvasSha)) {
        const region = item.regions.find(region => region.id === (row.id || row._key));
        row.box = region ? { x: region.x, y: region.y, w: region.w, h: region.h } : null;
        row.box_origin = region ? region.origin || 'manual' : null;
      }
    }
    markChanged();
  }
  function createRegion({ start }) {
    if (state.canvasMode === 'training') {
      const task = (state.draft.training_tasks || []).find(row => row.image_sha === state.canvasSha);
      if (!task) { state.message = '训练任务尚未建立，请重新读取草稿。'; queueMicrotask(paint); return null; }
      return newRegion(1, data.drawRole, start.x, start.y, 0, 0,
        { id: `local-train-${++nextTrainingBox}`, target: 'training' });
    }
    const candidates = state.value.blocks.filter(row => row.kind === 'image' && row.image_sha === state.canvasSha);
    const target = candidates.find(row => (row.id || row._key) === state.selectedBlock) || candidates.find(row => !row.box);
    if (!target) { state.message = '先在下方添加图片区块，再选择它画框。'; queueMicrotask(paint); return null; }
    state.selectedBlock = target.id || target._key;
    return newRegion(1, target.section === '答案' ? 'answer' : 'question', start.x, start.y, 0, 0,
      { id: state.selectedBlock, origin: target.box_origin === 'ai' ? 'ai_edited' : target.box_origin === 'original' ? 'manual' : target.box_origin || 'manual',
        ai_box: target.ai_box || null, target: 'body' });
  }
  function bind() {
    const next = host.querySelector('#drf-stage-img');
    if (next === stage) { controller?.paint(); return; }
    controller?.dispose(); controller = null; stage = next;
    if (!next) return;
    controller = createDraftCanvas(host, data, {
      afterEdit: changed, createRegion,
      canEdit: () => !state.busy && (state.canvasMode === 'training'
        ? (state.draft?.training_tasks || []).some(task => task.image_sha === state.canvasSha && task.status !== 'registered')
        : ['cropping', 'review'].includes(state.draft?.status)),
      onSelect: ({ region }) => {
        if (state.canvasMode === 'body') state.selectedBlock = region.id;
        else state.drawSection = region.role === 'answer' ? '答案' : '题目';
      },
    });
    controller.paint();
  }
  function image(sha) {
    if (!state.value?.source_images.includes(sha)) return;
    state.canvasSha = sha;
    state.selectedBlock = state.value.blocks.find(row => row.kind === 'image' && row.image_sha === sha && !row.box)?.id
      || state.value.blocks.find(row => row.kind === 'image' && row.image_sha === sha)?.id || null;
    refresh(); paint();
  }
  function mode(value) {
    if (!['body', 'training'].includes(value)) return;
    const source = (state.draft?.source_images || []).find(image => imageSha(image) === state.canvasSha);
    const task = (state.draft?.training_tasks || []).find(row => row.image_sha === state.canvasSha);
    const bodyBlocks = (state.value?.blocks || []).some(row => row.kind === 'image' && row.image_sha === state.canvasSha);
    if (value === 'training' && (!task || (!source?.train && !task.force_crop && bodyBlocks))) return;
    state.canvasMode = value; refresh(); paint();
  }
  function selectBlock(key) {
    const row = block(key);
    if (!row || row.image_sha !== state.canvasSha) return;
    state.selectedBlock = key; data.selR = key; controller?.paint(); paint();
  }
  function section(value) {
    if (!['题目', '答案'].includes(value)) return;
    state.drawSection = value; data.drawRole = value === '答案' ? 'answer' : 'question'; paint();
  }
  function clearBox(key) {
    const row = block(key);
    if (!row || row.kind !== 'image' || state.busy || ['done', 'discarded'].includes(state.draft?.status)) return;
    row.box = null; row.box_origin = null; refresh(); markChanged();
  }
  function trainingSection(arg, value) {
    if (!['题目', '答案'].includes(value)) return;
    const [taskId, key] = String(arg).split('|');
    const row = state.training[taskId]?.find(box => (box.id || box._key) === key);
    if (!row || state.busy) return;
    row.section = value; refresh(); markChanged();
  }
  function trainingRemove(arg) {
    const [taskId, key] = String(arg).split('|');
    if (!state.training[taskId] || state.busy) return;
    state.training[taskId] = state.training[taskId].filter(box => (box.id || box._key) !== key);
    refresh(); markChanged();
  }
  return { refresh, bind, isDragging: () => data.dragging, image, mode, selectBlock, section, clearBox,
    trainingSection, trainingRemove, dispose() { controller?.dispose(); } };
}
