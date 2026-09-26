/**
 * 数据复盘：视图模板（只产出 html``，由 index.js 用 morph 写入 #panel-data）。
 * 版式：说明与动作 → 八格概览 → 自动成两栏的图表卡（宽内容整行）。表格用 ui/table（手机降级为卡片），
 * 横条用原生 <progress>，SVG 图见 charts.js。卡片标题不再带 emoji（D7）；模板不写 style=（D11）。
 */
import { html, each, cls } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { progress } from '../../ui/progress.js';
import { table } from '../../ui/table.js';
import { empty } from '../../ui/empty.js';
import { status } from '../../ui/status.js';
import { skeleton } from '../../ui/skeleton.js';
import { labelChip } from '../../domain/labels/index.js';
import { pct, accTone } from './state.js';
import { trendSvg, radarSvg, scatterSvg } from './charts.js';

const tone = (value, text = pct(value)) => html`<span class="dat-tone" data-tone="${accTone(value)}">${text}</span>`;
const none = (title, hint) => empty({ icon: 'chart', title, hint, compact: true });

function card(key, title, body, { wide = false, sub } = {}) {
  return html`<section class="${cls('dat-card', wide && 'dat-card--wide')}" data-key="${key}" aria-labelledby="dat-${key}-t">
  <div class="dat-card__head"><h2 class="dat-card__title" id="dat-${key}-t">${title}</h2>${sub ? html`<p class="dat-card__sub">${sub}</p>` : ''}</div>${body}
</section>`;
}

function barList(rows, noun = '题') {
  if (!rows.length || rows.every(r => !r.value)) return none('还没有数据', `有${noun}之后这里按档位列出分布。`);
  return html`<ul class="dat-bars">${each(rows, r => r.key, r => html`<li class="dat-bar"><span class="dat-bar__label">${r.label}</span>${progress({ value: r.pct, max: 100, label: `${r.label} ${r.display}`, tone: r.tone, size: 'sm' })}<span class="dat-bar__val">${r.display}</span></li>`)}</ul>`;
}

function head(s) {
  const meta = s.phase === 'error' && s.analytics
    ? status({ tone: 'danger', text: `刷新失败：${s.error}` })
    : s.exportError ? status({ tone: 'danger', text: `导出失败：${s.exportError}` })
      : s.analytics ? html`数据基准时间 ${s.analytics.generated_at || '—'}` : '';
  return html`<section class="dat-head" data-key="head">
  <p class="dat-head__note">全面复盘数据。导出为 Markdown：上半部分是程序生成的复盘统计，下半部分是原始历史与 JSON，可以直接发给 AI 做个性化分析。</p>
  <div class="dat-head__acts">${button({ label: '刷新', icon: 'refresh', variant: 'ghost', action: 'data.refresh', loading: s.phase === 'loading' && !!s.analytics })}${button({ label: '导出复盘报告', icon: 'download', variant: 'primary', action: 'data.export', loading: s.exporting })}</div>
  <div class="dat-head__meta" id="data-status" role="status">${meta}</div>
</section>`;
}

function kpiGrid(rows) {
  return html`<dl class="dat-kpis" data-key="kpis">${each(rows, r => r.key, r => html`<div class="dat-kpi"><dt>${r.label}</dt><dd><span class="dat-kpi__value">${r.value}</span>${r.hint ? html`<span class="dat-kpi__hint">${r.hint}</span>` : ''}</dd></div>`)}</dl>`;
}

const uidCell = r => html`<span class="dat-uid">${r.uid}</span>`;
const actions = r => html`<span class="dat-acts">${button({ label: '查看', size: 'sm', action: 'data.view', arg: r.uid })}${button({ label: '加入展示板', size: 'sm', variant: 'ghost', action: 'data.board', arg: r.uid })}</span>`;

function charts(env) {
  const a = env.a;
  const b = env.bars;
  const subjects = env.subjects;
  return html`<div class="dat-grid" data-key="grid">
  ${card('trend', '每日练习趋势（近 30 天）', env.trend.points.length
    ? html`<dl class="dat-mini"><div><dt>近 30 天</dt><dd>${env.trend.total}</dd></div><div><dt>最近一天</dt><dd>${env.trend.last}</dd></div><div><dt>单日最高</dt><dd>${env.trend.max}</dd></div></dl>${trendSvg(env.trend)}`
    : none('还没有练习记录', '提交第一批反馈后，这里画出每天的练习次数。'))}
  ${card('labels', '标记分布', env.labels.length
    ? html`<ul class="dat-bars dat-bars--labels">${each(env.labels, r => r.name, r => html`<li class="dat-bar">${labelChip(r.name)}${progress({ value: r.pct, max: 100, label: `${r.name} ${r.count} 题`, size: 'sm' })}<span class="dat-bar__val">${r.count}</span></li>`)}</ul>`
    : none('还没有用户标记', '在题目上打标记后，这里按题数排出来。'))}
  ${card('subjects', '科目维度', html`${subjects.length >= 3 ? radarSvg(subjects) : html`<p class="dat-card__sub">科目少于 3 个，不画雷达图。</p>`}${table({ rowKey: 'subject', stack: true, empty: '暂无数据', rows: a.subjects || [], columns: [
    { key: 'subject', label: '科目', render: r => html`<b>${r.subject}</b>` }, { key: 'total', label: '题数', num: true }, { key: 'killed', label: '击杀', num: true },
    { key: 'attacking', label: '待攻克', num: true }, { key: 'leech', label: '顽固', num: true, render: r => (r.leech ? html`<span class="dat-tone" data-tone="danger">${r.leech}</span>` : '0') },
    { key: 'avg_mastery', label: '平均熟练', num: true, render: r => tone(r.avg_mastery) }, { key: 'avg_ef', label: 'EF', num: true },
    { key: 'accuracy', label: '正确率', num: true, render: r => tone(r.accuracy) }] })}`, { sub: '最薄弱在前' })}
  ${card('categories', '分类维度', table({ rowKey: 'key', stack: true, empty: '暂无数据', rows: (a.categories || []).slice(0, 15).map(c => ({ ...c, key: `${c.subject}/${c.category}` })), columns: [
    { key: 'category', label: '分类' }, { key: 'subject', label: '科目' }, { key: 'total', label: '题数', num: true },
    { key: 'avg_mastery', label: '平均熟练', num: true, render: r => tone(r.avg_mastery) }, { key: 'reviews', label: '复习', num: true },
    { key: 'accuracy', label: '正确率', num: true, render: r => tone(r.accuracy) }, { key: 'leech', label: '顽固', num: true, render: r => String(r.leech || 0) }] }), { sub: '最薄弱的 15 个' })}
  ${card('scatter', '难度与熟练度', env.scatter.length
    ? html`${scatterSvg(env.scatter)}<p class="dat-legend"><span data-tone="danger">低</span><span data-tone="warning">中</span><span data-tone="success">高</span><span>圆越大题目越多，颜色是该格的平均熟练度</span></p>`
    : none('还没有题目', '录入题目后，这里按难度和熟练度把题目聚成气泡。'))}
  ${card('mastery', '熟练度分布', barList(b.mastery))}
  ${card('decayed', '熟练度分布（衰减后）', barList(b.decayed))}
  ${card('ef', 'EF 分布', barList(b.ef), { sub: '越低越不稳定' })}
  ${card('difficulty', '难度分布', barList(b.difficulty))}
  ${card('repetition', '连续答对次数分布', barList(b.repetition))}
  ${card('interval', '复习间隔分布', barList(b.interval))}
  ${card('score', '各主观分正确率', barList(b.score, '反馈'))}
  ${card('weekly', '按周正确率', table({ rowKey: 'week', stack: true, empty: '暂无数据', rows: a.accuracy?.weekly || [], columns: [
    { key: 'week', label: '周' }, { key: 'reviews', label: '复习', num: true }, { key: 'correct', label: '答对', num: true },
    { key: 'accuracy', label: '正确率', num: true, render: r => tone(r.accuracy) }] }), { sub: '近 12 周' })}
  ${card('weekday', '按星期复习量', barList(b.weekday, '练习'))}
  ${card('hour', '按时段复习量', html`<div class="dat-heat" role="img" aria-label="按小时的复习次数"><ol class="dat-heat__grid">${each(env.hours, h => h.label, h => html`<li class="dat-heat__cell" data-level="${h.level}" title="${h.label}:00 — ${h.count} 次"></li>`)}</ol><div class="dat-heat__axis" aria-hidden="true"><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div></div>`, { sub: '每格一小时，颜色越深复习越多' })}
  ${card('forecast', '未来 7 天到期预测', barList(b.forecast))}
  ${card('label-acc', '按标记正确率与平均分', table({ rowKey: 'label', stack: true, empty: '还没有带标记的反馈', rows: a.accuracy?.by_label || [], columns: [
    { key: 'label', label: '标记', render: r => labelChip(r.label) }, { key: 'questions', label: '题数', num: true }, { key: 'reviews', label: '复习', num: true },
    { key: 'correct', label: '答对', num: true }, { key: 'accuracy', label: '正确率', num: true, render: r => tone(r.accuracy) },
    { key: 'avg_score', label: '平均分', num: true, render: r => (r.avg_score == null ? '—' : String(r.avg_score)) }] }), { wide: true })}
  ${card('alerts', '复习预警', html`<dl class="dat-alerts">${each(env.alerts, r => r.key, r => html`<div class="dat-alert" data-tone="${r.tone}"><dt>${r.label}</dt><dd>${r.value}</dd></div>`)}</dl>`, { wide: true })}
  ${card('leeches', '顽固题', table({ rowKey: 'uid', stack: true, empty: '没有顽固题：最近没有连续答错的题', rows: a.weak_spots?.leeches || [], columns: [
    { key: 'uid', label: 'UID', render: uidCell }, { key: 'subject', label: '科目' }, { key: 'category', label: '分类' },
    { key: 'wrong_streak', label: '连错', num: true, render: r => html`<span class="dat-tone" data-tone="danger">${r.wrong_streak}</span>` },
    { key: 'mastery', label: '熟练度', num: true, render: r => tone(r.mastery) }, { key: 'ef', label: 'EF', num: true }, { key: 'attempts', label: '复习', num: true },
    { key: 'act', label: '操作', render: actions }] }), { wide: true, sub: '最近连续答错' })}
  ${card('struggling', '屡练不熟', table({ rowKey: 'uid', stack: true, empty: '没有屡练不熟的题', rows: a.weak_spots?.struggling || [], columns: [
    { key: 'uid', label: 'UID', render: uidCell }, { key: 'subject', label: '科目' }, { key: 'category', label: '分类' },
    { key: 'mastery', label: '熟练度', num: true, render: r => tone(r.mastery) }, { key: 'attempts', label: '复习', num: true },
    { key: 'fail_count', label: '答错', num: true, render: r => (r.fail_count ? html`<span class="dat-tone" data-tone="danger">${r.fail_count}</span>` : '0') },
    { key: 'act', label: '操作', render: actions }] }), { wide: true, sub: '复习 ≥3 次且熟练度 <40%' })}
</div>`;
}

/** env = { s, a, kpis, bars, subjects, scatter, hours, alerts, trend, labels } */
export function view(env) {
  const s = env.s;
  let body;
  if (!s.analytics && s.phase === 'error') {
    body = html`<div class="dat-state" data-key="state">${status({ tone: 'danger', text: `数据复盘没有加载成功：${s.error}`, block: true })}${button({ label: '重试', variant: 'primary', icon: 'refresh', action: 'data.refresh' })}</div>`;
  } else if (!s.analytics) {
    body = html`<div class="dat-state" data-key="state">${s.phase === 'loading' ? skeleton({ lines: 6 }) : ''}</div>`;
  } else {
    body = html`${kpiGrid(env.kpis)}${charts(env)}`;
  }
  return html`<div class="dat" data-key="dat"${s.analytics ? html` data-dat-ready="1"` : ''}>${head(s)}${body}</div>`;
}
