/** 题卡工作区模板：顶部批量条、每张就绪题卡一行（左预览、右表单）；图片区域的裁图 canvas 放在 data-morph="skip" 里。 */
import { html, each, raw } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { empty } from '../../ui/empty.js';
import { labelChips } from '../../domain/labels/index.js';
import { renderMd, hashText } from '../../domain/question/index.js';
import { boxKey } from './crop.js';
import { allText, regionKinds, tagText, targetPath } from './cards-state.js';

const datalist = (id, values) => html`<datalist id="${id}">${values.map(value => html`<option value="${value}"></option>`)}</datalist>`;

function block(item, region) {
  if (region.convert === 'text' && region.text) {
    return html`<div class="crc-text q-md" data-key="t-${region.id}" data-hash="${hashText(region.text)}">${raw(renderMd(region.text))}</div>`;
  }
  return html`<div class="crc-crop" data-key="c-${region.id}-${boxKey(region)}" data-morph="skip"><canvas data-crop="${item.id}|${region.id}" data-crop-max="520" aria-label="裁图预览"></canvas></div>`;
}

function preview(item, role, regions) {
  const title = role === 'question' ? '题目' : '答案';
  return html`<section class="crc-block" data-role="${role}">
    <h4><span class="crc-role" data-role="${role}">${title}</span>写入 <code># ${title}</code></h4>
    <div class="crc-block__body">${regions.map(region => block(item, region))}</div>
  </section>`;
}

function formView(entry) {
  const { key, form } = entry;
  const ai = form.classified ? html`<span class="crc-ai">AI 已填 · 可改</span>` : '';
  const input = (field, value, { list, placeholder } = {}) => html`<input class="crc-input" data-input="create.cardField" data-arg="${key}|${field}" value="${value ?? ''}"${list ? html` list="${list}" autocomplete="off"` : ''}${placeholder ? html` placeholder="${placeholder}"` : ''}>`;
  return html`<div class="crc-form">
    <div class="crc-pair">
      <label>科目 *${ai}${input('subject', form.subject, { list: 'crc-subj-list' })}</label>
      <label>分类 *${ai}${input('category', form.category, { list: 'crc-cat-list' })}</label>
    </div>
    <label>难度${ai}<span class="crc-range"><input type="range" min="1" max="10" data-input="create.cardField" data-arg="${key}|difficulty" value="${form.difficulty || 5}"><output>${form.difficulty || 5}</output></span></label>
    <label>相关知识点${ai}${input('tags', tagText(form.tags), { list: 'crc-ktag-list', placeholder: '逗号分隔，写入 YAML 为 [[双链]]' })}</label>
    <div class="crc-labels"><span>标记${ai}</span>
      <div class="crc-labels__chips" data-card-labels="${key}">${labelChips(form.labels || [], { lg: true })}${button({ label: '添加标记', icon: 'plus', size: 'sm', action: 'create.cardLabels', arg: key })}</div>
    </div>
    <label class="crc-cause">错因 · 这道题为什么错？<textarea class="crc-input" rows="2" data-input="create.cardField" data-arg="${key}|cause" placeholder="写入 # 备注 的「## 错因」，复习时先看这里">${form.cause || ''}</textarea></label>
    <label class="crc-page">笔记本页码${input('page', form.page, { placeholder: 'p.23' })}</label>
  </div>`;
}

function cardView(entry, index, { selected, busy, multi }) {
  const { key, item, card, regions, form } = entry;
  const questions = regions.filter(region => region.role === 'question');
  const answers = regions.filter(region => region.role === 'answer');
  const working = busy.has(key);
  return html`<article class="crc-card" id="ib-card-${item.id}-${card}" data-key="${key}" data-ib-card="${key}">
    <header class="crc-card__head">
      <label class="crc-check" title="选择题卡 ${index + 1}"><input type="checkbox" data-change="create.cardSelect" data-arg="${key}" aria-label="选择题卡 ${index + 1}"${selected.has(key) ? html` checked` : ''}></label>
      <strong>题卡 ${index + 1}</strong>
      <span class="crc-src">${item.file}${multi.has(item.id) ? ` · 题卡 ${card}` : ''}</span>
      <span class="crc-kinds">题目 ${regionKinds(questions) || '—'}</span>
      <span class="crc-kinds">${answers.length ? `答案 ${regionKinds(answers)}` : '无答案'}</span>
    </header>
    <div class="crc-card__body">
      <div class="crc-preview">
        ${preview(item, 'question', questions)}
        ${answers.length ? preview(item, 'answer', answers) : ''}
        <p class="crc-note">${allText(regions)
    ? `原图 ${item.width}×${item.height} 不随题保存（已全部转文本），只留在收件箱数据集里。`
    : html`保留图片的区域会裁出存入 <code>附件/</code>；原图只留在收件箱数据集里。`}</p>
      </div>
      ${formView(entry)}
    </div>
    <footer class="crc-card__foot">
      <span class="crc-path">${targetPath(form)}</span>
      <span class="crc-grow"></span>
      ${button({ label: form.classified ? '重新识别题目信息' : 'AI 识别题目信息', icon: 'sparkle', size: 'sm', action: 'create.cardClassify', arg: key })}
      ${button({ label: '退回处理', size: 'sm', action: 'create.cardBack', arg: item.id })}
      ${button({ label: '创建题目', variant: 'primary', size: 'sm', action: 'create.cardCommit', arg: key, loading: working })}
    </footer>
  </article>`;
}

export function cardsView({ cards = [], selected = new Set(), busy = new Set(), batch = false, loaded = true, suggest = {} } = {}) {
  const images = new Set(cards.map(entry => entry.item.id)).size;
  const multi = new Set(cards.filter(entry => cards.some(other => other !== entry && other.item.id === entry.item.id)).map(entry => entry.item.id));
  const all = cards.length > 0 && cards.every(entry => selected.has(entry.key));
  const count = [...selected].filter(key => cards.some(entry => entry.key === key)).length;
  return html`<div class="crc">
    <div class="crc-head">
      <label class="crc-all"><input type="checkbox" id="ib-cr-all" data-change="create.cardAll"${all ? html` checked` : ''}${cards.length ? '' : html` disabled`}> 全选</label>
      <span class="crc-count" id="ib-cr-count">${cards.length} 张题卡待创建 · 来自 ${images} 张图</span>
      <span class="crc-grow"></span>
      ${button({ label: `AI 识别题目信息（勾选${count ? ` ${count}` : ''}）`, icon: 'sparkle', size: 'sm', action: 'create.cardClassifySelected', disabled: !count })}
      ${button({ label: '创建勾选的题目', variant: 'primary', size: 'sm', action: 'create.cardCommitSelected', disabled: !count, loading: batch })}
    </div>
    <div class="crc-list" id="ib-cards">
      ${!loaded ? html`<p class="crc-loading" role="status">正在读取收件箱…</p>`
    : cards.length ? each(cards, entry => entry.key, (entry, index) => cardView(entry, index, { selected, busy, multi }))
      : empty({ icon: 'inbox', title: '还没有就绪的题卡', hint: '在「处理」里把框选好的图标记就绪，题卡会出现在这里。', action: { label: '去处理', action: 'create.stage', arg: 'process' }, bordered: true })}
    </div>
    ${datalist('crc-subj-list', suggest.subjects || [])}${datalist('crc-cat-list', suggest.categories || [])}${datalist('crc-ktag-list', suggest.tags || [])}
  </div>`;
}
