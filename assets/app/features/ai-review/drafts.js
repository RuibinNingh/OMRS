import { imageValue } from '../../core/uploads.js';
/** 草稿审核控制器：一次只写一份草稿，失败时保留本地编辑。 */
import { get, post } from '../../core/api.js';
import { morph } from '../../core/dom.js';
import { currentDraftCounts, consumeDraftTarget, publishDraftChange, selectedDraftId, selectDraftId } from '../../domain/drafts.js';
import { toast } from '../../ui/toast.js';
const notify = (message, kind = 'info') => toast(message, { kind });
import { csvValues, draftProblems, editTraining, editValue, imageSha, imageUrl, trainingBoxPayload, updatePayload, commitProblem } from './drafts-state.js';
import { draftsView } from './drafts-view.js';
import { notifyHistoryChanged } from '../../domain/history.js';
import { reloadData } from '../../domain/data.js';
import { viewQ } from '../../domain/question/index.js';
import { dialog, confirm } from '../../ui/dialog.js';
import { openMenu } from '../../ui/menu.js';
import { openCreateLabelPicker } from '../../domain/labels/index.js';
import { cropDataUrl } from '../../domain/image-crop/crop.js';
import { paintDraftCrops } from './drafts-canvas.js';
import { createDraftCanvasControl } from './drafts-canvas-ctl.js';
import { createDraftJobPolling } from './drafts-job.js';
import { createDraftImageActions } from './drafts-image-actions.js';
import { previewDraftSource } from './drafts-preview.js';
import { createDraftBlockActions } from './drafts-block-actions.js';
import { confirmDraftCleanup, requestDraftCleanup } from './maintenance.js';
import { readDraftQueue } from './queue.js';
const responseError = result => result.error?.message || result.data?.msg || '请求失败';
export function createDrafts(root, ctx, options = {}) {
  const host = root.querySelector('#ib-stage-drafts');
  const state = { list: [], listLoaded: false, listError: '', filter: 'pending', selectedId: null,
    draft: null, value: null, saved: '', detailLoaded: true, detailError: '', dirty: false,
    busy: false, message: '', conflict: false, counts: currentDraftCounts(), training: {}, trainingSaved: '{}',
    canvasSha: null, canvasMode: 'body', selectedBlock: null, drawSection: '题目', job: null,
    workspaceMode: 'review', editingBlock: null, fieldsEditing: false, queueOpen: false, embedded: options.embedded, single: options.single };
  let alive = true, listRequest = 0, detailRequest = 0;
  const jobs = createDraftJobPolling(root, state, { isAlive: () => alive, loadDetail, paint, responseError });
  const canvas = createDraftCanvasControl(host, state, { markChanged, paint, block });
  const blocks = createDraftBlockActions(host, state, { isAlive: () => alive, block, paint, markChanged, canvas });
  const images = createDraftImageActions(state, { isAlive: () => alive, save, setDraft, showError, paint, canvas, jobs, markChanged, block });
  function paint() {
    if (!alive || !host || options.isActive?.() === false || canvas.isDragging()) return;
    state.counts = currentDraftCounts() || state.counts;
    morph(host, draftsView(state));
    canvas.bind();
    void paintDraftCrops(host, state.value);
  }
  function dirty() {
    state.dirty = Boolean(state.value && (JSON.stringify(state.value) !== state.saved
      || JSON.stringify(state.training) !== state.trainingSaved));
    state.message = ''; state.conflict = false;
  }
  function markChanged() { dirty(); paint(); }
  function setDraft(draft) {
    jobs.stop();
    if (state.draft?.id !== draft?.id) {
      blocks.dispose(); state.workspaceMode = 'review'; state.editingBlock = null; state.fieldsEditing = false;
      state.queueOpen = false;
    }
    state.draft = draft;
    state.value = editValue(draft);
    state.saved = JSON.stringify(state.value);
    state.training = editTraining(draft);
    state.trainingSaved = JSON.stringify(state.training);
    state.dirty = false; state.message = ''; state.conflict = false;
    state.detailLoaded = true; state.detailError = '';
    const shas = (draft?.source_images || []).map(imageSha);
    if (!shas.includes(state.canvasSha)) state.canvasSha = shas[0] || null;
    const source = (draft?.source_images || []).find(image => imageSha(image) === state.canvasSha);
    const task = (draft?.training_tasks || []).find(row => row.image_sha === state.canvasSha);
    const hasBodyImage = state.value?.blocks.some(row => row.kind === 'image' && row.image_sha === state.canvasSha);
    if (state.canvasMode === 'training' && (!task || (!source?.train && !task.force_crop && hasBodyImage))) state.canvasMode = 'body';
    if (draft?.status === 'done' && task?.force_crop && !hasBodyImage) state.canvasMode = 'training';
    if (draft?.status === 'cropping' && state.canvasSha) {
      state.selectedBlock = state.value.blocks.find(row => row.kind === 'image' && row.image_sha === state.canvasSha && !row.box)?.id || state.selectedBlock;
    }
    if (!state.value?.blocks.some(row => (row.id || row._key) === state.selectedBlock)) state.selectedBlock = null;
    canvas.refresh();
    const matchingFilter = draft && (['done', 'discarded'].includes(draft.status) ? draft.status : 'pending');
    if (matchingFilter && state.filter !== matchingFilter) { state.filter = matchingFilter; void loadList(); }
    paint();
    const active = (draft?.jobs || []).find(job => ['queued', 'running'].includes(job.status));
    if (active) jobs.start(active);
  }
  function showError(result, verb) {
    const reason = responseError(result);
    state.conflict = result.status === 409;
    state.message = state.conflict ? `${verb}冲突：草稿已在其他位置改变。本地编辑仍在，请核对后重新读取。` : `${verb}失败：${reason}`;
    paint();
    return false;
  }
  async function loadList({ reloadDetail = false } = {}) {
    const request = ++listRequest;
    const result = await readDraftQueue(state.filter, options.filterQueue);
    if (!alive || request !== listRequest) return false;
    if (!result.ok || !Array.isArray(result.data?.drafts)) {
      state.listError = responseError(result); state.listLoaded = true; paint(); return false;
    }
    state.listError = ''; state.listLoaded = true;
    state.list = result.data.drafts;
    paint();
    if (reloadDetail && state.selectedId && !state.dirty) await loadDetail(state.selectedId);
    return true;
  }
  async function loadDetail(id, { force = false } = {}) {
    if (!id) { state.selectedId = null; setDraft(null); return false; }
    if (!force && state.selectedId === id && state.draft && state.dirty) return true;
    const request = ++detailRequest, refreshing = state.draft?.id === id && Boolean(state.value);
    state.selectedId = id; state.detailLoaded = refreshing; state.detailError = ''; paint();
    const result = await get(`/api/drafts/item?id=${encodeURIComponent(id)}`);
    if (!alive || request !== detailRequest || state.selectedId !== id || (state.dirty && !force)) return false;
    if (!result.ok || !result.data?.draft) {
      if (!refreshing) { state.draft = null; state.value = null; }
      state.detailLoaded = true; state.detailError = responseError(result); paint(); return false;
    }
    if (!force && JSON.stringify(result.data.draft) === JSON.stringify(state.draft)) { state.detailLoaded = true; paint(); return true; }
    setDraft(result.data.draft);
    selectDraftId(id); options.onSelection?.(state.draft);
    return true;
  }
  function guard() {
    if (!state.dirty) return !state.busy;
    if (state.busy) return false;
    let choice = 'discard';
    return dialog({
      title: '草稿有未保存修改', hint: '选择如何处理当前草稿。',
      okText: '放弃修改并离开', cancelText: '留在当前', danger: true,
      onOk: async () => choice !== 'save' || await save(),
      onOpen(el) {
        el.querySelector('[data-dialog-ok]')?.addEventListener('click', event => { if (event.isTrusted) choice = 'discard'; });
        const saveButton = el.ownerDocument.createElement('button');
        saveButton.type = 'button'; saveButton.className = 'ui-btn ui-btn--primary';
        saveButton.textContent = '保存并离开';
        saveButton.addEventListener('click', () => { choice = 'save'; el.querySelector('[data-dialog-ok]')?.click(); });
        el.querySelector('.ui-dialog__foot')?.insertBefore(saveButton, el.querySelector('[data-dialog-ok]'));
      },
    }).then(result => {
      if (!result.ok) return false;
      if (choice === 'discard') {
        state.value = editValue(state.draft); state.saved = JSON.stringify(state.value);
        state.training = editTraining(state.draft); state.trainingSaved = JSON.stringify(state.training);
        state.dirty = false; canvas.refresh(); paint();
      }
      return true;
    });
  }
  async function open(id) {
    if (!id) return false;
    if (state.selectedId === id && !state.detailLoaded) return true;
    if (state.selectedId === id && state.draft && state.dirty) return true;
    if (state.selectedId === id && state.draft && !state.detailError) return true;
    if (state.selectedId && state.dirty && !await guard()) return false;
    return loadDetail(id);
  }
  async function navigate(step) {
    const index = state.list.findIndex(row => row.id === state.selectedId);
    const next = state.list[index + Number(step)];
    if (!next || state.busy) return false;
    if (state.dirty && !await guard()) return false;
    return loadDetail(next.id);
  }
  function toggleQueue() { state.queueOpen = !state.queueOpen; paint(); }
  function workspaceMode(mode) {
    if (!['review', 'source'].includes(mode)) return;
    state.workspaceMode = mode;
    paint();
    if (mode === 'source') requestAnimationFrame(() => { canvas.refresh(); void paintDraftCrops(host, state.value); });
  }
  function toggleSource() { workspaceMode(state.workspaceMode === 'source' ? 'review' : 'source'); }
  function editFields() {
    if (state.busy || !state.value || ['done', 'discarded'].includes(state.draft?.status)) return;
    state.fieldsEditing = !state.fieldsEditing; paint();
    if (state.fieldsEditing) host.querySelector('[data-input="ai-review.draftField"]')?.focus({ preventScroll: true });
  }
  async function queueMenu(anchor) {
    if (!alive || state.busy) return;
    const action = await openMenu(anchor, [{ value: 'reload', label: '刷新列表', disabled: state.busy },
      { value: 'cleanup', label: '清理过期草稿', disabled: state.busy }], { label: '草稿队列操作' });
    if (!alive) return;
    if (action === 'reload') await reload();
    else if (action === 'cleanup') await cleanup();
  }
  async function enter(id) {
    paint();
    await loadList();
    const target = id || consumeDraftTarget() || selectedDraftId();
    if (target) await open(target);
    else if (!state.selectedId && state.list.length) await open(state.list[0].id);
  }
  async function filter(next) {
    if (!['pending', 'done', 'discarded'].includes(next) || next === state.filter) return;
    if (state.dirty && !await guard()) {
      const select = host.querySelector('[data-change="ai-review.draftFilter"]'); if (select) select.value = state.filter; return;
    }
    state.filter = next;
    state.selectedId = null; state.draft = null; state.value = null;
    state.listLoaded = false; paint();
    if (await loadList() && state.list.length) await open(state.list[0].id);
  }
  async function reload({ changedIds = null } = {}) {
    const selectedChanged = !changedIds || changedIds.includes(state.selectedId);
    await loadList({ reloadDetail: selectedChanged && !state.busy && !state.dirty });
  }
  async function reloadDetail() {
    if (!state.selectedId) return;
    if (state.dirty && !await confirm('放弃本地修改并重新读取草稿？', { okText: '重新读取', danger: true })) return;
    await loadDetail(state.selectedId, { force: true });
  }
  function field(name, raw) {
    if (!state.value || state.busy || ['done', 'discarded'].includes(state.draft?.status) || !Object.hasOwn(state.value.fields, name)) return;
    state.value.fields[name] = ['knowledge_points', 'labels'].includes(name) ? csvValues(raw) : raw;
    markChanged();
  }
  function openLabels(anchor) {
    if (!state.value || state.busy || ['done', 'discarded'].includes(state.draft?.status)) return;
    openCreateLabelPicker(anchor, {
      get: () => state.value?.fields.labels || [],
      onSave(values) { if (!state.value) return; state.value.fields.labels = [...new Set(values || [])]; markChanged(); },
    });
  }
  function block(key) { return state.value?.blocks.find(row => (row.id || row._key) === key); }
  function blockField(key, name, raw) {
    if (state.busy || !state.value || ['done', 'discarded'].includes(state.draft?.status)) return;
    const row = block(key);
    if (!row) return;
    row[name] = raw;
    markChanged();
  }
  function sourceAdd() {
    if (state.busy || !state.value || ['done', 'discarded'].includes(state.draft?.status)) return;
    const sha = host.querySelector('#drf-source-select')?.value;
    if (!sha || !state.draft.conversation_images?.some(image => imageSha(image) === sha)) return;
    if (!state.value.source_images.includes(sha)) state.value.source_images.push(sha);
    markChanged();
  }
  function sourceRemove(sha) {
    if (state.draft?.source_channel === 'mcp' && state.draft.source_images?.some(image => imageSha(image) === sha)) {
      state.message = 'MCP 完整来源原图需保留，正文仍可人工编辑。'; paint(); return;
    }
    if (state.busy || !state.value || ['done', 'discarded'].includes(state.draft?.status) || state.value.blocks.some(row => row.image_sha === sha)) {
      state.message = '这张来源图仍被图片块使用，请先删除或更换该块。'; paint(); return;
    }
    state.value.source_images = state.value.source_images.filter(value => value !== sha);
    if (state.canvasSha === sha) state.canvasSha = state.value.source_images[0] || null;
    canvas.refresh();
    markChanged();
  }
  function whole(key) {
    const row = block(key);
    if (!row || row.kind !== 'image' || state.busy || ['done', 'discarded'].includes(state.draft?.status)) return;
    row.box = { x: 0, y: 0, w: 1, h: 1 };
    row.box_origin = row.box_origin === 'ai' ? 'ai_edited' : row.box_origin === 'original' ? 'manual' : row.box_origin || 'manual';
    canvas.refresh();
    markChanged();
  }
  async function retryTraining() {
    if (!state.draft || state.draft.status !== 'done' || state.busy) return false;
    if (state.dirty && !await save()) return false;
    state.busy = true; paint();
    try {
      const result = await post('/api/drafts/commit', { id: state.draft.id, revision: state.draft.revision });
      if (!alive) return false;
      if (!result.ok || !result.data?.draft) return showError(result, '重试训练登记');
      setDraft(result.data.draft); publishDraftChange([state.draft.id]);
      const training = result.data.training || {};
      state.message = training.failed?.length ? '仍有训练图登记失败，请查看任务错误。'
        : training.pending?.length ? '仍有训练图待补有效框，暂未完成登记。' : '训练登记已完成'; paint();
      return true;
    } finally { state.busy = false; paint(); }
  }
  async function cleanup() {
    if (state.busy || !await confirmDraftCleanup()) return;
    state.busy = true; paint();
    try {
      const { result, summary } = await requestDraftCleanup();
      if (!result.ok) { showError(result, '清理'); return; }
      state.message = summary; notify(summary); paint();
    } finally { state.busy = false; paint(); }
  }
  async function save() {
    if (!state.draft || !state.value || state.busy || state.draft.status === 'discarded') return false;
    if (!state.dirty) return true;
    const bodyDirty = JSON.stringify(state.value) !== state.saved;
    if (bodyDirty) {
      if (state.draft.status === 'done') return false;
      const problem = draftProblems(state.value);
      if (problem) { state.message = problem; paint(); return false; }
    }
    state.busy = true; state.message = ''; paint();
    try {
      if (bodyDirty) {
        const result = await post('/api/drafts/update', updatePayload(state.draft, state.value));
        if (!alive) return false;
        if (!result.ok || !result.data?.draft) return showError(result, '保存正文');
        const previousTraining = JSON.parse(state.trainingSaved);
        const changedTraining = Object.fromEntries(Object.entries(state.training).filter(([taskId, boxes]) =>
          JSON.stringify(boxes) !== JSON.stringify(previousTraining[taskId] || [])));
        state.draft = result.data.draft;
        const previousValue = state.value;
        state.value = editValue(state.draft); blocks.remapEditing(previousValue);
        state.saved = JSON.stringify(state.value);
        state.training = { ...editTraining(state.draft), ...changedTraining };
        state.trainingSaved = JSON.stringify(editTraining(state.draft));
        dirty(); canvas.refresh(); paint();
      }
      const trainingBoxes = trainingBoxPayload(state.draft, state.training, state.trainingSaved);
      if (trainingBoxes.length) {
        const result = await post('/api/drafts/boxes', { id: state.draft.id, revision: state.draft.revision,
          training_boxes: trainingBoxes });
        if (!alive) return false;
        if (!result.ok || !result.data?.draft) return showError(result, '保存训练框');
        setDraft(result.data.draft);
      }
      publishDraftChange([state.draft.id]);
      await loadList();
      state.message = '已保存'; paint();
      return true;
    } finally { state.busy = false; paint(); }
  }
  async function nextPending(previousIndex) { if (options.single) { await loadDetail(state.selectedId); return; }
    options.onPendingQueue?.();
    state.filter = 'pending'; state.list = state.list.filter(row => row.id !== state.selectedId);
    state.selectedId = null; selectDraftId(null); setDraft(null);
    if (!await loadList()) { options.onQueueError?.(state.listError); return; }
    const next = state.list[Math.max(0, Math.min(previousIndex, state.list.length - 1))];
    if (next) await loadDetail(next.id);
    else options.onSelection?.(null);
  }
  async function commit() {
    if (!state.draft || state.busy || ['done', 'discarded'].includes(state.draft.status)) return false;
    const currentId = state.draft.id;
    const previousIndex = state.list.findIndex(row => row.id === currentId);
    state.busy = true; paint();
    const latest = await get(`/api/drafts/item?id=${encodeURIComponent(currentId)}`);
    state.busy = false;
    if (!alive || state.selectedId !== currentId) return false;
    if (!latest.ok || !latest.data?.draft) return showError(latest, '核对草稿版本');
    if (latest.data.draft.revision !== state.draft.revision || latest.data.draft.status !== state.draft.status) {
      state.conflict = true;
      state.message = '草稿已有新版本。本地编辑已保留；请核对后重新读取，未执行入库。';
      paint(); return false;
    }
    if (commitProblem(state.value)) { state.message = commitProblem(state.value); paint(); return false; }
    if (state.dirty && !await save()) return false;
    if (state.draft.status !== 'review') { state.message = '草稿尚未达到可通过状态，请先保存并核对图片块。'; paint(); return false; }
    state.busy = true; paint();
    try {
      const id = state.draft.id;
      const crops = {};
      for (const row of state.draft.blocks || []) {
        if (row.kind !== 'image' || !row.box) continue;
        const { x, y, w, h } = row.box;
        if (x === 0 && y === 0 && w === 1 && h === 1) continue;
        crops[row.id] = await imageValue(await cropDataUrl({ id: row.image_sha }, row.box, 'image/png', .92, imageUrl(row.image_sha)), 'draft');
      }
      const payload = { id, revision: state.draft.revision, crops };
      let result = await post('/api/drafts/commit', payload);
      if (alive && !result.ok && result.status === 0) {
        // 响应丢失时以同一草稿版本重试；服务端入库操作按草稿身份复用。
        result = await post('/api/drafts/commit', payload);
      }
      if (!alive) return false;
      if (!result.ok || !result.data?.draft) return showError(result, '入库');
      publishDraftChange([id]);
      notifyHistoryChanged('create'); ctx.bus.emit('catalog:refresh');
      void reloadData();
      await nextPending(previousIndex);
      const failed = result.data.training?.failed || [];
      notify(`草稿已入库：${result.data.draft.uid || result.data.draft.question_id || id}${failed.length ? `；${failed.length} 张训练图登记失败，可在已入库列表重试` : ''}`);
      return true;
    } catch (error) {
      state.message = `入库前裁图失败：${error.message || error}`; paint(); return false;
    } finally { state.busy = false; paint(); }
  }
  async function discard() {
    if (!state.draft || state.busy || ['done', 'discarded'].includes(state.draft.status)) return false;
    if (!await confirm('确定丢弃这份草稿？', { hint: '丢弃后正文不能再编辑。', okText: '丢弃草稿', danger: true })) return false;
    state.busy = true; paint();
    try {
      const id = state.draft.id, previousIndex = state.list.findIndex(row => row.id === id);
      const result = await post('/api/drafts/discard', { id, revision: state.draft.revision });
      if (!alive) return false;
      if (!result.ok || !result.data?.draft) return showError(result, '丢弃');
      publishDraftChange([id]);
      await nextPending(previousIndex);
      notify('草稿已丢弃');
      return true;
    } finally { state.busy = false; paint(); }
  }
  function openQuestion() {
    if (state.draft?.uid && state.draft.question_available !== false) viewQ(state.draft.uid, 'q');
  }
  function beforeUnload(event) { if (!state.dirty) return; event.preventDefault(); event.returnValue = ''; }
  root.ownerDocument.defaultView.addEventListener('beforeunload', beforeUnload);
  return { state, paint, enter, open, navigate, toggleQueue, toggleSource, workspaceMode, editFields, queueMenu, guard, filter, reload, reloadDetail, field,
    openLabels, editBlock: blocks.editBlock, editImage: blocks.editImage, blockMenu: blocks.blockMenu, locateIssue: blocks.locateIssue,
    sourceAdd, sourceRemove, previewSource: sha => previewDraftSource(state, sha), addBlock: blocks.addBlock, addImage: blocks.addImage, whole, canvasImage: canvas.image, canvasMode: canvas.mode, canvasBlock: canvas.selectBlock,
    drawSection: canvas.section, clearBox: canvas.clearBox, trainingSection: canvas.trainingSection, trainingRemove: canvas.trainingRemove,
    trainToggle: images.trainToggle, extract: images.extract, detect: images.detect, acceptCandidate: images.acceptCandidate, retryTraining, cleanup,
    save, commit, discard, openQuestion,
    blockField, dispose() { alive = false; jobs.stop(); blocks.dispose(); canvas.dispose();
      root.ownerDocument.defaultView.removeEventListener('beforeunload', beforeUnload); } };
}
