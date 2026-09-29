import test from 'node:test';
import assert from 'node:assert/strict';
import { draftPendingCount, editValue, updatePayload, draftProblems, commitProblem, moveBlock, latestDetectResult } from '../../assets/app/features/create/drafts-state.js';
import { draftsView } from '../../assets/app/features/create/drafts-view.js';

const sample = () => ({ id: 'DR-1', revision: 3, status: 'cropping', subject: '数学', category: '函数', difficulty: 5,
  knowledge_points: ['导数'], labels: [], cause: '审题不清', note: '', source_images: [{ sha256: 'a'.repeat(64), ref: 'IMG-1' }],
  blocks: [
    { id: 'q1', section: '题目', kind: 'text', text: '求 $f(x)$', note: '' },
    { id: 'q2', section: '题目', kind: 'image', image_sha: 'a'.repeat(64), box: null, note: '' },
    { id: 'a1', section: '答案', kind: 'text', text: '答案', note: '' },
  ] });

test('草稿保存携带 revision、有序块和 sha 数组，保留已有块身份', () => {
  const draft = sample();
  const value = editValue(draft);
  assert.deepEqual(value.source_images, ['a'.repeat(64)]);
  assert.equal(moveBlock(value.blocks, 'q2', -1), true);
  value.blocks[0].box = { x: 0, y: 0, w: 1, h: 1 };
  value.blocks[0].box_origin = 'manual';
  value.blocks.push({ _key: 'local-1', section: '答案', kind: 'text', text: '补充', note: '' });
  const payload = updatePayload(draft, value);
  assert.deepEqual([payload.id, payload.revision], ['DR-1', 3]);
  assert.deepEqual(payload.blocks.map(block => block.id), ['q2', 'q1', 'a1', undefined]);
  assert.deepEqual(payload.blocks[0].box, { x: 0, y: 0, w: 1, h: 1 });
  assert.deepEqual(payload.source_images, ['a'.repeat(64)]);
  assert.equal('status' in payload.fields, false);
});

test('无效文字、未关联图与未框图分别阻止错误操作', () => {
  const value = editValue(sample());
  assert.match(commitProblem(value), /手动画框/);
  assert.match(commitProblem(value), /使用整图/);
  value.blocks[1].box = { x: 0, y: 0, w: 1, h: 1 };
  assert.equal(commitProblem(value), '');
  value.blocks[0].text = '';
  assert.match(draftProblems(value), /文字块不能为空/);
  value.blocks[0].text = '题目';
  value.source_images = [];
  assert.match(draftProblems(value), /关联/);
  value.fields.difficulty = '11';
  assert.match(draftProblems(value), /难度/);
  assert.equal(draftPendingCount({ cropping: 2, review: 3 }), 5);
});

test('完整保存已有 AI 框时保留候选坐标和人工调整来源', () => {
  const draft = sample();
  draft.blocks[1].box = { x: .1, y: .2, w: .4, h: .3 };
  draft.blocks[1].box_origin = 'ai_edited';
  draft.blocks[1].ai_box = { x: .12, y: .21, w: .39, h: .31 };
  const payload = updatePayload(draft, editValue(draft));
  assert.deepEqual(payload.blocks[1].ai_box, draft.blocks[1].ai_box);
  assert.equal(payload.blocks[1].box_origin, 'ai_edited');
});

test('AI 歧义候选只展示建议；全文字 done 可独立保存训练框', () => {
  const draft = { ...sample(), status: 'done', blocks: [sample().blocks[0]],
    source_images: [{ ...sample().source_images[0], train: false }],
    training_tasks: [{ id: 'dt-1', image_sha: 'a'.repeat(64), force_crop: true, status: 'pending', boxes: [] }],
    jobs: [{ type: 'detect', status: 'done', result: [{ sha: 'a'.repeat(64), status: 'suggested',
      reason: '候选不止一个', candidates: [{ role: 'question', x: .1, y: .2, w: .3, h: .4, conf: .9 }] }] }],
  };
  assert.equal(latestDetectResult(draft, null, 'a'.repeat(64)).result.status, 'suggested');
  const markup = draftsView({ list: [draft], listLoaded: true, filter: 'done', selectedId: draft.id,
    draft, value: editValue(draft), training: { 'dt-1': [] }, canvasSha: 'a'.repeat(64), canvasMode: 'training',
    detailLoaded: true, dirty: true, busy: false, sourceOpen: true }).text;
  assert.match(markup, /独立训练框待核对/);
  assert.match(markup, /训练任务：待框选/);
  assert.match(markup, /采用为训练框/);
  assert.match(markup, /保存训练框/);
  assert.doesNotMatch(markup, /先在下方添加图片区块/);
});

test('草稿视图显示原图、只读完成态及来源不完整提示，文本被转义', () => {
  const draft = { ...sample(), sources_complete: false, subject: '<script>', status: 'done', uid: 'MATH-1' };
  const markup = draftsView({ list: [draft], listLoaded: true, filter: 'done', selectedId: draft.id,
    counts: { cropping: 1, review: 1 }, draft, value: editValue(draft), detailLoaded: true, dirty: false, busy: false,
    sourceOpen: true }).text;
  assert.match(markup, /来源未完整恢复/);
  assert.match(markup, /查看题目/);
  assert.match(markup, /&lt;script&gt;/);
  assert.doesNotMatch(markup, /data-action="create\.draftCommit"|onclick=|style=/);
  assert.match(markup, /打开来源截图/);
  const unavailable = draftsView({ list: [draft], listLoaded: true, filter: 'done', selectedId: draft.id,
    counts: { cropping: 0, review: 0 }, draft: { ...draft, question_available: false }, value: editValue(draft), detailLoaded: true }).text;
  assert.match(unavailable, /题目当前不可用/);
  assert.doesNotMatch(unavailable, /data-action="create\.draftQuestion"/);
});

test('审核默认先呈现题目，编辑与来源对照按需展开', () => {
  const draft = { ...sample(), status: 'review', blocks: [sample().blocks[0], sample().blocks[2]] };
  const state = { list: [draft], listLoaded: true, filter: 'pending', selectedId: draft.id,
    counts: { cropping: 0, review: 1 }, draft, value: editValue(draft), detailLoaded: true,
    reviewTab: 'question', fieldsEditing: false, sourceOpen: false, dirty: false, busy: false };
  const reading = draftsView(state).text;
  assert.match(reading, /第 1\/1 题/);
  assert.match(reading, /保存并入库，下一题/);
  assert.match(reading, /class="drf-md q-md"/);
  assert.match(reading, /class="drf-source-trigger"[^>]*aria-expanded="false"/);
  assert.doesNotMatch(reading, /class="drf-canvas"/);
  assert.doesNotMatch(reading, /data-input="create\.draftBlockText"|data-input="create\.draftField"/);
  const editing = draftsView({ ...state, editingBlock: 'q1', fieldsEditing: true, sourceOpen: true }).text;
  assert.match(editing, /data-input="create\.draftBlockText"/);
  assert.match(editing, /data-input="create\.draftField"/);
  assert.match(editing, /class="drf-source-trigger"[^>]*aria-expanded="true"/);
});
