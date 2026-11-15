/** AI生成只拿预览，用户保存时才新增素材；原有默认独立选择。 */
import { html } from '../../core/html.js';
import { morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { dialog } from '../../ui/dialog.js';
import { segmented } from '../../ui/segmented.js';
import { reminderImage, requestId, saveDefault } from './reminder-data.js';

export async function createReminder({ method = 'ai', catalog } = {}) {
  const s = { method, name: '', prompt: '', svg: '', style: 'steps', snapshot: null, default: false, busy: false, error: '' };
  const identity = requestId();
  let saved = null;
  const view = () => html`<div class="rem-create"><div class="rem-create-form"><fieldset ${s.busy ? 'disabled' : ''}>
    ${segmented({ name: 'reminderMethod', label: '新增方式', value: s.method, options: [{ value: 'ai', label: 'AI 生成' }, { value: 'import', label: '导入 SVG' }] })}
    <label class="rem-field">素材名称<input class="ui-input" id="reminderName" maxlength="80" value="${s.name}" placeholder="例如：先写思路，再动笔"></label>
    ${s.method === 'ai' ? html`<label class="rem-field">希望它提醒你什么？<textarea class="ui-textarea" id="reminderPrompt" rows="5" maxlength="2000" placeholder="例如：做一个极简提醒，提醒我先读题、列关系，再开始计算，适合黑白打印。">${s.prompt}</textarea></label>
      <label class="rem-field">版式风格<select class="ui-select" id="reminderStyle">${[['steps','步骤提示'],['minimal','极简文字'],['review','复盘清单']].map(([v,t]) => html`<option value="${v}" ${s.style === v ? 'selected' : ''}>${t}</option>`)}</select></label>`
      : html`<label class="rem-field">选择 SVG 文件<input class="ui-input" type="file" id="reminderFile" accept="image/svg+xml,.svg"></label><label class="rem-field">或粘贴 SVG<textarea class="ui-textarea" id="reminderSvg" rows="5" placeholder="粘贴已有SVG源码">${s.svg}</textarea></label>`}
    <button class="ui-btn" type="button" data-reminder-preview ${s.busy ? 'disabled' : ''}>${s.busy ? '正在生成与检查…' : s.method === 'ai' ? '生成预览' : '校验并预览'}</button>
    <p class="rem-hint">横向放在第一页，适合黑白打印；AI使用设置中的助手模型。</p></fieldset>
    ${s.error ? html`<p class="rem-error" role="alert">${s.error}</p>` : ''}</div>
    <aside class="rem-create-preview"><h3>提醒预览</h3>${reminderImage(s.snapshot)}<label class="rem-check"><input id="reminderDefault" type="checkbox" ${s.default ? 'checked' : ''} ${s.busy ? 'disabled' : ''}>同时设为新计划默认提醒</label><p class="rem-hint">保存后可在导出面板的画廊中选用。</p></aside></div>`;
  const result = await dialog({ id: 'schedule-reminder-create', title: '新增提醒', size: 'lg', body: view(), okText: '保存到素材库', dismissible: () => !s.busy,
    onOpen(el) {
      const body = el.querySelector('.ui-dialog__body');
      const paint = () => {
        morph(body, view());
        el.querySelector('[data-dialog-ok]').disabled = s.busy || !s.snapshot;
        el.querySelectorAll('[data-dialog-cancel]').forEach(button => { button.disabled = s.busy; });
      };
      el.__remPaint = paint;
      body.addEventListener('input', event => {
        const e = event.target;
        if (e.id === 'reminderName') s.name = e.value;
        if (e.id === 'reminderPrompt') s.prompt = e.value;
        if (e.id === 'reminderSvg') { s.svg = e.value; s.snapshot = null; el.querySelector('[data-dialog-ok]').disabled = true; }
      });
      body.addEventListener('change', async event => {
        const e = event.target;
        if (e.name === 'reminderMethod') { s.method = e.value; s.snapshot = null; s.svg = ''; s.error = ''; paint(); }
        if (e.id === 'reminderStyle') s.style = e.value;
        if (e.id === 'reminderDefault') s.default = e.checked;
        if (e.id === 'reminderFile' && e.files[0]) {
          const file = e.files[0];
          if (file.size > 256 * 1024) { s.error = 'SVG超过256KiB，请精简'; paint(); return; }
          s.svg = await file.text(); s.snapshot = null; paint();
        }
      });
      body.addEventListener('click', async event => {
        if (!event.target.closest('[data-reminder-preview]') || s.busy) return;
        s.busy = true; s.error = ''; paint();
        const response = await post(s.method === 'ai' ? '/api/schedule-reminders/generate' : '/api/schedule-banner/preview',
          s.method === 'ai' ? { prompt: s.prompt, style: s.style } : { svg: s.svg }, { timeout: 150000 });
        s.busy = false;
        if (response.ok) { s.snapshot = response.data.snapshot; s.svg = s.snapshot.svg; }
        else s.error = response.error.message;
        if (el.isConnected) paint();
      });
      paint();
    },
    async onOk(values, el) {
      s.name = values.reminderName || s.name;
      if (!s.snapshot || !s.name.trim()) { s.error = '请填写素材名称，并先生成或校验预览。'; el.__remPaint(); return false; }
      s.busy = true; s.error = ''; el.__remPaint();
      const response = await post('/api/schedule-reminders/create', { name: s.name, svg: s.svg, request_id: identity, source: s.method });
      s.busy = false;
      if (!response.ok) { s.error = response.error.message; el.__remPaint(); return false; }
      saved = response.data.item;
      if (s.default) {
        const setting = await saveDefault(catalog, saved.id);
        if (!setting.ok) saved.defaultError = setting.error.message;
      }
      return true;
    },
  });
  return result.ok ? saved : null;
}
