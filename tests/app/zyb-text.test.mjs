import { test } from 'node:test';
import assert from 'node:assert/strict';
import { compactImages, expandImages, sourceProjection, editSource, toggleTextView, textView } from '../../assets/app/features/zuoyebang/zyb-text.js';
import { newZybState, bindCard, stashCard, extractionSnapshot, mergeExtraction, commitPayload } from '../../assets/app/features/zuoyebang/zyb-state.js';

const record = { id: 'text-card', status: 'ready', images: { question: {}, answer: {} }, extraction: {} };
const sample = '题干 $x=1$\n![示意图](https://example.test/a(b).png "标题)")\n![[本地图.png|320]]\n<img src="data:image/png;base64,AAAA" alt="a > b">\ndata:image/webp;base64,BBBB';

test('不同图片语法缩写且可逐字恢复原文', () => {
  const compact = compactImages(sample);
  assert.equal(compact.images.length, 4);
  assert.equal(compact.value, '题干 $x=1$\n[图片 1]\n[图片 2]\n[图片 3]\n[图片 4]');
  assert.equal(expandImages(compact.value, compact.images), sample);
});

test('编号避开原文中的同名占位文本，恢复只进行一次', () => {
  const text = '[图片 1] 是原文。![图](a.png "[图片 3]") ![[b.png]]';
  const compact = compactImages(text);
  assert.equal(compact.value, '[图片 1] 是原文。[图片 2] [图片 4]');
  assert.equal(expandImages(compact.value, compact.images), text);
});

test('连续编辑、删除及撤销占位符不会改串后续图片', () => {
  const section = { mode: 'text', text: sample };
  const initial = sourceProjection(section).value;
  assert.equal(editSource(section, initial.replace('[图片 1]\n', '')), true);
  assert.ok(!section.text.includes('https://example.test'));
  assert.equal(sourceProjection(section).value, initial.replace('[图片 1]\n', ''));
  editSource(section, sourceProjection(section).value + '\n人工补充');
  assert.ok(section.text.includes('![[本地图.png|320]]'));
  assert.ok(section.text.includes('data:image/webp;base64,BBBB'));
  editSource(section, initial);
  assert.equal(section.text, sample);
  assert.equal(editSource(section, initial), false);
});

test('粘贴新图片后往返视图会重新缩写，外部新正文不会沿用旧映射', () => {
  const section = { mode: 'text', view: 'source', text: '![[a.png]]' };
  editSource(section, sourceProjection(section).value + ' ![新图](new.png)');
  toggleTextView(section); toggleTextView(section);
  assert.equal(sourceProjection(section).value, '[图片 1] [图片 2]');
  section.text = '新的识别结果 ![[b.png]]';
  editSource(section, sourceProjection(section).value + ' 核对');
  assert.equal(section.text, '新的识别结果 ![[b.png]] 核对');
});

test('预览安全转义普通HTML，图片不产生img，空正文可切源码', () => {
  const section = { mode: 'text', text: sample + '\n<script>alert(1)</script>' };
  const output = String(textView(section, 'answer', false));
  assert.match(output, /data-zyb-preview="answer"/);
  assert.match(output, /class="math /);
  assert.match(output, /&lt;script&gt;/);
  assert.doesNotMatch(output, /<img|<script|https:\/\/example|AAAA|BBBB/);
  assert.match(String(textView({ mode: 'text', text: '' }, 'question', false)), /暂无正文，可切换源码补充/);
  assert.equal(toggleTextView({ mode: 'image' }), false);
});

test('切显示方式不改保存方式、脏状态或识别版本，迟到识别保留显示偏好', () => {
  const state = newZybState(); bindCard(state, record);
  state.sections.answer.mode = 'text';
  const snapshot = extractionSnapshot(state), versions = { ...state.versions };
  toggleTextView(state.sections.answer);
  assert.equal(state.dirty, false);
  assert.deepEqual(state.versions, versions);
  assert.equal(state.sections.answer.mode, 'text');
  mergeExtraction(state, { ...record, extraction: { answer: { mode: 'text', text: sample } } }, snapshot);
  assert.equal(state.sections.answer.view, 'source');
  assert.equal(state.sections.answer.text, sample);
});

test('切题、刷新草稿和提交始终保存真实原文，显示映射不进入提交', () => {
  const state = newZybState(); bindCard(state, record);
  state.form = { ...state.form, subject: '数学', category: '几何' };
  state.sections.answer = { mode: 'text', text: sample, view: 'source' };
  editSource(state.sections.answer, sourceProjection(state.sections.answer).value + '\n人工核对');
  stashCard(state);
  bindCard(state, { ...record, id: 'other-card' }); bindCard(state, record);
  assert.equal(state.sections.answer.view, 'source');
  assert.equal(state.sections.answer.text, sample + '\n人工核对');
  assert.deepEqual(commitPayload(state).sections.answer, { mode: 'text', text: sample + '\n人工核对' });
  assert.ok(!JSON.stringify(state.drafts).includes('"images"'));
});

test('已入库仍能切源码并复制，草稿只恢复显示偏好而不覆盖正式内容', () => {
  const state = newZybState(); bindCard(state, record);
  state.sections.answer = { mode: 'text', text: '未提交旧草稿', view: 'source' }; stashCard(state);
  bindCard(state, { ...record, commit: { result: { uid: '几何1' }, payload: {
    subject: '数学', category: '几何', difficulty: 5, related_tags: [], cause: '', labels: [],
    sections: { question: { mode: 'image', text: '' }, answer: { mode: 'text', text: sample } },
  } } });
  assert.equal(state.sections.answer.text, sample);
  assert.equal(state.sections.answer.view, 'source');
  const output = String(textView(state.sections.answer, 'answer', true));
  assert.match(output, /readonly/);
  assert.doesNotMatch(output, /disabled/);
  assert.match(output, /\[图片 1\]/);
});
