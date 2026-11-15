/** 素材画廊共用于本次导出与新计划默认，取消不产生写入。 */
import { html } from '../../core/html.js';
import { morph } from '../../core/dom.js';
import { dialog } from '../../ui/dialog.js';
import { loadReminders, reminderImage, defaultIdentity } from './reminder-data.js';

export async function chooseReminder({ data, value = 'session', context = 'export', sessionId } = {}) {
  if (!data) {
    const response = await loadReminders(sessionId);
    if (!response.ok) return { error: response.error.message };
    data = response.data;
  }
  let selected = value;
  const items = data.items || [];
  const choices = () => html`<div class="rem-picker">
    <div class="rem-picker-options">${(context === 'export' ? [['session', '沿用计划提醒'], ['off', '不显示提醒']] : [['off', '不显示提醒']]).map(([id, label]) => html`<button class="ui-btn" type="button" data-reminder-id="${id}" aria-pressed="${selected === id}">${label}</button>`)}</div>
    ${items.length ? html`<div class="rem-grid">${items.map(item => html`<button class="rem-pick" type="button" data-key="${item.id}" data-reminder-id="${item.id}" aria-pressed="${selected === item.id}">${reminderImage(item, item.name)}<span class="rem-pick-label"><span>${item.name}</span><span>${selected === item.id ? '已选择' : ''}</span></span></button>`)}</div>` : html`<p class="rem-hint">还没有提醒素材，可在调度页「提醒素材」中生成或导入。</p>`}
    <p class="rem-hint" role="status">已选：${selected === 'session' ? '沿用计划提醒' : selected === 'off' ? '不显示提醒' : items.find(x => x.id === selected)?.name || '请选择提醒'}</p></div>`;
  const result = await dialog({ id: 'schedule-reminder-picker', title: '选择首页提醒', size: 'lg',
    hint: context === 'export' ? '只替换本次导出的提醒。' : '只用于以后新建的计划，已有计划保持原提醒。',
    body: choices(), okText: '使用所选提醒',
    onOpen(el) {
      const body = el.querySelector('.ui-dialog__body');
      body.addEventListener('click', event => {
        const pick = event.target.closest('[data-reminder-id]');
        if (pick) { selected = pick.dataset.reminderId; morph(body, choices()); }
      });
    },
  });
  if (!result.ok) return null;
  const snapshot = selected === 'session' ? data.plan_snapshot : items.find(x => x.id === selected);
  return { value: selected, snapshot, name: items.find(x => x.id === selected)?.name, data };
}

export const chooseDefault = data => chooseReminder({ data, context: 'default', value: data.default.enabled ? defaultIdentity(data) || 'off' : 'off' });
