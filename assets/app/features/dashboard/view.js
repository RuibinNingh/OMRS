/**
 * 仪表盘：视图模板（只产出 html``，由 index.js 用 morph 写入 #panel-dashboard）。
 * 次序只回答「今天做什么」：今天 → 行动推荐 → 概览 → 近 30 天 / 最薄弱的科目 → 最近动态。
 * 每块带 data-key；动作一律 data-action="dashboard.*"（重新扫描是全站共用的 app.scan）。
 * 字号只用六档：display（今天的数字）、xl（概览与指标数字）、lg（卡片标题）、md（正文）、sm（按钮、说明）、xs（元信息）。
 */
import { html, each, cls } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';
import { tag } from '../../ui/tag.js';
import { progress } from '../../ui/progress.js';
import { empty } from '../../ui/empty.js';
import { status } from '../../ui/status.js';
import { skeleton } from '../../ui/skeleton.js';
import { LEVELS } from './plan.js';
import { visiblePlan } from './state.js';

const arg = (i, j) => `${i}:${j}`;

function actionButtons(actions, prefix, size) {
  return each(actions, (a, j) => j, (a, j) => button({ label: a.label, variant: a.primary ? 'primary' : 'default', size, action: 'dashboard.run', arg: `${prefix}${arg('', j)}` }));
}

function today(t, err) {
  if (err) {
    return html`<section class="dsh-today dsh-today--error" data-key="today" aria-label="今天">
  <div class="dsh-today__main">${status({ tone: 'danger', text: `统计数据没有加载成功：${err}`, block: true })}</div>
  <div class="dsh-today__acts">${button({ label: '重新加载', variant: 'primary', icon: 'refresh', action: 'dashboard.retry' })}</div>
</section>`;
  }
  const side = t.empty
    ? html`<p class="dsh-today__note">${t.note}</p>`
    : html`${progress({ value: t.pct, max: 100, label: '今天已练', meta: `${t.done} / 建议 ${t.target} 题`, tone: t.done >= t.target && t.target ? 'success' : 'accent' })}<p class="dsh-today__note">${t.note}</p>`;
  return html`<section class="${cls('dsh-today', `is-${t.level}`)}" data-key="today" aria-label="今天">
  <div class="dsh-today__main">
    <p class="dsh-today__date">${t.stamp}</p>
    <p class="dsh-today__num"><span class="dsh-today__value">${t.waiting}</span><span class="dsh-today__unit">${t.empty ? '题库还是空的' : '道题待复习'}</span></p>
    ${t.splits.length ? html`<ul class="dsh-today__split" aria-label="待复习分项">${each(t.splits, s => s.label, s => html`<li>${tag({ label: s.label, tone: s.tone })}</li>`)}</ul>` : ''}
  </div>
  <div class="dsh-today__side">${side}</div>
  <div class="dsh-today__acts">${actionButtons(t.actions, 'today', 'md')}</div>
</section>`;
}

function planCard(plan, showAll) {
  const { rows, hidden, collapsible } = visiblePlan(plan, showAll);
  const more = hidden > 0
    ? button({ label: `还有 ${hidden} 条建议`, iconRight: 'chevron-down', size: 'sm', variant: 'ghost', action: 'dashboard.more', block: true })
    : collapsible ? button({ label: '收起', iconRight: 'chevron-up', size: 'sm', variant: 'ghost', action: 'dashboard.more', block: true }) : '';
  return html`<section class="dsh-card dsh-plan" data-key="plan" aria-labelledby="dsh-plan-title">
  <div class="dsh-card__head"><h2 class="dsh-card__title" id="dsh-plan-title">行动推荐</h2><p class="dsh-card__sub">按当前题库状态排的优先级，从上往下做。</p></div>
  <ol class="dsh-plan__list">${each(rows, row => row.key, (row, i) => html`<li class="dsh-act" data-key="${row.key}" data-level="${row.level}">
    <span class="dsh-act__icon" aria-hidden="true">${icon(row.icon)}</span>
    <div class="dsh-act__body">
      <p class="dsh-act__title"><span>${row.title}</span>${tag({ label: LEVELS[row.level].label, tone: LEVELS[row.level].tone })}</p>
      <p class="dsh-act__detail">${row.detail}</p>
    </div>
    <span class="dsh-act__metric">${row.metric}</span>
    <div class="dsh-act__acts">${actionButtons(row.actions, `${i}`, 'sm')}</div>
  </li>`)}</ol>
  ${more ? html`<div class="dsh-plan__more" data-key="more">${more}</div>` : ''}
</section>`;
}

function kpiStrip(rows) {
  return html`<section class="dsh-kpis" data-key="kpis" aria-label="题库概览">
  <dl class="dsh-kpis__list">${each(rows, r => r.key, r => html`<div class="dsh-kpi" data-key="${r.key}"><dt>${r.label}</dt><dd><span class="dsh-kpi__value">${r.value}</span>${r.hint ? html`<span class="dsh-kpi__hint">${r.hint}</span>` : ''}</dd></div>`)}</dl>
  <div class="dsh-kpis__act">${button({ label: '重新扫描', icon: 'refresh', variant: 'ghost', size: 'sm', action: 'app.scan', title: '把在 Obsidian 里新增或改动的题目文件收进题库' })}</div>
</section>`;
}

function heatCard(h) {
  const summary = `近 30 天共 ${h.total} 次复习，${h.active} 天有练习，单日最多 ${h.peak} 次`;
  return html`<section class="dsh-card" data-key="heat" aria-labelledby="dsh-heat-title">
  <div class="dsh-card__head"><h2 class="dsh-card__title" id="dsh-heat-title">近 30 天活动</h2></div>
  <dl class="dsh-heat__stats"><div><dt>次复习</dt><dd>${h.total}</dd></div><div><dt>天活跃</dt><dd>${h.active}</dd></div><div><dt>单日峰值</dt><dd>${h.peak}</dd></div></dl>
  <div class="dsh-heat" role="img" aria-label="${summary}">
    <ol class="dsh-heat__grid">${each(h.days, d => d.key, d => html`<li class="dsh-heat__cell" data-level="${d.level}" title="${d.key}：${d.count} 次"></li>`)}</ol>
    <div class="dsh-heat__axis" aria-hidden="true">${each(h.ticks, t => t, t => html`<span>${t}</span>`)}</div>
  </div>
  <div class="dsh-heat__legend" aria-hidden="true"><span>少</span>${[0, 1, 2, 3, 4].map(l => html`<i class="dsh-heat__cell" data-level="${l}"></i>`)}<span>多</span></div>
</section>`;
}

function weakCard(rows) {
  const body = rows.length
    ? html`<ul class="dsh-weak">${each(rows, r => r.key, r => html`<li><button type="button" class="dsh-weak__row" data-action="dashboard.weak" data-arg="${r.key}" title="在题库里筛出该科目">
      <span class="dsh-weak__name">${r.key}</span>${progress({ value: r.pct, max: 100, label: `${r.key} 衰减后熟练度`, tone: r.tone, size: 'sm' })}<span class="dsh-weak__pct">${r.pct}%</span><span class="dsh-weak__count">${r.count} 题</span>
    </button></li>`)}</ul><p class="dsh-card__foot">按衰减后熟练度排序，题量 ≥ 5 才纳入。点一行跳到题库对应筛选。</p>`
    : empty({ icon: 'chart', title: '还没有题量 ≥ 5 的科目', hint: '某个科目录满 5 道题后，这里按衰减后熟练度从低到高排出来。', compact: true });
  return html`<section class="dsh-card" data-key="weak" aria-labelledby="dsh-weak-title">
  <div class="dsh-card__head"><h2 class="dsh-card__title" id="dsh-weak-title">最薄弱的科目</h2></div>${body}
</section>`;
}

function recentCard(recent, rows) {
  let body;
  if (recent.phase === 'error' && !rows.length) body = html`<div class="dsh-recent__state">${status({ tone: 'danger', text: `最近动态没有加载成功：${recent.error}` })}${button({ label: '重试', size: 'sm', action: 'dashboard.recentRetry' })}</div>`;
  else if (recent.phase === 'loading' && !rows.length) body = skeleton({ lines: 4 });
  else if (!rows.length && recent.phase !== 'idle') body = empty({ icon: 'clock', title: '还没有动态', hint: '录题、提交反馈、建复习计划之后，这里列出最近四件事。', compact: true });
  else body = html`<ol class="dsh-recent">${each(rows, r => r.id, r => html`<li class="dsh-recent__row" data-key="${r.id}">
    <span class="dsh-recent__dot" data-fam="${r.family}" aria-hidden="true"></span>
    <div class="dsh-recent__mid"><p class="dsh-recent__title">${r.title}</p><p class="dsh-recent__meta">${r.meta}</p></div>
    <span class="dsh-recent__chip">${r.chip ? tag({ label: r.chip, tone: 'success' }) : ''}</span><time class="dsh-recent__time">${r.time}</time>
  </li>`)}</ol>`;
  return html`<section class="dsh-card" data-key="recent" aria-labelledby="dsh-recent-title">
  <div class="dsh-card__head dsh-card__head--row"><h2 class="dsh-card__title" id="dsh-recent-title">最近动态</h2>${button({ label: '完整时间线', iconRight: 'arrow-right', size: 'sm', action: 'dashboard.go', arg: 'history' })}</div>${body}
</section>`;
}

/** env = { ready, error, today, plan, showAll, kpis, heat, weak, recent, recentRows } */
export function view(env) {
  if (!env.ready) return html`<div class="dsh" data-key="dsh">${skeleton({ lines: 6 })}</div>`;
  return html`<div class="dsh" data-key="dsh" data-dash-ready="1">
  ${today(env.today, env.error)}
  ${planCard(env.plan, env.showAll)}
  ${kpiStrip(env.kpis)}
  <div class="dsh-cols" data-key="cols">${heatCard(env.heat)}${weakCard(env.weak)}</div>
  ${recentCard(env.recent, env.recentRows)}
</div>`;
}
