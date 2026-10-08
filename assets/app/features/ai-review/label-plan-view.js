/** 标记整理：整批范围、跨科目开关、逐题理由、有限人工修订和真实结果。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { isPending } from './state.js';
import { pageOf, planRefs } from './label-plan-state.js';

const actionName = action => ({ create: '创建', update: '编辑', merge: '合并', delete: '删除' })[action];
const names = values => values?.join('、') || '无标记';
const arg = (...parts) => JSON.stringify(parts);
function definition(s, op) {
  const edited = s.edited.label_changes?.find(row => row.change_id === op.change_id) || op;
  const editable = isPending(s.item) && s.editing;
  return html`<section class="arv-label-definition" data-key="label-${op.change_id}">
    <div class="arv-label-heading"><strong>${actionName(op.action)} · ${op.before?.name || op.after?.name}</strong><span class="arv-muted">${op.affected_count} 道引用</span></div>
    <p>${op.action === 'merge' ? `迁移到 ${op.target_name || op.target_id}，合并后去重并保留目标定义。` : op.action === 'delete' ? '摘除全部引用，保留题目正文和其他标记。' : `${op.before?.name || '新标记'} → ${op.after?.name}`}</p>
    ${op.reason ? html`<p class="arv-muted">${op.reason}</p>` : ''}
    ${op.cross_scope ? html`<p class="arv-muted">跨范围影响：${Object.entries(op.affected_subject_counts || {}).map(([subject, count]) => `${subject} ${count} 题`).join(' · ')}。默认不执行，勾选后更新完整预览。</p>
      ${isPending(s.item) ? html`<label class="arv-label-check"><input type="checkbox" data-change="ai-review.labelCross" data-arg="${op.change_id}" ${edited.enabled ? html`checked` : ''} ${s.busy || s.dirty ? html`disabled` : ''}>允许此项跨范围变更${s.dirty ? '（请先保存其他修订）' : ''}</label>` : ''}` : ''}
    ${editable ? html`<label class="arv-label-check"><input type="checkbox" data-change="ai-review.labelField" data-arg="${arg('definition', op.change_id, 'enabled')}" ${edited.enabled ? html`checked` : ''} ${s.busy ? html`disabled` : ''}>纳入整批方案</label>
      ${op.after ? html`<div class="arv-label-fields"><label class="arv-field">名称<input class="ui-input" maxlength="80" value="${edited.name}" data-input="ai-review.labelField" data-arg="${arg('definition', op.change_id, 'name')}"></label>
      <label class="arv-field">颜色<input class="ui-input" type="color" value="${edited.color}" data-input="ai-review.labelField" data-arg="${arg('definition', op.change_id, 'color')}"></label>
      <label class="arv-field">排序<input class="ui-input" type="number" min="1" value="${edited.order}" data-input="ai-review.labelField" data-arg="${arg('definition', op.change_id, 'order')}"></label></div>` : ''}`
      : html`<p class="arv-muted">${op.enabled ? '纳入执行' : '已排除'}${op.after?.priority_bonus === 0 && op.action === 'create' ? ' · 新标记调度加成为 0' : ''}</p>`}
  </section>`;
}
export function labelPlanView(s) {
  const p = s.item.preview || {}, result = s.item.result;
  const applied = ['applied', 'unchanged'].includes(s.item.status) && result;
  const items = applied ? result.details || [] : p.items || [];
  const page = pageOf(items, s.labelPage);
  const editing = isPending(s.item) && s.editing;
  const refs = planRefs(s.item);
  const ops = applied ? result.label_changes || [] : p.label_changes || [];
  const groups = [ops.filter(op => !op.cross_scope), ops.filter(op => op.cross_scope)];
  return html`<section class="arv-label-plan" aria-label="整批标记方案">
    <p>${p.reason}</p><p class="arv-muted">范围：${[p.scope?.subject, p.scope?.category].filter(Boolean).join(' / ') || '全部科目'} · ${p.scope?.question_ids?.length ? `${p.scope.question_ids.length} 道指定题目` : '按筛选范围'} · 待判断 ${p.counts?.uncertain || 0} 题</p>
    ${groups.map((group, index) => group.length ? html`<section aria-label="${index ? '跨范围定义变更' : '定义变更'}"><h3>${index ? '跨范围变更 · 需要明确选择' : '标记定义'}</h3>${each(group, op => op.change_id, op => definition(s, op))}</section>` : '')}
    <h3>${applied ? '实际执行结果' : '逐题归类与理由'} · ${items.length} 题</h3>
    ${each(page.items, q => q.question_id, q => {
      const edit = s.edited.question_changes?.find(row => row.question_id === q.question_id);
      return html`<section class="arv-label-question" data-key="question-${q.question_id}"><div class="arv-label-heading"><strong>${q.uid}</strong><span class="arv-muted">${q.subject} / ${q.category}${q.cross_scope ? ' · 跨范围' : ''}</span></div>
        <p>${names(q.before)} → ${names(q.after)}</p>
        ${q.proposed_after && JSON.stringify(q.after) !== JSON.stringify(q.proposed_after) ? html`<p class="arv-muted">未纳入的建议：${names(q.proposed_after)}</p>` : ''}
        <p>${q.uncertain_reason ? `待判断：${q.uncertain_reason}` : q.reason || '标记定义级联变更'}</p>
        <span class="arv-muted">${q.changed ? applied ? '已变更' : '将变更' : '无需变更或已排除'}</span>
        ${editing ? html`<label class="arv-label-check"><input type="checkbox" data-change="ai-review.labelField" data-arg="${arg('exclude', q.question_id, 'enabled')}" ${s.edited.excluded_question_ids?.includes(q.question_id) ? html`checked` : ''}>排除此题（级联时同步取消对应定义操作）</label>
          ${edit ? html`<label class="arv-label-check"><input type="checkbox" data-change="ai-review.labelField" data-arg="${arg('question', q.question_id, 'enabled')}" ${edit.enabled ? html`checked` : ''}>纳入显式归类</label>
          ${!q.uncertain_reason ? html`<div class="arv-label-options">${refs.map(ref => html`<div><span>${ref.name}</span>${['add', 'remove'].map(field => html`<label class="arv-label-check"><input type="checkbox" data-change="ai-review.labelChoice" data-arg="${arg(q.question_id, field, ref.ref)}" ${edit[field].includes(ref.ref) ? html`checked` : ''}>${field === 'add' ? '添加' : '移除'}</label>`)}</div>`)}</div>` : ''}` : ''}` : ''}</section>`;
    })}
    <nav class="arv-label-pager" aria-label="逐题方案分页">${button({ label: '上一页', action: 'ai-review.labelPage', arg: String(page.page - 1), disabled: !page.page })}<span>第 ${page.page + 1} / ${page.pages} 页 · ${page.total} 题</span>${button({ label: '下一页', action: 'ai-review.labelPage', arg: String(page.page + 1), disabled: page.page + 1 >= page.pages })}</nav>
    ${applied && result.wrote && !result.revert_of && !result.reverted_by ? html`<div>${button({ label: '预览整批撤销', action: 'ai-review.labelRevert', disabled: s.busy })}</div>` : ''}
    ${result?.reverted_by ? html`<p role="status">本批已整批撤销，原始变更记录保留。</p>` : ''}
    ${s.revertPreview ? html`<section class="arv-label-revert" aria-label="整批撤销预览"><h3>撤销预览</h3>${s.revertPreview.ok ? html`<p>恢复 ${s.revertPreview.counts.definitions} 项定义与 ${s.revertPreview.counts.changed} 道题的本批变更，保留不相关的后续修改。</p>${(s.revertPreview.label_changes || []).map(op => html`<p>标记：${op.before ? `${op.before.name} · ${op.before.color} · 排序 ${op.before.order}` : '不存在'} → ${op.after ? `${op.after.name} · ${op.after.color} · 排序 ${op.after.order}` : '删除定义'}</p>`)}${pageOf(s.revertPreview.items, s.labelPage).items.map(q => html`<p>${q.uid}：${names(q.before)} → ${names(q.after)}</p>`)}${button({ label: '确认整批撤销', action: 'ai-review.labelRevertConfirm', variant: 'danger', disabled: s.busy })}` : html`<p role="alert">${s.revertPreview.conflicts.join('；')}</p>`}</section>` : ''}
  </section>`;
}
