/** 处理区动态队列与区域面板；分别挂到 #ib-pq-list、#ib-ps-body。 */
import { html, each, raw } from '../../core/html.js';
import { renderMd } from '../../domain/question/index.js';
import { groupCards, ROLES } from './process-state.js';

const STATUS = { pending: '待处理', boxed: '已框选', ready: '待创建', done: '已录入' };
const ROLE_KEYS = new Set(Object.keys(ROLES));
const roleOf = role => ROLE_KEYS.has(role) ? role : 'ignore';
const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;
const boxText = region => `[${['x', 'y', 'w', 'h'].map(key => number(region[key]).toFixed(3)).join(', ')}]`;

export function queueView({ items = [], selected = new Set(), currentId = null } = {}) {
  const queue = items.filter(item => item.status !== 'discarded' && item.status !== 'done');
  if (!queue.length) return html`<div class="ib-empty">队列空了。<br>去「上传」再投几张。</div>`;
  return each(queue, item => item.id, item => html`<div class="ib-pq-row${item.id === currentId ? ' cur' : ''}" data-key="${item.id}" data-ib-cur="${item.id}">
    <label class="crp-check" title="选择 ${item.file}"><input type="checkbox" class="ib-chk" data-ib-sel="${item.id}" aria-label="选择 ${item.file}"${selected.has(item.id) ? html` checked` : ''}></label>
    <img src="/api/inbox/raw?id=${encodeURIComponent(item.id)}" alt="" loading="lazy">
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

function conversionView(region) {
  if (roleOf(region.role) === 'ignore') return html``;
  const id = region.id;
  const convert = region.convert || 'auto';
  return html`<div class="ib-rg-conv"><span class="lbl">这块怎么存</span>
    <div class="ib-seg" role="group" aria-label="区域保存方式">
      <button type="button" class="${convert === 'text' ? 'on' : ''}" data-ib-conv="${id}:text">转文本</button>
      <button type="button" class="${convert === 'image' ? 'on' : ''}" data-ib-conv="${id}:image">保留图片</button>
      <button type="button" class="${convert === 'auto' ? 'on' : ''}" data-ib-conv="${id}:auto">让 AI 判断</button>
    </div>
    ${convert === 'image' ? '' : html`<button type="button" class="ui-btn ui-btn--sm" data-ib-extract="${id}"${region.text_status === 'running' ? html` disabled` : ''}>${region.text_status === 'done' ? '重新提取' : '提取文本'}</button>`}
  </div>
  ${region.judge ? html`<div class="ib-judge ${region.judge.ok ? 'ok' : 'no'}"><span>AI 判断：${region.judge.reason || (region.judge.ok ? '可转文本' : '建议保留图片')}${region.judge_overridden ? '（已被人工否决）' : ''}</span></div>` : ''}
  ${region.text_status === 'running' ? html`<div class="ib-judge busy"><span class="ib-spin"></span>提取中…后台任务，可以切到其他图继续</div>` : ''}
  ${region.text_status === 'error' ? html`<div class="ib-judge no">模型没有返回文本，可重试或改为保留图片</div>` : ''}
  ${region.text_status === 'stale' ? html`<div class="ib-judge no">框位改过了，文本可能不对应，建议重新提取</div>` : ''}
  ${region.text && convert !== 'image' ? html`<div class="ib-rg-text"><textarea class="input" rows="4" data-ib-text="${id}">${region.text}</textarea><div class="ib-rg-prev q-md" id="ib-prev-${id}">${raw(renderMd(region.text))}</div></div>` : ''}
  ${convert === 'image' ? html`<div class="ib-rg-crop"><canvas data-ib-cropcv="${id}"></canvas></div><div class="hint ib-rg-crop-note">保存为裁剪图嵌入 <code># ${ROLES[roleOf(region.role)]}</code></div>` : ''}`;
}

function regionView(item, region, selectedRegion) {
  const role = roleOf(region.role);
  const selectedId = typeof selectedRegion === 'object' ? selectedRegion?.id : selectedRegion;
  return html`<div class="ib-rg${region.id === selectedId ? ' sel' : ''}" data-key="${region.id}" data-ib-rg="${region.id}">
    <div class="ib-rg-top"><span class="ib-role ${role}">${ROLES[role]}</span>${originView(region)}
      <button type="button" class="ui-btn ui-btn--sm del" title="删除这个框" aria-label="删除${ROLES[role]}区域" data-ib-del="${region.id}">删除</button>
    </div>
    <div class="ib-rg-coord">归一化框 ${boxText(region)} · 裁出约 ${Math.round(number(region.w) * number(item.width))}×${Math.round(number(region.h) * number(item.height))}</div>
    ${conversionView(region)}
  </div>`;
}

export function sideView({ item = null, selectedRegion = null } = {}) {
  if (!item) return html`<div class="ib-empty">左边选一张图开始。</div>`;
  const groups = groupCards(item);
  if (!groups.length) return html`<div class="ib-empty">还没有框。<br>在图上拖出<b class="ib-role question">题目</b>和<b class="ib-role answer">答案</b>区域，或点「AI 框选此图」。<br><br><span class="hint">已裁好的题图直接点「整图即题目」。</span></div>`;
  return each(groups, ([card]) => card, ([card, regions]) => html`<div class="ib-cardgrp" data-key="${card}">
    <div class="ib-cardgrp-head">题卡 ${card}<span class="n">题目 ${regions.filter(region => region.role === 'question').length} · 答案 ${regions.filter(region => region.role === 'answer').length}
      ${groups.length > 1 ? html` · <a href="#" data-ib-drawcard="${card}">在此题卡画框</a>` : ''}</span>
    </div>
    ${each(regions, region => region.id, region => regionView(item, region, selectedRegion))}
  </div>`);
}
