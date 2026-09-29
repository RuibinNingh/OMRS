import test from 'node:test';
import assert from 'node:assert/strict';
import { newQuickState, createPayload, mergeClassification, afterCreate } from '../../assets/app/features/create/state.js';
import { quickView } from '../../assets/app/features/create/quick-view.js';

test('快速录入请求保留题目与答案图片的分区、标记和知识点', () => {
  const state = newQuickState();
  assert.deepEqual(createPayload(state), { ok: false, error: '请填写科目和分类' });
  Object.assign(state.form, { subject: ' 数学 ', category: ' 函数 ', difficulty: '7', related: '导数，极值', question: '题面', answer: '解析', cause: '审题' });
  state.labels = ['待攻克'];
  state.images.q = [{ id: 1, dataUrl: 'data:image/png;base64,QQ==' }];
  state.images.a = [{ id: 2, dataUrl: 'data:image/png;base64,Qg==' }];
  assert.deepEqual(createPayload(state).data, {
    subject: '数学', category: '函数', difficulty: 7, related_tags: ['导数', '极值'], labels: ['待攻克'],
    question_text: '题面', answer_text: '解析', cause: '审题',
    question_images: [{ data: 'data:image/png;base64,QQ==' }], answer_images: [{ data: 'data:image/png;base64,Qg==' }],
  });
});

test('分类识别只填空缺项，提交后保留录入上下文并清空内容与图片', () => {
  const state = newQuickState();
  Object.assign(state.form, { subject: '数学', category: '函数', related: '极值', question: '题面', answer: '解析', cause: '审题' });
  state.form = mergeClassification(state.form, { subject: '物理', category: '动力学', difficulty: 8, knowledge_tags: ['极值', '定义域'] });
  assert.equal(state.form.subject, '数学');
  assert.equal(state.form.category, '函数');
  assert.equal(state.form.related, '极值, 定义域');
  assert.equal(state.form.difficulty, '8');
  state.labels = ['待攻克'];
  state.images.q = [{ id: 1, dataUrl: 'data:a' }];
  const next = afterCreate(state);
  assert.deepEqual(next.images, { q: [], a: [] });
  assert.deepEqual([next.form.subject, next.form.category, next.form.related, next.labels[0]], ['数学', '函数', '极值, 定义域', '待攻克']);
  assert.deepEqual([next.form.question, next.form.answer, next.form.cause], ['', '', '']);
});

test('快速录入识别保留人工字段，错因候选和模型标记不能直接写入', () => {
  const form = { subject: '', category: '', difficulty: '5', related: '手写知识点', cause: '人工错因' };
  const result = { subject: '数学', category: '函数', difficulty: 9, knowledge_tags: ['导数'],
    labels: ['模型标记'], cause_candidate: { value: '粗心', evidence_text: '粗心' } };
  const next = mergeClassification(form, result, { manual: { difficulty: true, related: true, cause: true } });
  assert.deepEqual(next, { ...form, subject: '数学', category: '函数' });
  assert.equal('labels' in next, false);
});

test('快速录入视图只有委托动作、图片区域各自可选文件', () => {
  const markup = quickView(newQuickState()).text;
  assert.equal(markup.includes('onclick='), false);
  assert.equal(markup.includes('style='), false);
  assert.match(markup, /id="cr-q-file"[^>]*multiple/);
  assert.match(markup, /id="cr-a-file"[^>]*multiple/);
  assert.match(markup, /data-action="create.submit"/);
  assert.doesNotMatch(markup, /笔记本页码/);
});

import { liveItems, visibleItems, selectableItems, selectedCount, gridView } from '../../assets/app/features/create/grid-view.js';

test('收件箱网格只显示未丢弃图片，筛选与全选排除已录入', () => {
  const rows = [
    { id: 'a', status: 'pending', width: 64, height: 64, bytes: 10, file: '待处理.png', regions: [] },
    { id: 'b', status: 'done', width: 64, height: 64, bytes: 10, file: '已录入.png', regions: [] },
    { id: 'c', status: 'discarded', width: 64, height: 64, bytes: 10, file: '已丢弃.png', regions: [] },
  ];
  assert.deepEqual(liveItems(rows).map(row => row.id), ['a', 'b']);
  assert.deepEqual(visibleItems(rows, 'pending').map(row => row.id), ['a']);
  assert.deepEqual(selectableItems(liveItems(rows)).map(row => row.id), ['a']);
  assert.equal(selectedCount(rows, new Set(['a', 'b', 'c'])), 1);
  const markup = gridView({ items: rows, selected: new Set(['a']) }).text;
  assert.match(markup, /待处理.png/);
  assert.match(markup, /已录入.png/);
  assert.doesNotMatch(markup, /已丢弃.png/);
  assert.doesNotMatch(markup, /onclick=|style=/);
});

test('框位预览使用 SVG 坐标，文件名转义且无行内样式', () => {
  const markup = gridView({ items: [{ id: 'IB-1', status: 'boxed', width: 100, height: 100, bytes: 1024,
    file: '<题目>.png', regions: [{ x: .1, y: .2, w: .4, h: .3, role: 'question' }] }], selected: new Set() }).text;
  assert.match(markup, /<rect x="10"/);
  assert.match(markup, /&lt;题目&gt;\.png/);
  assert.doesNotMatch(markup, /style=|onclick=/);
});
