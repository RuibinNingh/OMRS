/** 提醒素材页：新增、删除和新计划默认；既定计划的快照保持独立。 */
import { html } from '../../core/html.js';
import { post } from '../../core/api.js';
import { button } from '../../ui/button.js';
import { confirm } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { loadReminders, reminderImage, defaultIdentity, saveDefault } from './reminder-data.js';
import { chooseDefault } from './reminder-picker.js';
import { createReminder } from './reminder-create.js';

export const remindersState = { data: null, loading: false, error: '', busy: false };

export function remindersView(s) {
  const data = s.data, identity = defaultIdentity(data), current = data?.items.find(x => x.id === identity);
  return html`<section class="rem-library" id="sch-reminders" role="tabpanel" aria-labelledby="sch-tab-reminders">
    <div class="schd-heading"><div><h2 class="schd-heading__title">提醒素材</h2><p class="schd-meta">给复习清单的第一页，留一句有用的话。</p></div><div class="rem-actions">${button({ label: '导入 SVG', icon: 'upload', action: 'schedule.rcreate', arg: 'import', disabled: !data || s.busy })}${button({ label: 'AI 生成提醒', icon: 'sparkle', variant: 'primary', action: 'schedule.rcreate', arg: 'ai', disabled: !data || s.busy })}</div></div>
    ${s.error ? html`<p class="rem-error" role="alert">${s.error}</p>` : ''}
    ${s.loading ? html`<p class="rem-hint" role="status">正在读取提醒素材…</p>` : ''}
    <div class="rem-default"><div><h3>新计划默认提醒</h3><p class="rem-hint">${data?.default.enabled ? current?.name || '原有首页提醒' : '不显示'} · 只影响以后新建的计划</p></div><div class="rem-actions">${button({ label: '更换', action: 'schedule.rdefault', size: 'sm', disabled: !data || s.busy })}<label class="rem-check"><input type="checkbox" data-change="schedule.renabled" ${data?.default.enabled ? 'checked' : ''} ${!current || s.busy ? 'disabled' : ''}>自动用于新计划</label></div></div>
    <div class="rem-section"><span>全部素材 · ${data?.items.length || 0} 个</span>${button({ label: '刷新素材', icon: 'refresh', size: 'sm', variant: 'ghost', action: 'schedule.rload', loading: s.loading })}</div>
    <div class="rem-grid">${(data?.items || []).map(item => html`<article class="rem-card" data-key="${item.id}">${reminderImage(item, item.name)}<div class="rem-card-body"><h3>${item.name}${item.id === identity && data.default.enabled ? html`<span class="ui-badge">新计划默认</span>` : ''}</h3><div class="rem-card-foot"><span class="rem-hint">${item.source}</span><div class="rem-actions">${item.id !== identity || !data.default.enabled ? button({ label: '设为默认', size: 'sm', variant: 'ghost', action: 'schedule.rset', arg: item.id, disabled: s.busy }) : ''}${button({ label: '删除', icon: 'trash', size: 'sm', variant: 'ghost', action: 'schedule.rdelete', arg: item.id, disabled: s.busy })}</div></div></div></article>`)}</div>
    ${!s.loading && data && !data.items.length ? html`<p class="rem-empty">还没有提醒素材，可以让 AI 设计一张，或导入已有 SVG。</p>` : ''}</section>`;
}

export function createReminderLibrary(paint) {
  const s = remindersState;
  let sequence = 0, alive = true;
  const render = () => { if (alive) paint(); };
  async function load() {
    const mine = ++sequence; s.loading = true; s.error = ''; render();
    const response = await loadReminders();
    if (!alive || mine !== sequence) return;
    s.loading = false;
    if (response.ok) s.data = response.data; else s.error = response.error.message;
    render();
  }
  async function changeDefault(identity, enabled = true) {
    if (!s.data || s.busy) return;
    s.busy = true; render();
    const response = await saveDefault(s.data, identity, enabled);
    s.busy = false;
    if (!response.ok) toast(response.error.message, { kind: 'error' });
    await load();
  }
  return {
    load,
    setDefault: identity => changeDefault(identity),
    enabled: value => changeDefault(defaultIdentity(s.data), value),
    async choose() { if (!s.data || s.busy) return; const result = await chooseDefault(s.data); if (result) await changeDefault(result.value === 'off' ? '' : result.value); },
    async create(method) {
      if (!s.data || s.busy) return;
      s.busy = true; render();
      const item = await createReminder({ method, catalog: s.data });
      s.busy = false;
      if (item) toast(item.defaultError ? `素材已保存；默认未修改：${item.defaultError}` : '提醒已加入素材库', { kind: item.defaultError ? 'error' : 'ok' });
      await load();
    },
    async remove(identity) {
      const item = s.data?.items.find(x => x.id === identity);
      if (!item || s.busy) return;
      s.busy = true; render();
      const ok = await confirm(`删除「${item.name}」？`, { danger: true, okText: '删除素材', hint: `已有计划和已导出文件保留原提醒。${defaultIdentity(s.data) === identity ? '删除后，新计划默认改为不显示提醒。' : ''}` });
      if (ok) {
        const response = await post('/api/schedule-reminders/delete', { id: identity, expected_revision: item.revision });
        if (!response.ok) toast(response.error.message, { kind: 'error' });
      }
      s.busy = false; await load();
    },
    dispose() { alive = false; sequence += 1; s.loading = false; s.busy = false; },
  };
}
