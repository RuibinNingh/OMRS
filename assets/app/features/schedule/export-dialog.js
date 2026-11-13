/** 导出参数面板：草稿与已记忆参数分开；右侧为明确标注的排版示意。 */
import { html } from '../../core/html.js';
import { morph } from '../../core/dom.js';
import { dialog } from '../../ui/dialog.js';
import { segmented } from '../../ui/segmented.js';
import { DEFAULT_EXPORT_OPTIONS, normalizeExportOptions, loadExportOptions } from './export-options.js';

const choice = (key, title, value, options, disabled = false) => html`<div class="exd-field"><span>${title}</span>${segmented({ name: key, label: title, value, options: options.map(([value, label]) => ({ value, label })), disabled })}</div>`;
const check = (key, label, checked, disabled = false) => html`<label class="exd-check"><input id="${key}" type="checkbox" data-export-option="${key}"${checked ? ' checked' : ''}${disabled ? ' disabled' : ''}>${label}</label>`;

function previewHistory(o) {
  const scores = [9, 7, 3, 8, 5, 2, 6, 4, 8, 3, 7, 4, 6, 1, 5, 2].slice(0, o.historyLimit);
  return html`<div class="exd-history" aria-label="历史图排版示意"><span class="exd-history__cap">近 ${o.historyLimit} 次<small>新 → 旧</small></span><div class="exd-history__chart"><div class="exd-bars">${scores.map((score, i) => html`<div class="exd-bar" data-score="${score}" data-correct="${i % 3 !== 2 ? '1' : '0'}"><span>${o.historyScores ? score : ''}</span><i aria-hidden="true"></i><small>${i % 3 !== 2 ? '✓' : '×'}</small></div>`)}</div>${o.historyDates ? html`<div class="exd-dates"><span>11/13</span><span>10/02</span></div>` : ''}</div></div>`;
}

function preview(o) {
  const screen = o.variant === 'screen';
  return html`<aside class="exd-preview"><div class="exd-preview__caption"><strong>排版示意</strong><span>${screen ? '屏幕版' : `A4 · ${o.twoColumns ? '双栏' : '单栏'}`}</span></div>
    <div class="exd-paper" data-columns="${!screen && o.twoColumns ? '2' : '1'}">
      <div class="exd-paper__title">错题复习清单</div><div class="exd-paper__rule"></div>
      <div class="exd-paper__section">一、题目</div><div class="exd-paper__question"><b>第 1 题</b><span>数学 · 函数</span></div>
      ${o.historyPosition === 'question' ? previewHistory(o) : ''}
      <p class="exd-paper__text">已知函数 f(x)，求其单调区间。</p><div class="exd-paper__lines" aria-hidden="true"></div>
      <div class="exd-paper__section">${screen ? '显示答案后' : '二、反馈区'}</div><div class="exd-paper__question"><b>第 1 题</b><span>核对与回顾</span></div>
      ${o.historyPosition === 'feedback' ? previewHistory(o) : ''}
      ${o.answers || screen ? html`<p class="exd-paper__text">答案与解析……</p>` : ''}<p class="exd-paper__text exd-paper__muted">错因：注意区间端点。</p>
    </div><p class="exd-preview__note">示例内容；实际按题目与纸张自动分页。</p>
    ${o.historyPosition !== 'none' ? html`<p class="exd-legend"><span>✓ 答对</span><span>× 答错</span><span>柱高 = 分数 / 10</span></p>` : ''}
  </aside>`;
}

export function exportDialogView(o, extra = false, error = '', busy = false) {
  const screen = o.variant === 'screen', off = o.historyPosition === 'none';
  return html`<div class="exd-layout"><div class="exd-form"><fieldset aria-label="导出参数"${busy ? ' disabled' : ''}>
    <section class="exd-section"><h3>导出内容</h3>
      ${choice('variant', '文件版本', o.variant, [['a4', 'A4 打印版'], ['screen', '屏幕版']])}
      ${choice('columns', '纸面布局', o.twoColumns ? 'two' : 'one', [['two', '双栏'], ['one', '单栏']], screen)}
      <p class="exd-hint">${screen ? '屏幕版始终附带答案，纸面设置保留。' : '长公式、宽表格建议使用单栏。'}</p>
      <div class="exd-row">${check('answers', '附带答案', screen || o.answers, screen)}<label class="exd-gap" for="gap">题间留白 <input class="ui-input" id="gap" data-export-option="gap" type="number" min="0" max="20" step="1" value="${o.gap}"${screen ? ' disabled' : ''}> 行</label></div>
    </section>
    <section class="exd-section"><h3>练习历史<span>左新右旧</span></h3>
      ${choice('historyPosition', '显示位置', o.historyPosition, [['none', '关闭'], ['question', '题目区'], ['feedback', '反馈区']])}
      <label class="exd-limit" for="historyLimit"><span>最近记录</span><input class="ui-input" id="historyLimit" data-export-option="historyLimit" type="number" min="1" max="16" step="1" value="${o.historyLimit}"${off ? ' disabled' : ''}><span>次</span></label>
      <p class="exd-hint">${screen && o.historyPosition === 'feedback' ? '在「显示答案」后查看历史。' : '每题约占 12–15mm；没有记录时不占位。'}</p>
      <details class="ui-disclosure exd-more"${extra ? ' open' : ''}><summary>图表细节</summary><div class="exd-row">${check('historyScores', '显示分数', o.historyScores, off)}${check('historyDates', '显示首尾日期', o.historyDates, off)}</div><p class="exd-hint">颜色按实际对错区分；✓ / × 便于黑白打印辨认。</p></details>
    </section><div class="exd-bottom"><span>导出后自动记住本次设置</span><button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-export-reset>恢复默认</button></div>
    </fieldset>${error ? html`<p class="exd-error" role="alert">${error}</p>` : ''}</div>${preview(o)}</div>`;
}

export async function openExportDialog({ variant, count, run }) {
  let draft = normalizeExportOptions({ ...loadExportOptions(), ...(variant ? { variant } : {}) });
  let extra = false, busy = false, result = null, error = '';
  const answer = await dialog({
    id: 'schedule-export-dialog', title: '导出复习清单', size: 'lg',
    hint: `${count ? `已选 ${count} 道题 · ` : ''}设置版式与练习历史，生成可离线打开的 HTML 文件。`,
    body: exportDialogView(draft), okText: '导出文件', dismissible: () => !busy,
    onOpen(el) {
      const body = el.querySelector('.ui-dialog__body');
      const paint = () => {
        morph(body, exportDialogView(draft, extra, error, busy));
        el.querySelectorAll('[data-dialog-cancel]').forEach(button => { button.disabled = busy; });
      };
      el.__exportPaint = paint;
      body.addEventListener('toggle', event => { if (event.target.matches('.exd-more')) extra = event.target.open; }, true);
      body.addEventListener('change', event => {
        const input = event.target;
        const key = input.dataset.exportOption || input.name;
        if (key === 'columns') draft.twoColumns = input.value === 'two';
        else if (Object.hasOwn(draft, key)) draft[key] = input.type === 'checkbox' ? input.checked : input.value;
        draft = normalizeExportOptions(draft); error = ''; paint();
      });
      body.addEventListener('click', event => {
        if (event.target.closest('[data-export-reset]')) { draft = { ...DEFAULT_EXPORT_OPTIONS }; error = ''; paint(); }
      });
    },
    async onOk(values, el) {
      // Enter 确认不会先触发数字框 blur/change；以当前控件值捕获最后一次输入。
      draft = normalizeExportOptions({ ...draft, gap: values.gap, historyLimit: values.historyLimit });
      busy = true; error = ''; el.__exportPaint();
      try { result = await run({ ...draft }); }
      catch (e) { result = { ok: false, text: `导出失败：${e?.message || '未知错误'}` }; }
      busy = false;
      if (!result.ok) { error = result.text; el.__exportPaint(); return false; }
      return true;
    },
  });
  return answer.ok ? result : null;
}
