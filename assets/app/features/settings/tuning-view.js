/** 学习参数编辑复用设置表单；高级参数默认折叠。 */
import { html } from '../../core/html.js';
import { TUNING_FIELDS } from './tuning-state.js';

const fieldView = field => html`<div class="form-group">
  <label for="st-tuning-${field.key}">${field.label}</label>
  <input class="ui-input" type="number" inputmode="decimal" id="st-tuning-${field.key}" min="${field.min}" max="${field.max ?? ''}" step="${field.step}" disabled>
  ${field.hint ? html`<p class="hint">${field.hint}</p>` : ''}
</div>`;

export const tuningView = () => html`<div class="card st-card" id="st-tuning-card">
  <div class="card-title">学习算法参数</div>
  <p class="hint st-lead">保存后立即按新参数重算全部历史，再同步统计与复习计划；数据较多时请等待完成。</p>
  <div class="st-fields st-grid3">${TUNING_FIELDS.slice(0, 4).map(fieldView)}</div>
  <details class="st-tuning-advanced"><summary>高级参数（15 项）</summary>
    <div class="st-fields st-grid3">${TUNING_FIELDS.slice(4).map(fieldView)}</div>
  </details>
  <div class="st-actions">
    <button class="ui-btn ui-btn--primary" type="button" id="st-tuning-save" data-action="settings.saveTuning" disabled>保存并重算历史</button>
    <button class="ui-btn" type="button" id="st-tuning-check" data-action="settings.checkTuning">核验当前状态</button>
  </div>
  <p class="st-status" id="st-tuning-status" role="status" aria-live="polite">正在读取学习参数…</p>
</div>`;
