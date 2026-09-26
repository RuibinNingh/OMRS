// 数据复盘（features/data）的纯函数：概览、横条分档与配色、24 小时热力、预警、标记分布、趋势、气泡分箱，以及三张 SVG 的产出。
import test from 'node:test';
import assert from 'node:assert/strict';
import * as S from '../../assets/app/features/data/state.js';
import { trendSvg, radarSvg, scatterSvg, smoothPath } from '../../assets/app/features/data/charts.js';

const A = {
  overview: { total_reviews: 42, total_correct: 26, total_wrong: 16, accuracy: 0.619, current_streak: 1, longest_streak: 3, leech: 2, never_reviewed: 10,
    avg_mastery: 0.16, avg_decayed_mastery: 0.12, avg_ef: 2.5, avg_attempts: 1.08, active_days: 4, first_review: '2026-09-01', reviews_last_30: 40, reviews_last_7: 12 },
  distributions: {
    mastery_histogram: { '0-10': 20, '10-20': 7, '20-30': 1, '30-40': 3, '40-50': 7, '50-60': 0, '60-70': 0, '70-80': 0, '80-90': 0, '90-100': 1 },
    decayed_histogram: { '0-10': 22, '10-20': 5 }, ef_dist: { '1.3-1.7': 1, '1.7-2.1': 0, '2.1-2.5': 3, '2.5-3.0': 35 },
    difficulty_dist: { 1: 0, 3: 2, 5: 39, 7: 1, 9: 4 }, repetition_dist: { 0: 21, 1: 14, 2: 4, 3: 0, '5+': 1 }, interval_dist: { '0-1': 21, '2-6': 14, '7-15': 4, '16-30': 0, '31-60': 0, '60+': 1 },
  },
  accuracy: { by_score: { 0: { count: 0, accuracy: null }, 2: { count: 3, accuracy: 1 }, 6: { count: 6, accuracy: 0.333 } } },
  behavior: { by_weekday: { 周一: 0, 周五: 42 }, by_hour: { 11: 42, 9: 10, '23': 1 } },
  forecast: { 0: 10, 1: 11, 6: 14, '7+': 3 },
  review_alert: { overdue: 2, due_today: 10, due_next_3_days: 11, due_next_7_days: 25, low_mastery_not_due: 28, leech: 0 },
};

test('pct and tones', () => {
  assert.deepEqual([S.pct(null), S.pct(undefined), S.pct(0.619), S.pct(0)], ['—', '—', '62%', '0%']);
  assert.deepEqual([S.accTone(null), S.accTone(0.8), S.accTone(0.5), S.accTone(0.49)], ['muted', 'success', 'warning', 'danger']);
  assert.deepEqual([0, 2, 3, 5, 6, 7, 8, 9].map(S.masteryTone), ['danger', 'danger', 'warning', 'warning', 'info', 'info', 'success', 'success']);
});

test('kpis: eight cells with legacy labels and hints', () => {
  const k = S.kpis(A.overview);
  assert.deepEqual(k.map(r => r.value), ['42', '62%', '1 天', '2', '16%', '2.5', '4', '40']);
  assert.deepEqual(k.map(r => r.hint || ''), ['答对 26 / 答错 16', '', '最长 3 天', '从未复习 10', '衰减后 12%', '平均复习 1.08 次', '自 2026-09-01', '近 7 天 12']);
  assert.equal(S.kpis({}).find(r => r.key === 'active').hint, '');
});

test('barSets: bands, tones, relative width, score filter and forecast order', () => {
  const b = S.barSets(A);
  assert.equal(b.mastery.length, 10);
  assert.deepEqual(b.mastery.slice(0, 2).map(r => [r.label, r.value, r.pct, r.tone]), [['0-10%', 20, 100, 'danger'], ['10-20%', 7, 35, 'danger']]);
  assert.equal(b.decayed[2].value, 0, '衰减后缺档按 0');
  assert.deepEqual(b.ef.map(r => r.tone), ['danger', 'warning', 'info', 'success']);
  assert.deepEqual(b.difficulty.map(r => [r.label, r.tone]), [['Lv.1', 'success'], ['Lv.3', 'success'], ['Lv.5', 'info'], ['Lv.7', 'accent'], ['Lv.9', 'danger']]);
  assert.deepEqual(b.interval.map(r => r.label), ['0-1天', '2-6天', '7-15天', '16-30天', '31-60天', '60+天']);
  assert.deepEqual(b.score.map(r => [r.label, r.value, r.display, r.tone]), [['2分', 100, '100% (3)', 'success'], ['6分', 33, '33% (6)', 'danger']]);
  assert.deepEqual(b.forecast.map(r => [r.label, r.value]), [['今日', 10], ['+1天', 11], ['+2天', 0], ['+3天', 0], ['+4天', 0], ['+5天', 0], ['+6天', 14], ['+7天', 0], ['7天+', 3]]);
  assert.deepEqual(S.bars([]), []);
  assert.equal(S.barSets({}).mastery.length, 0);
});

test('hours, alerts, labelCounts, trend, scatterBins, subjectsSorted', () => {
  const h = S.hours(A.behavior.by_hour);
  assert.equal(h.length, 24);
  assert.deepEqual([h[11].level, h[9].level, h[23].level, h[0].level, h[0].label], [4, 1, 1, 0, '00']);
  assert.deepEqual(S.alerts(A.review_alert).map(r => [r.value, r.tone]), [[2, 'danger'], [10, 'warning'], [11, 'warning'], [25, 'info'], [28, 'accent'], [0, 'accent']]);
  assert.deepEqual(S.labelCounts([{ labels: ['乙', '甲'] }, { labels: ['甲', ' '] }, { labels: ['丙'], suspended: true }]),
    [{ name: '甲', count: 2, pct: 100 }, { name: '乙', count: 1, pct: 50 }]);
  const t = S.trend({ '2026-09-03': 2, '2026-09-01': 5 });
  assert.deepEqual([t.points.map(p => p.date), t.total, t.last, t.max], [['2026-09-01', '2026-09-03'], 7, 2, 5]);
  assert.deepEqual(S.trend({}), { points: [], total: 0, last: 0, max: 0 });
  const bins = S.scatterBins([{ difficulty: 5, mastery: 0.1 }, { difficulty: 5.4, mastery: 0.15 }, { difficulty: 12, mastery: 1 }, { difficulty: null, mastery: 0.2 }]);
  assert.deepEqual(bins.map(o => [o.key, o.count]), [['5_0', 2], ['10_4', 1]]);
  assert.equal(Math.round(bins[0].avg * 1000), 125);
  assert.deepEqual(S.subjectsSorted([{ subject: '物理' }, {}, { subject: '化学' }]).map(s => s.subject), ['化学', '物理']);
});

test('SVG builders: trend path and peak, radar points, scatter bubbles; no inline style', () => {
  assert.equal(smoothPath([]), '');
  assert.equal(smoothPath([{ x: 0, y: 1 }]), 'M 0 1');
  const svg = trendSvg(S.trend({ '2026-09-01': 1, '2026-09-02': 4 })).text;
  assert.match(svg, /class="dat-trend__peak"/);
  assert.match(svg, /2026-09-02：4 次/);
  assert.match(svg, /aria-label="每日练习趋势：合计 5 次，单日最高 4 次"/);
  const radar = radarSvg([{ subject: '化学', avg_mastery: 0.9 }, { subject: '数学', avg_mastery: 0.3 }, { subject: '物理', avg_mastery: 0.6 }]).text;
  assert.equal((radar.match(/<circle/g) || []).length, 3);
  assert.match(radar, /data-tone="success"><title>化学 · 90%/);
  const sc = scatterSvg(S.scatterBins([{ difficulty: 5, mastery: 0.8 }])).text;
  assert.match(sc, /data-tone="success"><title>难度 5 · 熟练度 80–100% · 1 题（均 80%）/);
  for (const text of [svg, radar, sc]) assert.ok(!/style=|font-size=|fill="#|stroke="var/.test(text), '颜色与字号全在 CSS');
});
