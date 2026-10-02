/**
 * 复习调度：视图模板（只产出 html``，由 index.js 用 morph 写入 #sch-app）。
 * 三个工作区都在这里渲染：安排复习（arrange-view.js）、已有计划（本文件）、全题库导出（exporter-view.js）。保留旧 id（#sch-tab-*、#sch-plans、#sch-plan-filter、#sch-plan-detail、
 * #sch-session-status、#sch-include-answers、#sch-question-gap、#sch-status），冒烟测试按 id 找它们。
 */
import { html, each, cls } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { tag } from '../../ui/tag.js';
import { progress } from '../../ui/progress.js';
import { empty } from '../../ui/empty.js';
import { status } from '../../ui/status.js';
import { skeleton } from '../../ui/skeleton.js';
import { arrangeView } from './arrange-view.js';
import { exporterView } from './exporter-view.js';

function tabs(env) {
  const tab = (id, label, extra) => html`<button type="button" class="schd-tab" id="sch-tab-${id}" role="tab" aria-selected="${env.view === id ? 'true' : 'false'}" aria-controls="${id === 'arrange' ? 'recommend-panel-v2' : 'sch-plans'}" tabindex="${env.view === id ? '0' : '-1'}" data-action="schedule.view" data-arg="${id}">${label}${extra || ''}</button>`;
  return html`<div class="schd-top" data-key="top">
  <div class="schd-tabs" role="tablist" aria-label="复习调度工作区">${tab('arrange', '安排复习')}${tab('plans', '已有计划', html`<span class="schd-count" id="sch-plan-count">待完成 ${env.active}</span>`)}</div>
  ${button({ label: '全题库导出', iconRight: 'external', size: 'sm', variant: 'ghost', action: 'schedule.view', arg: 'export', title: '按条件从整个题库挑题导出' })}
</div>`;
}

function planList(env) {
  if (!env.plans.length) {
    const title = env.error ? '暂时无法获取计划' : env.loading ? '正在读取计划…' : '没有符合条件的计划';
    return html`<div class="schd-list">${empty({ icon: 'calendar', title, hint: env.error ? '检查服务后点上面的「重试」。' : '先在「安排复习」里选题生成计划。', compact: true, action: { label: '安排新复习', action: 'schedule.view', arg: 'arrange', variant: 'default' } })}</div>`;
  }
  return html`<ul class="schd-list" id="sch-plan-list" aria-label="计划列表">${each(env.plans, p => p.id, p => html`<li><button type="button" class="${cls('schd-plan', p.id === env.selected && 'is-active')}" aria-pressed="${p.id === env.selected ? 'true' : 'false'}" data-action="schedule.open" data-arg="${p.id}">
    <span class="schd-plan__head"><strong>${p.when}</strong>${tag({ label: p.status, tone: p.done ? 'success' : 'warning' })}</span>
    <span class="schd-plan__title">${p.title}</span>
    ${progress({ value: p.recorded, max: Math.max(1, p.total), label: '计划完成进度', size: 'sm', tone: p.done ? 'success' : 'accent' })}
    <span class="schd-plan__meta">已录入 ${p.recorded} / 共 ${p.total} 题</span><span class="schd-plan__id">${p.id}</span>
  </button></li>`)}</ul>`;
}

function detail(env) {
  const s = env.s;
  const back = html`<div class="schd-back">${button({ label: '返回计划列表', icon: 'arrow-left', size: 'sm', variant: 'ghost', action: 'schedule.back' })}</div>`;
  if (!s.selected) return html`<div class="schd-detail" id="sch-plan-detail">${s.deleted ? empty({ icon: 'check', title: '调度已删除', hint: '可在历史记录中恢复。请选择其他计划，或安排新复习。', compact: true }) : empty({ icon: 'list', title: '选择一个计划', hint: '查看题目和进度，导出练习，或接着录入结果。', compact: true })}</div>`;
  if (s.detailPhase === 'error') return html`<div class="schd-detail" id="sch-plan-detail">${back}<div class="schd-state">${status({ tone: 'danger', text: `无法读取计划：${s.detailError}` })}${button({ label: '重试', action: 'schedule.open', arg: s.selected })}</div></div>`;
  if (!env.detail) return html`<div class="schd-detail" id="sch-plan-detail">${back}${skeleton({ lines: 5 })}</div>`;
  const d = env.detail;
  return html`<div class="schd-detail" id="sch-plan-detail">${back}
  <div class="schd-detail__head"><div><h3 class="schd-detail__title">${d.title}</h3><p class="schd-meta" data-sid="${d.id}">${d.when} · ${d.id}</p></div>${tag({ label: d.status, tone: d.done ? 'success' : 'warning' })}</div>
  <p class="schd-detail__sum"><strong>已录入 ${d.recorded} / 共 ${d.total} 题</strong><span class="schd-meta">${d.hint}</span></p>
  <div class="schd-acts">${button({ label: '录入结果', variant: 'primary', action: 'schedule.feedback', disabled: !d.canFeedback })}${button({ label: '导出打印版', icon: 'print', action: 'schedule.export', arg: 'a4', loading: s.exporting === 'a4', disabled: !d.canExport })}${button({ label: '导出屏幕版', icon: 'download', action: 'schedule.export', arg: 'screen', loading: s.exporting === 'screen', disabled: !d.canExport })}${button({ label: '删除调度', variant: 'danger', icon: 'trash', action: 'schedule.remove', loading: s.deleting.has(d.id) })}</div>
  <details class="schd-options"${s.options ? ' open' : ''}><summary data-action="schedule.options">打印选项</summary><div class="schd-options__row">
    <label class="schd-check"><input type="checkbox" id="sch-include-answers" data-change="schedule.answers"${s.answers ? ' checked' : ''}> 附带答案</label>
    <label class="schd-gap">题间留白 <input id="sch-question-gap" class="schd-num" type="number" min="0" max="20" value="${s.gap}" data-input="schedule.gap"> 行</label>
  </div></details>
  <div id="sch-status" role="status">${s.exportStatus ? status({ tone: s.exportStatus.ok ? 'success' : 'danger', text: s.exportStatus.text }) : ''}</div>
  <ol class="schd-questions">${each(d.questions, q => `${q.n}:${q.uid}`, q => html`<li class="schd-q">
    <span class="schd-q__n">${q.n}</span><div class="schd-q__main"><strong>${q.uid}</strong><span class="schd-meta">${q.meta}</span></div>
    ${tag({ label: q.recorded ? '已录入' : '待录入', tone: q.recorded ? 'success' : 'neutral' })}${q.availability === 'unresolved' ? button({ label: '绑定题目', size: 'sm', action: 'schedule.bind', arg: q.entry_id }) : button({ label: '预览', size: 'sm', action: 'schedule.preview', arg: q.preview_key, disabled: q.missing || !q.preview_key })}
  </li>`)}</ol>
</div>`;
}

function plans(env) {
  const s = env.s;
  const note = env.error
    ? html`${status({ tone: 'danger', text: `计划加载失败：${env.error}` })}${button({ label: '重试', size: 'sm', action: 'schedule.refresh' })}`
    : env.loading ? html`<span class="schd-meta">正在更新计划…</span>` : '';
  return html`<section class="schd-plans" id="sch-plans" role="tabpanel" aria-labelledby="sch-tab-plans" data-key="plans">
  <div class="schd-heading"><div><h2 class="schd-heading__title">每一次复习，都有去处</h2><p class="schd-meta">查看题目、导出练习、录入结果，接着上次的进度继续。</p></div>${button({ label: '刷新计划', icon: 'refresh', size: 'sm', action: 'schedule.refresh' })}</div>
  <div class="schd-filters">
    <label class="schd-field"><span>计划状态</span><select id="sch-plan-filter" class="schd-input" data-change="schedule.filter">${[['active', '待完成'], ['completed', '已完成'], ['all', '全部']].map(([v, l]) => html`<option value="${v}"${s.filter === v ? ' selected' : ''}>${l}</option>`)}</select></label>
    <label class="schd-field schd-field--grow"><span>查找计划</span><input id="sch-plan-search" class="schd-input" type="search" placeholder="搜索计划编号" value="${s.search}" data-input="schedule.search"></label>
  </div>
  <div id="sch-session-status" class="schd-note" role="status">${note}</div>
  <div class="schd-work" data-detail="${s.showDetail ? '1' : '0'}">${planList(env)}${detail(env)}</div>
</section>`;
}

/** env = { s, view, active, plans, selected, detail, loading, error } */
export function view(env) {
  return html`<div class="schd" data-key="schd">${tabs(env)}${env.view === 'plans' ? plans(env) : ''}${env.view === 'arrange' ? arrangeView(env.a, env.arrange) : ''}${env.view === 'export' ? exporterView(env.x, env.exporter) : ''}</div>`;
}
