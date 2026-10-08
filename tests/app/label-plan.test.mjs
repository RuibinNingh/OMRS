import test from 'node:test';
import assert from 'node:assert/strict';
import { labelPlanValues, editLabelPlan, pageOf } from '../../assets/app/features/ai-review/label-plan-state.js';
import { labelPlanView } from '../../assets/app/features/ai-review/label-plan-view.js';

const item = { tool: 'propose_label_plan', kind: 'operation', status: 'pending_confirmation', payload: { label_changes: [{ action: 'create', change_id: '1', key: 'n', label_id: 'LB-n', enabled: true }], question_changes: [{ question_id: 'q', enabled: true, add: ['n'], remove: [] }] },
  preview: { label_changes: [{ action: 'create', change_id: '1', after: { name: '<危险>', color: '#123456', order: 1 }, enabled: true, affected_count: 0 }], items: [{ question_id: 'q', uid: '数学1', before: [], after: ['<危险>'], reason: '按答案归类', changed: true }] } };
test('修订不能改变稳定目标；勾选添加同步取消移除且不修改原数组', () => {
  const original = labelPlanValues(item);
  const edited = editLabelPlan(original, 'question', 'q', 'remove', ['n', true]);
  assert.deepEqual(original.question_changes[0].add, ['n']);
  assert.deepEqual(edited.question_changes[0].add, []);
  assert.deepEqual(edited.question_changes[0].remove, ['n']);
  assert.equal(edited.label_changes[0].change_id, '1');
});
test('三百题分页每页最多25项，越界页收敛', () => {
  const items = Array.from({length:300}, (_, id) => id);
  assert.equal(pageOf(items).items.length, 25);
  assert.equal(pageOf(items, 99).page, 11);
  assert.equal(pageOf(items, 11).items[24], 299);
});
test('方案渲染转义标记和理由，提供人工排除及统一确认所需表单', () => {
  const values = labelPlanValues(item);
  const view = String(labelPlanView({ item, edited: values, editing: true }));
  assert.ok(view.includes('&lt;危险&gt;'));
  assert.ok(view.includes('按答案归类'));
  assert.ok(view.includes('ai-review.labelField'));
  assert.ok(view.includes('排除此题'));
  assert.ok(!view.includes('<危险>'));
});
test('撤销预览显示定义逆变更；已撤销结果不再提供撤销入口', () => {
  const applied = { ...item, status: 'applied', result: { wrote: true, label_changes: [], details: [], counts: {} } };
  const s = { item: applied, edited: {}, revertPreview: { ok: true, counts: { definitions: 1, changed: 0 }, items: [],
    label_changes: [{ before: { name: '<新>', color: '#123456', order: 2 }, after: { name: '原名称', color: '#654321', order: 1 } }] } };
  const preview = String(labelPlanView(s));
  assert.ok(preview.includes('&lt;新&gt; · #123456 · 排序 2'));
  assert.ok(preview.includes('原名称 · #654321 · 排序 1'));
  assert.ok(preview.includes('ai-review.labelRevertConfirm'));
  applied.result.reverted_by = 'undo_complete';
  const completed = String(labelPlanView({ ...s, revertPreview: null }));
  assert.ok(completed.includes('本批已整批撤销'));
  assert.ok(!completed.includes('data-action="ai-review.labelRevert"'));
});
