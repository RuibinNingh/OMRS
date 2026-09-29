import { hasExtraction } from './process-state.js';
/** 处理区动态队列与区域面板；分别挂到 #ib-pq-list、#ib-ps-body。事件一律走 data-action / data-change / data-input。 */
import { html, each, raw } from '../../core/html.js';
import { renderMd } from '../../domain/question/index.js';
import { groupCards, ROLES } from './process-state.js';
import { rawUrl, boxKey } from './crop.js';

const STATUS = { pending: '待处理', boxed: '已框选', ready: '待创建', done: '已录入' };
const ROLE_KEYS = new Set(Object.keys(ROLES));
const roleOf = role => ROLE_KEYS.has(role) ? role : 'ignore';
const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const boxText = region => `[${['x', 'y', 'w', 'h'].map(key => number(region[key]).toFixed(3)).join(', ')}]`;

export function queueView({ items = [], selected = new Set(), currentId = null } = {}) {
  const queue = items.filter(item => item.status !== 'discarded' && item.status !== 'done');
  if (!queue.length) return html`<div class="ib-empty">队列空了。<br>去「上传」再投几张。</div>`;
  return each(queue, item => item.id, item => html`<div class="ib-pq-row${item.id === currentId ? ' cur' : ''}" data-key="${item.id}" data-ib-cur="${item.id}" data-action="create.processOpen" data-arg="${item.id}">
    <label class="crp-check" title="选择 ${item.file}"><input type="checkbox" class="ib-chk" data-change="create.processSelect" data-arg="${item.id}" aria-label="选择 ${item.file}"${selected.has(item.id) ? html` checked` : ''}></label>
    <img src="${rawUrl(item.id)}" alt="" loading="lazy">
    <div class="ib-pq-detail"><div class="ib-pq-name">${item.file}</div>
      <div class="ib-pq-sub"><span class="ib-st ${item.status in STATUS ? item.status : 'pending'}">${STATUS[item.status] || item.status}</span>
        <span class="ib-rc" aria-label="${(item.regions || []).length} 个区域">${(item.regions || []).map(region => html`<i class="${roleOf(region.role)}"></i>`)}</span>
      </div>
    </div>
  </div>`);
}

function originView(region) {
  if (region.origin === 'ai') return html`<span class="ib-origin ai">AI 建议 ${number(region.conf).toFixed(2)} · 待确认</span>`;
  if (region.origin === 'ai_edited') return html`<span class="ib-origin edited">AI 建议 · 已人工调整</span>`;
  return html`<span class="ib-origin">手动</span>`;
}

function conversionView(region, itemId) {
  if (roleOf(region.role) === 'ignore') return html``;
  const id = region.id;
  const convert = region.convert || 'auto';
  const complete = hasExtraction(region);
  const running = region.text_status === 'running';
  return html`
  ${running ? html`<div class="ib-judge busy" role="status"><span class="ib-spin"></span>提取中…完成后请人工审核</div>` : ''}
  ${region.text_status === 'error' ? html`<div class="ib-judge no" role="status">提取失败，请重试；原图已保留</div>` : ''}
  ${region.text_status === 'stale' ? html`<div class="ib-judge no">框位或角色改过了，请重新提取后审核</div>` : ''}
  ${complete ? html`<div class="ib-judge ${region.judge.ok ? 'ok' : 'no'}"><span>${region.judge.ok ? '已提取文本，请核对' : (convert === 'image' ? '无法完整提取，已保留图片' : 'AI 未能完整提取，请核对补录文本')}${region.judge.reason ? `：${region.judge.reason}` : ''}</span></div>` : ''}
  ${!complete && !running && !['error', 'stale'].includes(region.text_status) ? html`<div class="hint ib-rg-crop-note">点击「一键提取」，完成后审核文本或图片</div>` : ''}
  <div class="ib-rg-conv">
    ${complete ? html`<button type="button" class="ui-btn ui-btn--sm ui-btn--ghost" data-action="create.processConvert" data-arg="${id}:${convert === 'image' ? 'text' : 'image'}">${convert === 'image' ? '改用文本' : '保存为图片'}</button>` : ''}
    ${region.judge || ['error', 'stale'].includes(region.text_status) ? html`<button type="button" class="ui-btn ui-btn--sm ui-btn--ghost" data-action="create.processExtract" data-arg="${id}"${running ? html` disabled` : ''}>重新提取</button>` : ''}
  </div>
  ${!running && convert !== 'image' && (region.text || region.judge) ? html`<div class="ib-rg-text"><textarea class="ui-textarea" rows="4" aria-label="区域文本" data-input="create.processText" data-arg="${id}">${region.text}</textarea><div class="ib-rg-prev q-md" id="ib-prev-${id}">${raw(renderMd(region.text))}</div></div>` : ''}
  ${convert === 'image' ? html`<div class="ib-rg-crop" data-key="crop-${boxKey(region)}" data-morph="skip"><canvas data-crop="${itemId}|${id}" data-crop-max="340" aria-label="裁图预览"></canvas></div><div class="hint ib-rg-crop-note">保存为裁剪图嵌入 <code># ${ROLES[roleOf(region.role)]}</code></div>` : ''}`;
}

function regionView(item, region, selectedRegion) {
  const role = roleOf(region.role);
  const selectedId = typeof selectedRegion === 'object' ? selectedRegion?.id : selectedRegion;
  return html`<div class="ib-rg${region.id === selectedId ? ' sel' : ''}" data-key="${region.id}" data-ib-rg="${region.id}" data-action="create.processRegion" data-arg="${region.id}">
    <div class="ib-rg-top"><span class="ib-role ${role}">${ROLES[role]}</span>${originView(region)}
      <button type="button" class="ui-btn ui-btn--sm del" title="删除这个框" aria-label="删除${ROLES[role]}区域" data-action="create.processDelete" data-arg="${region.id}">删除</button>
    </div>
    <div class="ib-rg-coord">归一化框 ${boxText(region)} · 裁出约 ${Math.round(number(region.w) * number(item.width))}×${Math.round(number(region.h) * number(item.height))}</div>
    ${conversionView(region, item.id)}
  </div>`;
}

export function sideView({ item = null, selectedRegion = null } = {}) {
  if (!item) return html`<div class="ib-empty">左边选一张图开始。</div>`;
  const groups = groupCards(item);
  if (!groups.length) return html`<div class="ib-empty">还没有框。<br>在图上拖出<b class="ib-role question">题目</b>和<b class="ib-role answer">答案</b>区域，或点「AI 框选此图」。<br><br><span class="hint">已裁好的题图直接点「整图即题目」。</span></div>`;
  return each(groups, ([card]) => card, ([card, regions]) => html`<div class="ib-cardgrp" data-key="${card}">
    <div class="ib-cardgrp-head">题卡 ${card}<span class="n">题目 ${regions.filter(region => region.role === 'question').length} · 答案 ${regions.filter(region => region.role === 'answer').length}
      ${groups.length > 1 ? html` · <button type="button" class="ui-btn ui-btn--sm ui-btn--ghost" data-action="create.processDrawCard" data-arg="${card}">在此题卡画框</button>` : ''}</span>
    </div>
    ${each(regions, region => region.id, region => regionView(item, region, selectedRegion))}
  </div>`);
}
