import test from 'node:test';
import assert from 'node:assert/strict';
import { newQuickState, createPayload, mergeClassification, afterCreate } from '../../assets/app/features/create/state.js';
import { quickView } from '../../assets/app/features/create/quick-view.js';

test('快速录入请求保留题目与答案图片的分区、标记和知识点', () => {
  const state = newQuickState();
  assert.deepEqual(createPayload(state), { ok: false, error: '请填写科目和分类' });
  Object.assign(state.form, { subject: ' 数学 ', category: ' 函数 ', difficulty: '7', related: '导数，极值', question: '题面', answer: '解析', cause: '审题', note: ' p.3 ' });
  state.labels = ['待攻克'];
  state.images.q = [{ id: 1, dataUrl: 'data:image/png;base64,QQ==' }];
  state.images.a = [{ id: 2, dataUrl: 'data:image/png;base64,Qg==' }];
  assert.deepEqual(createPayload(state).data, {
    subject: '数学', category: '函数', difficulty: 7, note: 'p.3', related_tags: ['导数', '极值'], labels: ['待攻克'],
    question_text: '题面', answer_text: '解析', cause: '审题',
    question_images: [{ data: 'data:image/png;base64,QQ==' }], answer_images: [{ data: 'data:image/png;base64,Qg==' }],
  });
});

test('分类识别只填空缺项，提交后保留录入上下文并清空内容与图片', () => {
  const state = newQuickState();
  Object.assign(state.form, { subject: '数学', category: '函数', related: '极值', question: '题面', answer: '解析', cause: '审题', note: 'p.4' });
  state.form = mergeClassification(state.form, { subject: '物理', category: '动力学', difficulty: 8, knowledge_tags: ['极值', '定义域'] });
  assert.equal(state.form.subject, '数学');
  assert.equal(state.form.category, '函数');
  assert.equal(state.form.related, '极值, 定义域');
  assert.equal(state.form.difficulty, '8');
  state.labels = ['待攻克'];
  state.images.q = [{ id: 1, dataUrl: 'data:a' }];
  const next = afterCreate(state);
  assert.deepEqual(next.images, { q: [], a: [] });
  assert.deepEqual([next.form.subject, next.form.category, next.form.related, next.form.note, next.labels[0]], ['数学', '函数', '极值, 定义域', 'p.4', '待攻克']);
  assert.deepEqual([next.form.question, next.form.answer, next.form.cause], ['', '', '']);
});

test('快速录入视图只有委托动作、图片区域各自可选文件', () => {
  const markup = quickView(newQuickState()).text;
  assert.equal(markup.includes('onclick='), false);
  assert.equal(markup.includes('style='), false);
  assert.match(markup, /id="cr-q-file"[^>]*multiple/);
  assert.match(markup, /id="cr-a-file"[^>]*multiple/);
  assert.match(markup, /data-action="create.submit"/);
});
