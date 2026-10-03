/** 草稿块的局部编辑、菜单与校验定位；所有改动仍由控制器显式保存。 */
import { openMenu, closeMenu } from '../../ui/menu.js';
import { confirm } from '../../ui/dialog.js';
import { draftIssue, imageSha, insertBlock, moveBlock, moveBlockToSection } from './drafts-state.js';

export function createDraftBlockActions(host, state, { isAlive, block, paint, markChanged, canvas }) {
  let nextLocalBlock = 0;
  const editable = () => isAlive() && state.value && !state.busy && ['cropping', 'review'].includes(state.draft?.status);
  function focus(selector, arg) {
    const el = [...host.querySelectorAll(selector)].find(node => arg == null || node.dataset.arg === arg);
    el?.focus({ preventScroll: true });
    el?.scrollIntoView({ block: 'nearest' });
  }
  function editBlock(key) {
    if (!editable() || !block(key)) return;
    state.editingBlock = state.editingBlock === key ? null : key;
    paint();
    focus(state.editingBlock ? '[data-input="ai-review.draftBlockText"], [data-input="ai-review.draftBlockNote"]' : '[data-action="ai-review.draftEditBlock"]', key);
  }
  function editImage(key) {
    const row = block(key);
    if (!editable() || row?.kind !== 'image') return;
    state.workspaceMode = 'source'; state.canvasSha = row.image_sha;
    state.canvasMode = 'body'; state.selectedBlock = key;
    canvas.refresh(); paint();
    focus('#drf-canvas-block');
  }
  function addBlock(section, kind, afterKey = null, sourceSha = null) {
    if (!editable() || !['题目', '答案'].includes(section) || !['text', 'image'].includes(kind)) return;
    const row = { _key: `local-${++nextLocalBlock}`, section, kind, text: kind === 'text' ? '' : null,
      image_sha: null, note: '', box: null, box_origin: null };
    if (kind === 'image') {
      row.image_sha = sourceSha;
      if (!state.value.source_images.includes(row.image_sha)) return;
    }
    if (!insertBlock(state.value.blocks, row, afterKey)) return;
    state.editingBlock = row._key;
    if (kind === 'image') { state.canvasSha = row.image_sha; state.canvasMode = 'body'; state.selectedBlock = row._key; canvas.refresh(); }
    markChanged();
    focus(kind === 'text' ? '[data-input="ai-review.draftBlockText"]' : '[data-input="ai-review.draftBlockNote"]', row._key);
  }
  async function addImage(section, anchor) {
    if (!editable() || !['题目', '答案'].includes(section)) return;
    const draftId = state.draft.id;
    const sources = [...(state.draft.source_images || []), ...(state.draft.conversation_images || [])];
    const choices = state.value.source_images.map(sha => ({ value: sha,
      label: sources.find(image => imageSha(image) === sha)?.ref || sha.slice(0, 10) }));
    if (!choices.length) return;
    const sha = choices.length === 1 ? choices[0].value : await openMenu(anchor, choices, { label: '选择图片来源' });
    if (editable() && state.draft.id === draftId && sha) addBlock(section, 'image', null, sha);
  }
  async function removeBlock(key) {
    const row = block(key);
    if (!editable() || !row) return;
    const draftId = state.draft.id;
    if (!await confirm('删除这个内容块？', { hint: '暂存后会保存删除结果；来源原图仍保留。', okText: '删除块', danger: true })) return;
    if (!editable() || state.draft.id !== draftId || !block(key)) return;
    const peers = state.value.blocks.filter(item => item.section === row.section);
    const index = peers.indexOf(row);
    state.value.blocks = state.value.blocks.filter(item => (item.id || item._key) !== key);
    if (state.editingBlock === key) state.editingBlock = null;
    if (state.selectedBlock === key) state.selectedBlock = null;
    canvas.refresh(); markChanged();
    const next = peers[index + 1] || peers[index - 1];
    focus(next ? '[data-action="ai-review.draftEditBlock"]' : '[data-action="ai-review.draftAddText"]', next ? next.id || next._key : row.section);
  }
  function move(key, step) {
    if (editable() && moveBlock(state.value.blocks, key, step)) { markChanged(); focus('[data-action="ai-review.draftBlockMenu"]', key); }
  }
  async function blockMenu(key, anchor) {
    const row = block(key);
    if (!editable() || !row) return;
    const draftId = state.draft.id;
    const peers = state.value.blocks.filter(item => item.section === row.section);
    const index = peers.indexOf(row);
    const section = row.section === '题目' ? '答案' : '题目';
    const action = await openMenu(anchor, [
      { value: 'up', label: '上移', disabled: index === 0 },
      { value: 'down', label: '下移', disabled: index === peers.length - 1 },
      { value: 'insert', label: '在下方插入文字块' },
      { value: 'section', label: `移到${section}` },
      { divider: true }, { value: 'remove', label: '删除块', danger: true },
    ], { label: `${row.section}内容块操作` });
    if (!editable() || state.draft.id !== draftId || !block(key)) return;
    if (action === 'up' || action === 'down') move(key, action === 'up' ? -1 : 1);
    else if (action === 'insert') addBlock(row.section, 'text', key);
    else if (action === 'section' && moveBlockToSection(state.value.blocks, key, section)) {
      canvas.refresh(); markChanged(); focus('[data-action="ai-review.draftBlockMenu"]', key);
    } else if (action === 'remove') await removeBlock(key);
  }
  function locateIssue() {
    if (!editable()) return;
    const issue = draftIssue(state.value);
    if (!issue) return;
    state.workspaceMode = 'review';
    if (issue.field) { state.fieldsEditing = true; paint(); focus('[data-input="ai-review.draftField"]', issue.field); }
    else if (issue.blockKey && block(issue.blockKey)?.kind === 'image') editImage(issue.blockKey);
    else if (issue.blockKey) { state.editingBlock = null; editBlock(issue.blockKey); }
    else if (issue.section) { paint(); focus('[data-action="ai-review.draftAddText"]', issue.section); }
    else { state.workspaceMode = 'source'; canvas.refresh(); paint(); focus('.drf-source-trigger'); }
  }
  function remapEditing(previousValue) {
    function savedKey(key) {
      const previous = previousValue?.blocks.find(row => (row.id || row._key) === key);
      if (!previous) return null;
      if (previous.id) return previous.id;
      const index = previousValue.blocks.filter(row => row.section === previous.section).indexOf(previous);
      return state.value.blocks.filter(row => row.section === previous.section)[index]?.id || null;
    }
    state.editingBlock = savedKey(state.editingBlock);
    state.selectedBlock = savedKey(state.selectedBlock);
  }
  return { editBlock, editImage, addBlock, addImage, removeBlock, move, blockMenu, locateIssue, remapEditing, dispose: closeMenu };
}
