/** AI 训练工作区模板：数据集指标、构成条形、导出与清理、框选提供方与自动策略表单。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';
import { stat } from '../../ui/stat.js';
import { progress } from '../../ui/progress.js';
import { status } from '../../ui/status.js';
import { field, input } from '../../ui/field.js';
import { select } from '../../ui/select.js';
import { switchControl } from '../../ui/switch.js';
import { FORMATS, PROVIDERS, exportHref } from './train-state.js';

function bars(rows, unit) {
  if (!rows.length) return html`<p class="crt-muted">还没有数据：录入过的图片会按版式计入这里。</p>`;
  return each(rows, row => row.key, row => html`<div class="crt-bar" data-key="${row.key}">
    <span class="crt-bar__label">${row.label}</span>
    ${progress({ value: row.value, label: `${row.label} ${row.value}%`, tone: row.tone === 'success' ? 'success' : 'accent' })}
    <span class="crt-bar__value">${row.count}${unit}</span>
  </div>`);
}

function statsView(model, { loading, error }) {
  return html`<div class="crt-stats" aria-busy="${loading ? 'true' : 'false'}">
    ${each(model.cards, card => card.id, card => html`<div class="crt-stat" data-key="${card.id}" data-stat="${card.id}">${stat({ label: card.label, value: loading ? '—' : card.value, hint: card.hint })}</div>`)}
  </div>
  ${error ? html`<div class="crt-error">${status({ tone: 'danger', text: error })}${button({ label: '重试', size: 'sm', action: 'create.trainRefresh' })}</div>` : ''}`;
}

function datasetView(model, format) {
  return html`<div class="crt-cols">
    <section class="crt-panel" aria-labelledby="crt-layout-title">
      <h3 id="crt-layout-title">数据集构成</h3>
      <div class="crt-bars">${bars(model.layouts, ' 张')}</div>
      <h4>转换决策（按区域）</h4>
      <div class="crt-bars">${bars(model.convert, '')}</div>
    </section>
    <section class="crt-panel" aria-labelledby="crt-export-title">
      <h3 id="crt-export-title">导出与模型</h3>
      <p class="crt-muted">每次 AI 框选都记录「AI 原框 / 人工最终框 / 采纳方式」，人工否决 AI 转文本判断也会留痕；全部事件在 <code>错题/.omrs/inbox/annotations.jsonl</code>。框选模型按用途在「设置 → AI 自动识别」里分别配置（detect 需支持定位输出；extract 建议用 OCR 类模型）。</p>
      <div class="crt-row">
        <span class="crt-format" data-change="create.trainFormat">${select({ id: 'ib-tr-fmt', options: FORMATS, value: format, size: 'sm', label: '数据集格式' })}</span>
        <a class="ui-btn ui-btn--sm ui-btn--primary" id="ib-tr-export" href="${exportHref(format)}" download><span class="ui-btn__label">导出数据集（含原图）</span></a>
        ${button({ label: '刷新', icon: 'refresh', size: 'sm', action: 'create.trainRefresh' })}
      </div>
      <dl class="crt-facts">
        <dt>盲标评估集</dt><dd id="ib-tr-blind">${model.blind}</dd>
        <dt>聊天来源</dt><dd id="ib-tr-chat">${model.chat}</dd>
        <dt>存储</dt><dd id="ib-tr-storage">${model.storage}</dd>
      </dl>
      <div class="crt-row">
        ${button({ label: '清理超期丢弃图', size: 'sm', action: 'create.trainCleanup', title: '按下方「丢弃保留天数」删除超期的已丢弃原图；上传时也会自动执行' })}
        ${button({ label: '清空裁图缓存', size: 'sm', action: 'create.trainCleanup', arg: 'crops', title: 'crops/ 可随时清空，需要时由前端或 Pillow 重建' })}
      </div>
    </section>
  </div>`;
}

function policyView(form, { saving, message }) {
  if (!form) return html`<p class="crt-muted" role="status">正在读取策略配置…</p>`;
  const numberInput = (id, key, attrs) => html`<span class="crt-num" data-input="create.trainPolicy" data-arg="${key}">${input({ id, type: 'number', value: form[key], placeholder: attrs.placeholder })}</span>`;
  return html`<div class="crt-policy">
    ${field({ label: '框选提供方', id: 'ib-pl-provider', control: html`<span data-change="create.trainPolicy" data-arg="provider">${select({ id: 'ib-pl-provider', options: PROVIDERS, value: form.provider })}</span>` })}
    <div class="crt-local" id="ib-pl-local-row"${form.provider === 'local_http' ? '' : html` hidden`}>
      ${field({ label: '本地检测服务地址', id: 'ib-pl-local', control: html`<span data-input="create.trainPolicy" data-arg="local">${input({ id: 'ib-pl-local', value: form.local, placeholder: 'http://127.0.0.1:8600/detect' })}</span>` })}
    </div>
    ${field({ label: '每 N 张盲标（0 = 关闭）', id: 'ib-pl-blind', hint: '盲标的图不展示 AI 框，人工画完后成对留痕，作干净评估集，避免标注被模型带偏', control: numberInput('ib-pl-blind', 'blind', { placeholder: '0' }) })}
    ${field({ label: '自动提取的置信度阈值（0 = 关闭）', id: 'ib-pl-conf', hint: 'AI 框全部 ≥ 阈值时自动提取并判断是否留图，完成后仍需人工审核；服务端裁图需 Pillow', control: numberInput('ib-pl-conf', 'conf', { placeholder: '0' }) })}
    <div class="crt-switch" data-change="create.trainPolicy" data-arg="upload">
      <span class="ui-field__label">上传后自动处理</span>
      ${switchControl({ id: 'ib-pl-upload', label: '手机 / 电脑上传即自动框选（无人值守，配合上面的阈值）', checked: form.upload })}
    </div>
    ${field({ label: '丢弃的原图保留天数', id: 'ib-pl-days', control: numberInput('ib-pl-days', 'days', { placeholder: '7' }) })}
  </div>
  <div class="crt-row">
    ${button({ label: '保存策略', variant: 'primary', size: 'sm', action: 'create.trainSave', loading: saving })}
    <span id="ib-pl-status">${message ? status({ tone: message.ok ? 'success' : 'danger', text: message.text }) : ''}</span>
  </div>`;
}

/** 独立框选标注页入口：新标签页打开 /annotate；annotate 为 /api/annotate/stats 的结果，读取失败时只显示说明。 */
function annotateView(annotate) {
  const counts = annotate
    ? `已上传 ${annotate.images} 张，完成 ${annotate.done} 张 · 题目框 ${annotate.boxes?.question ?? 0}、答案框 ${annotate.boxes?.answer ?? 0}`
    : '上传截图后只框「题目」和「答案」，不进收件箱、不建题目';
  return html`<section class="crt-panel crt-annotate" aria-labelledby="crt-annotate-title">
    <div class="crt-annotate__text">
      <h3 id="crt-annotate-title">框选标注页</h3>
      <p class="crt-muted" id="ib-tr-annotate">${counts}</p>
    </div>
    <a class="ui-btn ui-btn--sm ui-btn--primary" id="ib-tr-annotate-open" href="/annotate" target="_blank" rel="noopener">${icon('external')}<span class="ui-btn__label">打开标注页</span></a>
  </section>`;
}

function trainpanelView(panel) {
  const current = panel?.latest?.status;
  const online = panel?.online_model;
  const run = panel?.runs?.find(item => item.online);
  const passed = run?.evaluation?.model?.answer?.pass_rate;
  const split = { val: '验证集', test: '历史回归集', independent: '独立验收集' }[run?.evaluation_split] || '已评估';
  const active = online ? `在线模型 ${online.name}${passed == null ? '' : ` · ${split}答案框 IoU ${Math.round(passed * 1000) / 10}%`}`
    : panel?.online_state === 'offline' ? '检测服务离线' : '尚无在线模型';
  const training = panel?.training_model || panel?.model;
  const summary = `${current?.state === 'running' ? `训练中 第 ${current.epoch} / ${current.epochs} 轮；` : ''}${active}；训练目录当前 ${training?.name || '无'}`;
  return html`<section class="crt-panel crt-annotate" aria-labelledby="crt-trainpanel-title">
    <div class="crt-annotate__text"><h3 id="crt-trainpanel-title">训练面板</h3><p class="crt-muted" id="ib-tr-panel-summary">${summary}</p></div>
    <a class="ui-btn ui-btn--sm ui-btn--primary" id="ib-tr-panel-open" href="/train" target="_blank" rel="noopener">${icon('external')}<span class="ui-btn__label">打开训练面板</span></a>
  </section>`;
}

export function trainView({ model, loading = false, error = '', format = 'omrs_jsonl', policy = null, policyError = '', saving = false, message = null, annotate = null, trainpanel = null } = {}) {
  return html`<div class="crt" id="ib-train">
    ${statsView(model, { loading, error })}
    ${annotateView(annotate)}
    ${trainpanelView(trainpanel)}
    ${datasetView(model, format)}
    <section class="crt-panel" aria-labelledby="crt-policy-title">
      <h3 id="crt-policy-title">框选提供方与自动策略</h3>
      <p class="crt-muted">「AI 框选」按钮使用这里选的提供方。本地检测服务协议：<code>POST {image, layout, width, height}</code> → <code>[{label, card, bbox_2d:[x1,y1,x2,y2], confidence}]</code>（坐标 0–1000 / 0–1 / 像素均可）。</p>
      ${policyError ? html`<div class="crt-error">${status({ tone: 'danger', text: policyError })}${button({ label: '重试', size: 'sm', action: 'create.trainRefresh' })}</div>` : policyView(policy, { saving, message })}
    </section>
  </div>`;
}
