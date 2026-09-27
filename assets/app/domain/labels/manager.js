/** Native label management dialog. */
import { escape as escapeAttr, escape as escapeHtml, raw } from '../../core/html.js';
import { render } from '../../core/dom.js';
import { dialog, confirm, closeDialog } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { chipHtml } from './chips.js';
import { ensureColor } from './sheet.js';
import { normalizeColor, presetColors } from './color.js';
import { formValues as labelFormValues } from './model.js';
import { allLabels, nextLabelColor, loadLabels, labelRequest, refreshLabelViews, reloadLabelsAndData } from './state.js';

function labelManagerRowHtml(item) {
  const bonus = Number(item.priority_bonus || 0);
  return `<div class="label-manager-row" data-label-id="${escapeAttr(item.id)}">
    <span class="label-swatch" data-lbl-c="${ensureColor(item.color)}"></span>
    <span class="label-manager-name">${chipHtml(item, { lg: true, variant: 'solid' })}</span>
    <span class="label-manager-count">${item.count || 0} 题</span>
    <span class="label-manager-bonus" title="推荐优先级加成">${bonus > 0 ? `+${bonus.toFixed(2)}` : '—'}</span>
    <span class="label-manager-acts"><button class="btn sm" type="button" data-label-edit="${escapeAttr(item.id)}">编辑</button><button class="btn sm" type="button" data-label-merge="${escapeAttr(item.id)}" ${allLabels().length < 2 ? 'disabled' : ''}>合并</button><button class="btn sm danger" type="button" data-label-delete="${escapeAttr(item.id)}">删除</button></span>
  </div>`;
}
function labelSwatchesHtml(current, name = 'color') {
  const hex = normalizeColor(current);
  const presets = presetColors();
  const custom = !presets.includes(hex);
  return `<div class="lbl-swatches" data-lbl-swatches="${escapeAttr(name)}">${presets.map(color => `<button type="button" class="sw ${color === hex ? 'on' : ''}" data-lbl-c="${ensureColor(color)}" data-sw="${color}" title="${color}"></button>`).join('')}<span class="sw custom ${custom ? 'on' : ''}" title="自定义颜色"><input type="color" value="${escapeAttr(hex)}" data-sw-custom></span><input type="hidden" data-sw-value value="${escapeAttr(hex)}"></div>`;
}
function labelEditFormHtml(item) {
  return `<div class="label-edit">
    <div class="label-edit-row"><label>名称</label><input class="input" data-label-field="name" value="${escapeAttr(item.name || '')}" maxlength="80" placeholder="标记名称"></div>
    <div class="label-edit-row"><label>颜色</label>${labelSwatchesHtml(item.color)}</div>
    <div class="label-edit-row"><label>调度加成</label><input class="input label-bonus-input" type="number" data-label-field="priority_bonus" min="0" max="1" step="0.05" value="${escapeAttr(Number(item.priority_bonus || 0))}"><span class="hint">0 = 不影响推荐；例如给「考前必看」设 0.3 让它在推荐里上浮（上限受 label_bonus_cap 约束）</span></div>
    <div class="label-edit-row"><span class="grow"></span><button class="btn sm ghost" type="button" data-label-cancel>取消</button><button class="btn sm primary" type="button" data-label-save="${escapeAttr(item.id || '')}">${item.id ? '保存' : '＋ 新建'}</button></div>
  </div>`;
}
let managerNode = null;
export const managerOpen = () => !!managerNode?.open;
export function closeLabelManager() { if (managerNode) closeDialog(managerNode); }

export function openLabelManager() {
  if (managerOpen()) return;
  const body = raw(`<div class="label-manager-modal">
    <p class="hint">标记名称写在题目 Markdown 的 YAML「标记:」里，Obsidian 可读可改。改名、合并和删除会逐题重写引用它的文件并记 metadata commit；题目多时会花几秒。</p>
    <div class="label-manager-list"></div>
    <div class="label-manager-form" data-label-new-form>${labelEditFormHtml({ name: '', color: nextLabelColor(), priority_bonus: 0 })}</div>
  </div>`);
  const pending = dialog({
    title: '管理标记', size: 'lg', body, okText: '关闭', hideCancel: true,
    onOpen(modal) {
      managerNode = modal;
      const list = modal.querySelector('.label-manager-list');
      const freshForm = () => render(modal.querySelector('[data-label-new-form]'), raw(labelEditFormHtml({ name: '', color: nextLabelColor(), priority_bonus: 0 })));
      const renderList = () => render(list, raw(allLabels().length ? allLabels().map(labelManagerRowHtml).join('') : '<div class="empty-inline">还没有标记。用下面的表单新建，或在任意题目上点「＋ 标记」。</div>'));
      const readForm = root => labelFormValues({
        name: root.querySelector('[data-label-field="name"]')?.value,
        color: root.querySelector('[data-sw-value]')?.value,
        bonus: root.querySelector('[data-label-field="priority_bonus"]')?.value,
      }, nextLabelColor());
      renderList();
      modal.addEventListener('input', event => {
        const custom = event.target.closest('[data-sw-custom]');
        if (!custom) return;
        const wrap = custom.closest('[data-lbl-swatches]');
        wrap.querySelector('[data-sw-value]').value = custom.value;
        wrap.querySelectorAll('.sw').forEach(node => node.classList.toggle('on', node.classList.contains('custom')));
      });
      modal.addEventListener('click', async event => {
        const sw = event.target.closest('[data-sw]');
        if (sw) {
          const wrap = sw.closest('[data-lbl-swatches]');
          wrap.querySelector('[data-sw-value]').value = sw.dataset.sw;
          wrap.querySelectorAll('.sw').forEach(node => node.classList.toggle('on', node === sw));
          return;
        }
        const edit = event.target.closest('[data-label-edit]');
        if (edit) {
          const item = allLabels().find(label => label.id === edit.dataset.labelEdit);
          const row = edit.closest('.label-manager-row');
          if (!item || !row) return;
          row.classList.add('editing');
          render(row, raw(labelEditFormHtml(item)));
          row.querySelector('[data-label-field="name"]')?.focus();
          return;
        }
        if (event.target.closest('[data-label-cancel]')) {
          const row = event.target.closest('.label-manager-row');
          if (row) renderList(); else freshForm();
          return;
        }
        const save = event.target.closest('[data-label-save]');
        if (save) {
          const root = save.closest('.label-manager-row') || save.closest('[data-label-new-form]');
          const form = readForm(root);
          if (!form.name) { toast('标记名称不能为空', { kind: 'warn' }); return; }
          const id = save.dataset.labelSave || '';
          const item = id ? allLabels().find(label => label.id === id) : null;
          if (item && item.name !== form.name && (item.count || 0) > 200) {
            const ok = await confirm(`把「${item.name}」改名为「${form.name}」？`, { hint: `会重写 ${item.count} 道题的 Markdown，可能需要几秒钟。`, okText: '改名' });
            if (!ok) return;
          }
          save.disabled = true;
          try {
            const result = await labelRequest('/api/label/save', { ...form, id: id || undefined });
            await loadLabels(); renderList();
            if (!id) freshForm();
            if (item && item.name !== form.name) await reloadLabelsAndData(); else refreshLabelViews();
            toast(id ? `已保存「${form.name}」${result.label?.affected ? ` · 更新了 ${result.label.affected} 道题` : ''}` : `已新建「${form.name}」`, { kind: 'ok' });
          } catch (error) { toast(`保存标记失败：${error.message}`, { kind: 'error' }); }
          finally { save.disabled = false; }
          return;
        }
        const merge = event.target.closest('[data-label-merge]');
        if (merge) {
          const item = allLabels().find(label => label.id === merge.dataset.labelMerge);
          if (!item) return;
          const others = allLabels().filter(label => label.id !== item.id);
          const selectId = 'label-merge-target';
          const res = await dialog({ title: `把「${item.name}」合并到…`, okText: '合并',
            hint: `引用「${item.name}」的 ${item.count || 0} 道题会改成目标标记，然后删除「${item.name}」。`,
            body: raw(`<select class="ui-select" id="${selectId}">${others.map(label => `<option value="${escapeAttr(label.id)}">${escapeHtml(label.name)}（${label.count || 0} 题）</option>`).join('')}</select>`), focus: '#' + selectId });
          if (!res.ok) return;
          try {
            const result = await labelRequest('/api/label/merge', { from: item.id, into: res.values[selectId] });
            await reloadLabelsAndData(); renderList();
            toast(`已合并到「${result.into}」，影响 ${result.affected} 道题`, { kind: 'ok' });
          } catch (error) { toast(`合并失败：${error.message}`, { kind: 'error' }); }
          return;
        }
        const remove = event.target.closest('[data-label-delete]');
        if (!remove) return;
        const item = allLabels().find(label => label.id === remove.dataset.labelDelete);
        if (!item) return;
        const ok = await confirm(`删除标记「${item.name}」？`, { hint: `会从 ${item.count || 0} 道题的 YAML 里移除它；题目本身不受影响。`, okText: '删除', danger: true });
        if (!ok) return;
        try {
          await labelRequest('/api/label/delete', { id: item.id, detach: true });
          await reloadLabelsAndData(); renderList();
          toast(`已删除「${item.name}」`, { kind: 'ok' });
        } catch (error) { toast(`删除标记失败：${error.message}`, { kind: 'error' }); }
      });
    },
  });
  pending.finally(() => { managerNode = null; });
  return pending;
}
