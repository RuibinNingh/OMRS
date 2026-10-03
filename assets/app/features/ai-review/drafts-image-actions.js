/** 草稿来源图操作：训练开关、AI 框选建议与按块转文字。 */
import { post } from '../../core/api.js';
import { imageValue } from '../../core/uploads.js';
import { publishDraftChange } from '../../domain/drafts.js';
import { cropDataUrl } from '../../domain/image-crop/crop.js';
import { imageSha, imageUrl, latestDetectResult } from './drafts-state.js';

let nextSuggestedBox = 0;

export function createDraftImageActions(state, { isAlive, save, setDraft, showError, paint, canvas, jobs, markChanged, block }) {
  async function trainToggle(sha) {
    if (!state.draft || state.busy) return false;
    if (state.dirty && !await save()) return false;
    const source = (state.draft.source_images || []).find(image => imageSha(image) === sha);
    if (!source || source.inbox_item_id) return false;
    state.busy = true; paint();
    try {
      const result = await post('/api/drafts/image/train', { id: state.draft.id, revision: state.draft.revision,
        sha, enabled: !source.train });
      if (!isAlive()) return false;
      if (!result.ok || !result.data?.draft) return showError(result, '训练开关');
      setDraft(result.data.draft);
      const task = (state.draft.training_tasks || []).find(row => row.image_sha === sha);
      const bodyImage = state.value.blocks.some(row => row.kind === 'image' && row.image_sha === sha);
      if (!result.data.image?.train && !task?.force_crop && bodyImage && state.canvasMode === 'training') state.canvasMode = 'body';
      canvas.refresh(); publishDraftChange();
      state.message = source.train ? '已关闭这张图的训练登记' : '已开启这张图的训练登记'; paint();
      return true;
    } finally { state.busy = false; paint(); }
  }
  async function extract(key) {
    if (!state.draft || state.busy || state.job || !['cropping', 'review'].includes(state.draft.status)) return false;
    if (state.dirty && !await save()) return false;
    const row = state.draft.blocks.find(block => block.id === key && block.kind === 'image');
    if (!row?.box) { state.message = '请先为图片区块画框并保存。'; paint(); return false; }
    state.busy = true; paint();
    try {
      const crops = {};
      const { x, y, w, h } = row.box;
      if (!(x === 0 && y === 0 && w === 1 && h === 1)) {
        crops[key] = await imageValue(await cropDataUrl({ id: row.image_sha }, row.box, 'image/png', .92, imageUrl(row.image_sha)), 'draft');
      }
      const result = await post('/api/drafts/extract', { id: state.draft.id, revision: state.draft.revision,
        block_ids: [key], crops });
      if (!isAlive()) return false;
      if (!result.ok || !result.data?.job) return showError(result, '转文字');
      state.message = '转文字任务已提交；结果会自动同步。';
      jobs.start(result.data.job); paint();
      return true;
    } catch (error) { state.message = `准备裁图失败：${error.message || error}`; paint(); return false; }
    finally { state.busy = false; paint(); }
  }
  async function detect(sha) {
    if (!state.draft || state.busy || state.job || state.draft.status === 'discarded') return false;
    if (state.dirty && !await save()) return false;
    const source = (state.draft.source_images || []).find(image => imageSha(image) === sha);
    if (!source) return false;
    state.busy = true; paint();
    try {
      const result = await post('/api/drafts/detect', { id: state.draft.id, revision: state.draft.revision, sha });
      if (!isAlive()) return false;
      if (!result.ok || !result.data?.job) return showError(result, 'AI 框选');
      state.message = 'AI 框选任务已提交；候选结果会在这里显示。';
      jobs.start(result.data.job); paint();
      return true;
    } finally { state.busy = false; paint(); }
  }
  function acceptCandidate(index) {
    if (state.busy || !state.value || !state.draft || state.draft.status === 'discarded') return;
    const detected = latestDetectResult(state.draft, state.job, state.canvasSha);
    const row = detected?.result;
    const candidate = row?.status === 'suggested' && row.candidates?.[Number(index)];
    if (!candidate) return;
    if (detected.job.revision !== state.draft.revision) {
      state.message = '候选来自旧版草稿，请重新发起 AI 框选后再采用。'; paint(); return;
    }
    const boxValue = { x: candidate.x, y: candidate.y, w: candidate.w, h: candidate.h };
    const section = candidate.role === 'answer' ? '答案' : '题目';
    if (state.canvasMode === 'training') {
      const task = (state.draft.training_tasks || []).find(item => item.image_sha === state.canvasSha);
      if (!task || task.status === 'registered') return;
      const boxes = state.training[task.id] ||= [];
      if (boxes.some(item => item.section === section && JSON.stringify(item.box) === JSON.stringify(boxValue))) {
        state.message = '这个候选已在训练框中。'; paint(); return;
      }
      boxes.push({ _key: `local-suggest-${++nextSuggestedBox}`, task_id: task.id, section, box: boxValue,
        box_origin: 'ai', ai_box: { ...boxValue } });
    } else {
      if (state.draft.status === 'done') return;
      const target = block(state.selectedBlock);
      if (!target || target.kind !== 'image' || target.image_sha !== state.canvasSha || target.section !== section) {
        state.message = `请先选择本图的${section}图片区块，再采用候选。`; paint(); return;
      }
      target.box = boxValue; target.box_origin = 'ai'; target.ai_box = { ...boxValue };
    }
    canvas.refresh(); markChanged();
  }
  return { trainToggle, extract, detect, acceptCandidate };
}
