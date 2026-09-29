/** 小型 SVG 图表，所有颜色由页面设计 token 决定。 */
import { html } from '../../core/html.js';
import { point, ticks, pct } from './state.js';

export function lineChart(rows, series, label, fixedMax = null) {
  const maxX = Math.max(1, ...rows.map(row => row.epoch));
  const values = rows.flatMap(row => series.map(s => Number(row[s.key]) || 0));
  const maxY = fixedMax ?? Math.max(1, Math.ceil(Math.max(0, ...values) * 10) / 10);
  return html`<figure class="tp-chart"><figcaption>${label}</figcaption>
    <svg viewBox="0 0 600 230" role="img" aria-label="${label}" data-points="${rows.length}">
      ${ticks(maxY).map(value => { const y = point(0, value, maxX, maxY)[1]; return html`<line class="tp-grid" x1="48" y1="${y}" x2="564" y2="${y}"></line><text class="tp-tick" x="40" y="${y + 4}" text-anchor="end">${value.toFixed(2)}</text>`; })}
      ${ticks(maxX).map(value => html`<text class="tp-tick" x="${point(value, 0, maxX, maxY)[0]}" y="215" text-anchor="middle">${Math.round(value)}</text>`)}
      ${series.map((s, index) => html`<polyline class="tp-line tp-series-${index}" points="${rows.map(row => point(row.epoch, row[s.key], maxX, maxY).join(',')).join(' ')}" data-series="${s.key}"></polyline>`)}
      <text class="tp-tick" x="580" y="215">轮</text>
    </svg><div class="tp-legend">${series.map((s, index) => html`<span class="tp-legend-item tp-series-${index}">${s.label}</span>`)}</div>
  </figure>`;
}

export function comparison(model, template, role, metric, label) {
  const a = model?.[role.key]?.[metric] || 0;
  const b = template?.[role.key]?.[metric] || 0;
  return html`<figure class="tp-compare"><figcaption>${role.label} · ${label}</figcaption>
    <svg viewBox="0 0 600 100" role="img" aria-label="${role.label}${label}模型${pct(a)}模板${pct(b)}">
      <text class="tp-tick" x="0" y="30">模型</text><rect class="tp-model-bar" x="48" y="14" width="${a * 420}" height="22"></rect><text class="tp-value" x="${56 + a * 420}" y="30">${pct(a)}</text>
      <text class="tp-tick" x="0" y="68">模板</text><rect class="tp-template-bar" x="48" y="52" width="${b * 420}" height="22"></rect><text class="tp-value" x="${56 + b * 420}" y="68">${pct(b)}</text>
      ${metric === 'pass_rate' ? html`<line class="tp-target" x1="${48 + role.target * 420}" y1="8" x2="${48 + role.target * 420}" y2="78"></line><text class="tp-tick" x="${48 + role.target * 420}" y="96" text-anchor="middle">达标线 ${pct(role.target)}</text>` : ''}
    </svg></figure>`;
}

export function histogram(model, template, role) {
  const a = model?.[role.key]?.histogram || [];
  const b = template?.[role.key]?.histogram || [];
  const max = Math.max(1, ...a, ...b);
  return html`<figure class="tp-chart"><figcaption>${role.label}框 IoU 分布（张数）</figcaption>
    <svg viewBox="0 0 600 230" role="img" aria-label="${role.label}框IoU分布">
      ${ticks(max).map(n => html`<text class="tp-tick" x="36" y="${200 - n / max * 160}" text-anchor="end">${n.toFixed(1)}</text>`)}
      ${Array.from({ length: 10 }, (_, i) => html`<g><rect class="tp-model-bar" x="${48 + i * 52}" y="${196 - (a[i] || 0) / max * 160}" width="18" height="${(a[i] || 0) / max * 160}"></rect><rect class="tp-template-bar" x="${68 + i * 52}" y="${196 - (b[i] || 0) / max * 160}" width="18" height="${(b[i] || 0) / max * 160}"></rect><text class="tp-tick" x="${65 + i * 52}" y="218" text-anchor="middle">${(i / 10).toFixed(1)}–</text></g>`)}
    </svg><div class="tp-legend"><span class="tp-legend-item tp-series-0">模型</span><span class="tp-legend-item tp-series-1">模板</span></div></figure>`;
}
