import test from 'node:test';
import assert from 'node:assert/strict';
import { draftPendingCount, editValue, updatePayload, draftProblems, commitProblem, moveBlock } from '../../assets/app/features/create/drafts-state.js';
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

test('草稿视图显示原图、只读完成态及来源不完整提示，文本被转义', () => {
  const draft = { ...sample(), sources_complete: false, subject: '<script>', status: 'done', uid: 'MATH-1' };
  const markup = draftsView({ list: [draft], listLoaded: true, filter: 'done', selectedId: draft.id,
    counts: { cropping: 1, review: 1 }, draft, value: editValue(draft), detailLoaded: true, dirty: false, busy: false }).text;
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
