import { questionRefs } from '../../domain/question/ref.js';
/**
 * 题库页的对话框（全部基于 ui/dialog：焦点陷阱、Esc、关闭后焦点回触发元素）：
 * - 批量打标记：勾选添加 / 移除，另可当场新建一个标记并添加（取代旧弹层里的「＋ 新建标记」按钮 + 二次输入框）。
 * - 存为视图：ui/dialog 的 prompt。
 * - 管理视图预设：列表里「应用」直接关闭对话框并回传名字（隐藏字段 + data-dialog-ok），「删除」就地移除该行。
 */
import { html } from '../../core/html.js';
import { toElement } from '../../core/dom.js';
import { dialog, prompt } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { labelChip, listLabels, createLabel, batchLabels } from '../../domain/labels/index.js';
import { batchLabelPlan, describeView } from './state.js';

export async function openBatchLabels(uids) {
  const refs = questionRefs(uids);
  const names = listLabels().map(label => label.name);
  const options = prefix => (names.length
    ? names.map((name, i) => html`<label class="qlb-lblopt"><input type="checkbox" id="${prefix}-${i}">${labelChip(name)}</label>`)
    : html`<span class="qlb-hint">暂无标记</span>`);
  const res = await dialog({
    title: '批量打标记', size: 'md', okText: `保存到 ${uids.length} 道题`,
    hint: `已选 ${uids.length} 道题。勾选要添加 / 移除的标记，一次保存；没勾的标记保持原样。`,
    body: html`<div class="qlb-lbldlg">
      <p class="qlb-lbldlg__cap">添加</p><div class="qlb-lbldlg__opts">${options('qlb-lbl-add')}</div>
      <label class="ui-field__label" for="qlb-lbl-new">新建标记并添加</label>
      <input class="ui-input" id="qlb-lbl-new" placeholder="如：考前必看（留空则不新建）" maxlength="40" autocomplete="off">
      <p class="qlb-lbldlg__cap">移除</p><div class="qlb-lbldlg__opts">${options('qlb-lbl-rm')}</div>
    </div>`,
  });
  if (!res.ok) return false;
  const plan = batchLabelPlan(res.values, names);
  if (!plan.add.length && !plan.remove.length) return false;
  try {
    if (plan.create) await createLabel(plan.create);
    const result = await batchLabels(refs, plan.add, plan.remove);
    const failed = result?.failed?.length || 0;
    toast(`已更新 ${result?.changed ?? uids.length} 道题的标记${failed ? `，${failed} 道失败` : ''}`, { kind: failed ? 'warn' : 'ok' });
    return true;
  } catch (error) {
    toast(`批量保存标记失败：${error.message}`, { kind: 'error' });
    return false;
  }
}

export const askViewName = current => prompt('把当前筛选 + 排序 + 列设置存为视图', current || '', {
  placeholder: '如：考前必看·未掌握', hint: '存在本机浏览器里，下次一键回到同一子集。',
});

/** 返回要应用的视图名；关闭或只做了删除时返回空串。onDelete(name) 负责落盘。 */
export async function manageViews(views, { onDelete }) {
  const names = Object.keys(views);
  const node = toElement(html`<div class="qlb-vm">
    <input type="hidden" id="qlb-vm-pick" value="">
    ${names.map(name => html`<div class="qlb-vm__row" data-vm-row="${name}">
      <span class="qlb-vm__name">${name}<small>${describeView(views[name])}</small></span>
      <button type="button" class="ui-btn ui-btn--sm" data-vm-apply="${name}" data-dialog-ok>应用</button>
      <button type="button" class="ui-btn ui-btn--sm ui-btn--danger" data-vm-delete="${name}">删除</button>
    </div>`)}
  </div>`);
  node.addEventListener('click', event => {
    const apply = event.target.closest('[data-vm-apply]');
    if (apply) { node.querySelector('#qlb-vm-pick').value = apply.dataset.vmApply; return; }
    const remove = event.target.closest('[data-vm-delete]');
    if (!remove) return;
    onDelete(remove.dataset.vmDelete);
    remove.closest('[data-vm-row]')?.remove();
  });
  const res = await dialog({ title: '管理视图预设', content: node, okText: '关闭', hideCancel: true, size: 'md' });
  return res.ok ? String(res.values['qlb-vm-pick'] || '') : '';
}
