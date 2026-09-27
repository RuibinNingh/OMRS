/** 快速录入表单：图片与结构化题卡并列，所有输入保持旧接口字段。 */
import { html, each } from '../../core/html.js';
import { filedrop } from '../../ui/filedrop.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';
import { labelChips } from '../../domain/labels/index.js';

const IMAGE_FIELDS = [
  { kind: 'q', title: '题目截图', hint: '拖入、点击，或 Ctrl / ⌘ + V 粘到此', ai: [
    { action: 'classify', id: 'cr-classify-btn', label: '识别题目信息' },
    { action: 'questionText', id: 'cr-question-text-btn', label: '提取题目文本' },
  ] },
  { kind: 'a', title: '答案截图', hint: '可选；支持拖入、点击或粘贴', ai: [
    { action: 'answerText', id: 'cr-extract-btn', label: '提取答案文本' },
  ] },
];

export function imageThumbs(images, kind) {
  return each(images, image => image.id, (image, index) => html`<div class="crw-thumb" data-key="${image.id}">
    <img src="${image.dataUrl}" alt="${kind === 'q' ? '题目' : '答案'}图片 ${index + 1}">
    <button type="button" class="crw-thumb__remove" data-action="create.removeImage" data-arg="${kind}:${image.id}" aria-label="移除第 ${index + 1} 张${kind === 'q' ? '题目' : '答案'}图片">${icon('x')}</button>
    <span class="crw-thumb__number">${index + 1}</span>
  </div>`);
}

function imageField(field, state) {
  const kind = field.kind;
  return html`<section class="crw-shot${state.target === kind ? ' is-target' : ''}" id="cr-${kind}-paste" data-cr-paste="${kind}">
    <h3>${field.title}${kind === 'a' ? html`<small>可选</small>` : ''}</h3>
    ${filedrop({ id: `cr-${kind}-file`, title: field.hint, accept: 'image/*', multiple: true })}
    <div class="crw-thumbs" id="cr-${kind}-images">${imageThumbs(state.images[kind], kind)}</div>
    <div class="crw-shot__actions">
      ${button({ label: `从剪贴板读取到「${kind === 'q' ? '题目' : '答案'}」`, icon: 'copy', action: 'create.readImage', arg: kind })}
      ${field.ai.map(action => html`<button type="button" class="ui-btn" id="${action.id}" data-action="create.${action.action}"${state.images[kind].length ? '' : html` disabled`}>${icon('sparkle')}<span>${action.label}</span></button>`)}
    </div>
    <span class="crw-shot__status" id="${kind === 'q' ? 'cr-classify-status' : 'cr-extract-status'}" role="status" aria-live="polite"></span>
  </section>`;
}

export function resultView(result) {
  if (!result) return html``;
  if (result.error) return html`<div class="crw-result is-error" role="alert">${icon('alert-circle')}<span>${result.error}</span></div>`;
  return html`<div class="crw-result is-success" role="status">
    ${icon('check-circle')}<div><strong>${result.uid}</strong> 已创建${result.imageCount ? `，已保存 ${result.imageCount} 张图片` : ''}<br>${result.filePath}
      <div class="crw-result__action">${button({ label: '加入展示板', icon: 'plus', action: 'create.boardAdd' })}<span>加入最近用过的板；没有板会先新建</span></div>
    </div>
  </div>`;
}

export function quickView(state, { subjects = [], categories = [], tags = [] } = {}) {
  const f = state.form;
  return html`<div class="crw-quick">
    <div class="crw-steps" aria-label="快速录入流程"><span>1 截图</span>${icon('arrow-right')}<span>2 识别</span>${icon('arrow-right')}<strong>3 核对</strong>${icon('arrow-right')}<span>4 保存</span></div>
    <div class="crw-columns">
      <section class="crw-pane" aria-label="截图工作区"><h2>截图工作区</h2>
        ${IMAGE_FIELDS.map(field => imageField(field, state))}
        <p class="crw-help">点击图片区会切换粘贴目标；题目图可提取题面与分类，答案图可提取解析。识别结果仍可手动核对。</p>
      </section>
      <section class="crw-pane" aria-label="题卡内容"><h2>题卡内容</h2>
        <div class="crw-fields-pair">
          <label>科目 *<input id="cr-subject" data-cr-field="subject" list="crw-subj-list" value="${f.subject}" placeholder="数学、物理、化学…"><datalist id="crw-subj-list">${subjects.map(value => html`<option value="${value}"></option>`)}</datalist></label>
          <label>分类（知识点）*<input id="cr-category" data-cr-field="category" list="crw-cat-list" value="${f.category}" placeholder="函数、动能定理…"><datalist id="crw-cat-list">${categories.map(value => html`<option value="${value}"></option>`)}</datalist></label>
        </div>
        <div class="crw-fields-pair">
          <label>难度（1–10）<span class="crw-range"><input type="range" id="cr-diff" data-cr-field="difficulty" min="1" max="10" value="${f.difficulty}"><output id="cr-diff-val">${f.difficulty}</output></span></label>
          <label>相关知识点<input id="cr-related" data-cr-field="related" list="crw-ktag-list" value="${f.related}" placeholder="逗号分隔"><datalist id="crw-ktag-list">${tags.map(value => html`<option value="${value}"></option>`)}</datalist></label>
        </div>
        <label>题目正文<textarea id="cr-question" data-cr-field="question" rows="3" placeholder="支持 LaTeX，如 $x^2+1$">${f.question}</textarea></label>
        <label>答案 / 解析<textarea id="cr-answer" data-cr-field="answer" rows="3" placeholder="可手动输入或从答案图提取">${f.answer}</textarea></label>
        <label class="crw-cause">错因 · 这道题为什么错？<textarea id="cr-cause" data-cr-field="cause" rows="2" placeholder="复习时先看这里">${f.cause}</textarea></label>
        <div class="crw-labels"><span>标记 · 可选</span><div id="crw-labels">${labelChips(state.labels)}${button({ label: '添加标记', icon: 'plus', action: 'create.openLabels' })}</div></div>
        <label>笔记本页码 · 可选<input id="cr-note" data-cr-field="note" value="${f.note}" placeholder="p.23"></label>
      </section>
    </div>
    <div class="crw-actionbar"><p>核对无误后保存：题目写入对应科目和分类，图片自动嵌入，随后可在「题目库」查看。</p>
      <div>${button({ label: '重置', action: 'create.reset' })}${button({ label: '创建题目', variant: 'primary', action: 'create.submit' })}</div>
    </div>
    <div id="cr-result">${resultView(state.result)}</div>
    <details class="crw-details"><summary>文件结构与说明</summary><p>系统自动编号，题目文件位于对应的科目和分类文件夹，图片存入附件文件夹。AI 识别需先在「设置 → AI 识别」中配置。</p></details>
  </div>`;
}
