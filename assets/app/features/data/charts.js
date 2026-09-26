/**
 * 数据复盘的三张 SVG 图（原 assets/data.js 的 renderTrendChart / renderSubjectRadar / renderDataScatter，几何原样）。
 * 只产出 html``；颜色、线宽、字号全部走 data.css 的类（svg 属性里不写颜色与字号），语气用 data-tone。
 */
import { html, each } from '../../core/html.js';
import { pct, accTone } from './state.js';

const r1 = v => Math.round(v * 10) / 10;

export function smoothPath(points) {
  if (!points.length) return '';
  let path = `M ${points[0].x} ${points[0].y}`;
  for (let i = 1; i < points.length; i += 1) {
    const prev = points[i - 1], cur = points[i], mid = r1((prev.x + cur.x) / 2);
    path += ` C ${mid} ${prev.y}, ${mid} ${cur.y}, ${cur.x} ${cur.y}`;
  }
  return path;
}

/** 每日练习趋势：t = state.trend() 的结果。 */
export function trendSvg(t) {
  const w = 680, h = 286, padL = 44, padR = 18, padT = 18, padB = 38, baseY = h - padB, plotH = h - padT - padB, plotW = w - padL - padR;
  const max = Math.max(1, t.max);
  const n = t.points.length;
  const pts = t.points.map((p, i) => ({ ...p, x: r1(padL + (i / (n - 1 || 1)) * plotW), y: r1(baseY - (p.value / max) * plotH) }));
  const line = smoothPath(pts);
  const area = pts.length ? `${line} L ${pts[pts.length - 1].x} ${baseY} L ${pts[0].x} ${baseY} Z` : '';
  const grid = [0, 1, 2, 3, 4].map(i => { const y = r1(baseY - (i / 4) * plotH); return html`<line x1="${padL}" y1="${y}" x2="${w - padR}" y2="${y}" class="dat-svg__grid"/><text x="${padL - 10}" y="${y + 4}" text-anchor="end">${Math.round(max * i / 4)}</text>`; });
  const ticks = pts.filter((_, i) => i === 0 || i === n - 1 || i === Math.floor(n / 2));
  const anchor = x => (x === padL ? 'start' : x === w - padR ? 'end' : 'middle');
  return html`<svg viewBox="0 0 ${w} ${h}" class="dat-svg" role="img" aria-label="每日练习趋势：合计 ${t.total} 次，单日最高 ${t.max} 次">
  ${grid}<path d="${area}" class="dat-trend__area"/><path d="${line}" class="dat-trend__line"/>
  ${each(pts.filter(p => p.value > 0), p => p.date, p => html`<circle cx="${p.x}" cy="${p.y}" r="${p.value === max ? 5 : 3.5}" class="${p.value === max ? 'dat-trend__peak' : 'dat-trend__dot'}"><title>${p.date}：${p.value} 次</title></circle>`)}
  <line x1="${padL}" y1="${baseY}" x2="${w - padR}" y2="${baseY}" class="dat-svg__axis"/>
  ${each(ticks, p => p.date, p => html`<text x="${p.x}" y="${h - 12}" text-anchor="${anchor(p.x)}">${p.date.slice(5)}</text>`)}
</svg>`;
}

/** 科目雷达：subjects 已按名称排序；少于 3 个科目时调用方显示说明而不是图。 */
export function radarSvg(subjects) {
  const w = 520, h = 300, cx = w / 2, cy = 145, r = 98;
  const angle = i => -Math.PI / 2 + (Math.PI * 2 * i / subjects.length);
  const point = (value, i) => ({ x: r1(cx + Math.cos(angle(i)) * r * value), y: r1(cy + Math.sin(angle(i)) * r * value) });
  const ring = level => subjects.map((_, i) => { const p = point(level, i); return `${p.x},${p.y}`; }).join(' ');
  const clamp = v => Math.max(0, Math.min(1, Number(v) || 0));
  const dots = subjects.map((s, i) => ({ s, p: point(clamp(s.avg_mastery), i) }));
  return html`<svg viewBox="0 0 ${w} ${h}" class="dat-svg dat-svg--radar" role="img" aria-label="各科平均熟练度">
  ${[0.25, 0.5, 0.75, 1].map(level => html`<polygon points="${ring(level)}" class="dat-svg__grid"/><text x="${cx + 4}" y="${r1(cy - r * level + 4)}">${Math.round(level * 100)}%</text>`)}
  ${subjects.map((s, i) => { const end = point(1, i), label = point(1.18, i); const a = Math.abs(label.x - cx) < 8 ? 'middle' : label.x > cx ? 'start' : 'end';
    return html`<line x1="${cx}" y1="${cy}" x2="${end.x}" y2="${end.y}" class="dat-svg__grid"/><text x="${label.x}" y="${r1(label.y + 4)}" text-anchor="${a}" class="dat-svg__label">${s.subject}</text>`; })}
  <polygon points="${dots.map(d => `${d.p.x},${d.p.y}`).join(' ')}" class="dat-radar__area"/>
  ${dots.map(({ s, p }) => html`<circle cx="${p.x}" cy="${p.y}" r="4.5" class="dat-svg__dot" data-tone="${accTone(s.avg_mastery)}"><title>${s.subject} · ${pct(s.avg_mastery)}</title></circle>`)}
  <text x="${cx}" y="${h - 12}" text-anchor="middle">各科平均熟练度</text>
</svg>`;
}

/** 难度 × 熟练度气泡：bins = state.scatterBins()。 */
export function scatterSvg(bins, bands = 5) {
  const sw = 640, sh = 300, pad = 36, baseY = sh - pad, plotW = sw - pad * 2, plotH = sh - pad * 2;
  const tone = m => (m >= 0.7 ? 'success' : m >= 0.45 ? 'warning' : 'danger');
  const band = b => `${b * 20}–${b * 20 + 20}%`;
  return html`<svg viewBox="0 0 ${sw} ${sh}" class="dat-svg" role="img" aria-label="难度与熟练度分布">
  <rect x="${pad}" y="${pad}" width="${plotW}" height="${plotH}" rx="6" class="dat-scatter__plot"/>
  ${Array.from({ length: bands + 1 }, (_, i) => { const y = r1(baseY - (i / bands) * plotH); return html`<line x1="${pad}" y1="${y}" x2="${sw - pad}" y2="${y}" class="dat-svg__grid"/>`; })}
  ${[0, 20, 40, 60, 80, 100].map(v => html`<text x="${pad - 8}" y="${r1(baseY - (v / 100) * plotH + 4)}" text-anchor="end">${v}%</text>`)}
  ${[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(v => html`<text x="${r1(pad + ((v - 1) / 9) * plotW)}" y="${sh - 13}" text-anchor="middle">${v}</text>`)}
  <line x1="${pad}" y1="${baseY}" x2="${sw - pad}" y2="${baseY}" class="dat-svg__axis"/><line x1="${pad}" y1="${pad}" x2="${pad}" y2="${baseY}" class="dat-svg__axis"/>
  <text x="${sw / 2}" y="${sh - 1}" text-anchor="middle" class="dat-svg__label">难度</text><text x="13" y="${sh / 2}" transform="rotate(-90 13,${sh / 2})" class="dat-svg__label">熟练度</text>
  ${each(bins, o => o.key, o => html`<circle cx="${r1(pad + ((o.d - 1) / 9) * plotW)}" cy="${r1(baseY - ((o.b + 0.5) / bands) * plotH)}" r="${r1(Math.max(4, Math.min(26, Math.sqrt(o.count) * 4.6)))}" class="dat-scatter__bubble" data-tone="${tone(o.avg)}"><title>难度 ${o.d} · 熟练度 ${band(o.b)} · ${o.count} 题（均 ${(o.avg * 100).toFixed(0)}%）</title></circle>`)}
</svg>`;
}
