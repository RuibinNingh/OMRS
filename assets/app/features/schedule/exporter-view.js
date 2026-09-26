/**
 * 复习调度 ·「全题库导出」视图（原 omrs_dashboard.html 的 #export-panel 与 export.js 的渲染）。
 * 保留旧 id（#export-panel、#pick-*、#export-summary、#export-view-*、#export-include-answers、#export-question-gap、#export-status），
 * 表单值全部来自页面状态。画廊题面挂载点 data-morph="skip"，由 exporter-ctl 懒加载。
 */
import { html, each, cls } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { select } from '../../ui/select.js';
import { tag } from '../../ui/tag.js';
import { empty } from '../../ui/empty.js';
import { status } from '../../ui/status.js';
import { labelChip, labelChips } from '../../domain/labels/index.js';
import { EXPORT_SORTS, statusTag } from './exporter.js';

const opts = (values, all) => [{ value: '', label: all }, ...values.map(v => ({ value: v, label: v }))];
const pct = v => `${Math.round((Number(v) || 0) * 100)}%`;
const sel = (label, key, control) => html`<label class="schd-field" data-change="schedule.xfield" data-arg="${key}"><span>${label}</span>${control}</label>`;
const num = (label, key, id, value, min, max) => html`<label class="schd-field"><span>${label}</span><input id="${id}" class="schd-input" type="number" min="${min}" max="${max}" value="${value}" data-input="schedule.xfield" data-arg="${key}"></label>`;
const seg = (id, on, action, arg, label) => html`<button type="button" id="${id}" class="${cls('schd-seg', on && 'is-on')}" aria-pressed="${on ? 'true' : 'false'}" data-action="${action}" data-arg="${arg}">${label}</button>`;
const ktags = item => (item.knowledge_tags || []).slice(0, 4).map(t => tag({ label: t, tone: 'accent' }));

function filters(x, env) {
  const f = x.filters;
  const { subjects, categories, ktags: ks } = env.facets;
  return html`<div class="schd-setup" data-key="xsetup"><div class="schd-filters schd-filters--more">
    <label class="schd-field schd-field--grow"><span>搜索</span><input id="pick-search" class="schd-input" type="search" placeholder="UID、科目、分类、状态、知识点或标记" value="${f.text}" data-input="schedule.xfield" data-arg="text"></label>
    ${sel('科目', 'subject', select({ id: 'pick-subject', options: opts(subjects, '全部科目'), value: f.subject }))}
    ${sel('分类', 'category', select({ id: 'pick-category', options: opts(categories, '全部分类'), value: f.category }))}
    ${sel('状态', 'tag', select({ id: 'pick-tag', options: opts(['待攻克', '已击杀'], '全部状态'), value: f.tag }))}
    ${sel('知识点', 'ktag', select({ id: 'pick-ktag', options: opts(ks, '全部知识点'), value: f.ktag }))}
    ${num('难度 ≥', 'diffMin', 'pick-diff-min', f.diffMin, 1, 10)}${num('难度 ≤', 'diffMax', 'pick-diff-max', f.diffMax, 1, 10)}
    ${num('熟练度 ≥ %', 'masteryMin', 'pick-mastery-min', f.masteryMin, 0, 100)}${num('熟练度 ≤ %', 'masteryMax', 'pick-mastery-max', f.masteryMax, 0, 100)}
    ${sel('排序', 'sort', select({ id: 'pick-sort', options: EXPORT_SORTS.map(([value, label]) => ({ value, label })), value: f.sort }))}
    ${sel('标记匹配', 'labelMode', select({ id: 'pick-label-mode', options: [{ value: 'any', label: '标记任一' }, { value: 'all', label: '标记全部' }], value: f.labelMode }))}
    <div class="schd-labels" aria-label="导出标记筛选"><span class="schd-field__cap">标记</span>${env.labels.length ? each(env.labels, l => l.name, l => html`<button type="button" class="schd-lblf" aria-pressed="${f.labels.includes(l.name) ? 'true' : 'false'}" data-action="schedule.xlabel" data-arg="${l.name}">${labelChip(l.name)}</button>`) : html`<span class="schd-meta">还没有标记</span>`}</div>
  </div></div>`;
}

function options(x) {
  const st = x.status;
  return html`<div class="schd-xopts" data-key="xopts">
  <span class="schd-segs" role="group" aria-label="导出版本">${seg('export-variant-a4', x.variant === 'a4', 'schedule.xvariant', 'a4', 'A4 打印版')}${seg('export-variant-screen', x.variant === 'screen', 'schedule.xvariant', 'screen', '屏幕版')}</span>
  <label class="schd-check"><input type="checkbox" id="export-include-answers" data-change="schedule.xanswers"${x.variant === 'screen' || x.answers ? ' checked' : ''}${x.variant === 'screen' ? ' disabled' : ''}> 附带答案</label>
  <label class="schd-gap" title="仅影响 A4 打印版；每行约为正文一行的高度">题间留白 <input id="export-question-gap" class="schd-num" type="number" min="0" max="20" step="1" value="${x.gap}" data-input="schedule.xgap"${x.variant === 'screen' ? ' disabled' : ''}> 行</label>
  ${button({ label: `导出选中（${x.selection.length}）`, variant: 'primary', icon: 'download', action: 'schedule.xexport', loading: x.busy })}
  <span id="export-status" role="status">${st ? status({ tone: st.ok ? 'success' : 'danger', text: st.text }) : ''}</span>
</div>`;
}

function selection(x, env) {
  const rows = env.selected;
  return html`<section class="schd-xsel" data-key="xsel" aria-label="已选导出">
  <p class="schd-xsel__head"><strong>已选导出：${x.selection.length} 题</strong>${x.variant === 'screen' ? html`<span class="schd-meta">屏幕版始终附带答案</span>` : ''}</p>
  ${rows.length ? html`<ol class="schd-xlist">${each(rows, it => it.uid, (it, i) => html`<li class="schd-xrow">
    <div class="schd-xrow__main"><strong>${i + 1}. ${it.uid}</strong><span class="schd-meta">${it.subject || ''} · ${it.category || ''} · 难度 ${it.difficulty} · 熟练度 ${pct(it.mastery)}</span><span class="schd-xrow__tags">${labelChips(it.labels || [])}${ktags(it)}</span></div>
    <span class="schd-acts">${button({ label: '预览', size: 'sm', action: 'schedule.xpreview', arg: `export-selection|${it.uid}` })}${button({ label: '移除', size: 'sm', variant: 'ghost', action: 'schedule.xtoggle', arg: it.uid })}</span>
  </li>`)}</ol>` : html`<p class="schd-meta">还没有加入导出的题目。在下面勾选，或用「选择当前筛选」。</p>`}
</section>`;
}

function picker(x, env) {
  if (!env.filtered.length) return html`<div class="schd-xpick" data-key="xpick">${empty({ icon: 'filter', title: '没有符合当前筛选条件的题目', hint: '放宽筛选条件再试。', compact: true })}</div>`;
  const chosen = new Set(x.selection);
  const toggle = it => button({ label: chosen.has(it.uid) ? '移除' : '加入', size: 'sm', variant: chosen.has(it.uid) ? 'ghost' : 'default', action: 'schedule.xtoggle', arg: it.uid });
  const head = it => { const st = statusTag(it); return html`${st.label ? tag({ label: st.label, tone: st.tone }) : ''}${labelChips(it.labels || [])}${ktags(it)}`; };
  if (x.view === 'gallery') {
    return html`<div class="schd-xpick schd-xgrid" data-key="xpick">${each(env.filtered, it => it.uid, it => html`<article class="${cls('schd-xcard', chosen.has(it.uid) && 'is-selected')}">
      <div class="schd-xcard__head"><div><strong>${it.uid}</strong><p class="schd-meta">${it.subject || ''} · ${it.category || ''} · 难度 ${it.difficulty} · 熟练度 ${pct(it.mastery)}</p></div>${toggle(it)}</div>
      <p class="schd-xrow__tags">${head(it)}</p>
      <div class="schd-xcard__preview" data-xpreview-uid="${it.uid}" data-key="xp-${it.uid}" data-morph="skip"></div>
      <div class="schd-xcard__foot">${button({ label: '完整查看', size: 'sm', variant: 'ghost', action: 'schedule.xpreview', arg: `export|${it.uid}` })}</div>
    </article>`)}</div>`;
  }
  return html`<ol class="schd-xpick schd-xlist" data-key="xpick">${each(env.filtered, it => it.uid, it => html`<li class="${cls('schd-xrow', chosen.has(it.uid) && 'is-selected')}">
    <div class="schd-xrow__main"><strong>${it.uid}</strong><span class="schd-meta">${it.subject || ''} · ${it.category || ''} · 难度 ${it.difficulty} · 熟练度 ${pct(it.mastery)} · 上次复习 ${it.last_review || '—'}</span><span class="schd-xrow__tags">${head(it)}</span></div>
    <span class="schd-acts">${button({ label: '预览', size: 'sm', action: 'schedule.xpreview', arg: `export|${it.uid}` })}${toggle(it)}</span>
  </li>`)}</ol>`;
}

export function exporterView(x, env) {
  return html`<section class="schd-export" id="export-panel" aria-labelledby="schd-export-title" data-key="export">
  <div class="schd-heading"><div><h2 class="schd-heading__title" id="schd-export-title">导出 HTML：全题库筛选</h2><p class="schd-meta">勾选题目后导出为自包含 HTML（图片已内嵌）。A4 打印版用浏览器打印或另存 PDF，可选是否附带答案；屏幕版是手机、平板上的复习 App（一题一屏、看答案、判对错并打分、进度自动保存），始终附带答案。</p></div>${button({ label: '返回复习调度', icon: 'arrow-left', size: 'sm', action: 'schedule.view', arg: 'back' })}</div>
  ${filters(x, env)}
  <div class="schd-listbar"><span id="export-summary" class="schd-meta">${env.summary}</span>
    <div class="schd-listbar__acts"><span class="schd-segs" role="group" aria-label="导出选题视图">${seg('export-view-flat', x.view === 'flat', 'schedule.xview', 'flat', '平铺式')}${seg('export-view-gallery', x.view === 'gallery', 'schedule.xview', 'gallery', '画廊式')}</span>${button({ label: '选择当前筛选', size: 'sm', action: 'schedule.xaddFiltered' })}${button({ label: '移除当前筛选', size: 'sm', action: 'schedule.xremoveFiltered' })}${button({ label: '清空已选', size: 'sm', variant: 'danger', action: 'schedule.xclear', disabled: !x.selection.length })}</div></div>
  ${options(x)}
  ${selection(x, env)}
  ${picker(x, env)}
</section>`;
}
