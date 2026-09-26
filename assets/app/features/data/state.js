/**
 * 数据复盘：模块状态 + 纯函数（把 /api/analytics 与统计快照整理成视图要的行），node 单测全覆盖。
 * 语义与原 assets/data.js 一致：分档配色、表格列、Top 15、24 小时热力、到期预测、预警、顽固题与屡练不熟。
 * 颜色一律用语气名（success / warning / danger / info / accent / muted），由 CSS 映射到 token，不写行内样式。
 */
export const state = { phase: 'idle', analytics: null, error: '', exporting: false, exportError: '' };

const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };
export const pct = value => (value === null || value === undefined ? '—' : `${(num(value) * 100).toFixed(0)}%`);
/** 正确率 / 熟练度的语气：≥80% 好、≥50% 中、其余差；没有数据是 muted。 */
export const accTone = value => (value === null || value === undefined ? 'muted' : value >= 0.8 ? 'success' : value >= 0.5 ? 'warning' : 'danger');
/** 熟练度十档直方图的第 i 档：0–2 危险、3–5 拉升、6–7 稳定、8–9 掌握。 */
export const masteryTone = i => (i < 3 ? 'danger' : i < 6 ? 'warning' : i < 8 ? 'info' : 'success');

export function kpis(ov = {}) {
  return [
    { key: 'reviews', label: '总复习次数', value: String(num(ov.total_reviews)), hint: `答对 ${num(ov.total_correct)} / 答错 ${num(ov.total_wrong)}` },
    { key: 'accuracy', label: '总体正确率', value: pct(ov.accuracy) },
    { key: 'streak', label: '当前连续', value: `${num(ov.current_streak)} 天`, hint: `最长 ${num(ov.longest_streak)} 天` },
    { key: 'leech', label: '顽固题', value: String(num(ov.leech)), hint: `从未复习 ${num(ov.never_reviewed)}` },
    { key: 'mastery', label: '平均熟练度', value: pct(ov.avg_mastery), hint: `衰减后 ${pct(ov.avg_decayed_mastery)}` },
    { key: 'ef', label: '平均 EF', value: String(ov.avg_ef ?? '—'), hint: `平均复习 ${ov.avg_attempts ?? 0} 次` },
    { key: 'active', label: '活跃天数', value: String(num(ov.active_days)), hint: ov.first_review ? `自 ${ov.first_review}` : '' },
    { key: 'recent', label: '近 30 天复习', value: String(num(ov.reviews_last_30)), hint: `近 7 天 ${num(ov.reviews_last_7)}` },
  ];
}

/** 一组横条：rows = [{ key, label, value, display?, tone }]；pct 是相对本组最大值的百分比（整数）。 */
export function bars(rows) {
  const max = Math.max(1, ...rows.map(r => num(r.value)));
  return rows.map(r => ({ ...r, value: num(r.value), display: r.display ?? String(num(r.value)), pct: Math.round(num(r.value) / max * 100) }));
}

const keysOf = obj => Object.keys(obj || {});
export function barSets(a) {
  const d = a.distributions || {};
  const mh = d.mastery_histogram || {};
  const dh = d.decayed_histogram || {};
  const ef = d.ef_dist || {};
  const dd = d.difficulty_dist || {};
  const rep = d.repetition_dist || {};
  const iv = d.interval_dist || {};
  const bs = a.accuracy?.by_score || {};
  const wd = a.behavior?.by_weekday || {};
  const fc = a.forecast || {};
  const four = i => (i === 0 ? 'danger' : i === 1 ? 'warning' : i === 2 ? 'info' : 'success');
  return {
    mastery: bars(keysOf(mh).map((k, i) => ({ key: k, label: `${k}%`, value: mh[k], tone: masteryTone(i) }))),
    decayed: bars(keysOf(mh).map((k, i) => ({ key: k, label: `${k}%`, value: dh[k], tone: masteryTone(i) }))),
    ef: bars(keysOf(ef).map((k, i) => ({ key: k, label: k, value: ef[k], tone: four(i) }))),
    difficulty: bars(keysOf(dd).map(k => { const i = +k; return { key: k, label: `Lv.${k}`, value: dd[k], tone: i <= 3 ? 'success' : i <= 6 ? 'info' : i <= 8 ? 'accent' : 'danger' }; })),
    repetition: bars(keysOf(rep).map((k, i) => ({ key: k, label: k, value: rep[k], tone: i === 0 ? 'danger' : i === 1 ? 'warning' : i <= 2 ? 'info' : 'success' }))),
    interval: bars(keysOf(iv).map((k, i) => ({ key: k, label: `${k}天`, value: iv[k], tone: i <= 1 ? 'danger' : i <= 2 ? 'warning' : i <= 3 ? 'info' : 'success' }))),
    score: bars(keysOf(bs).filter(s => bs[s].count).map(s => ({ key: s, label: `${s}分`, value: Math.round(num(bs[s].accuracy) * 100),
      display: `${pct(bs[s].accuracy)} (${bs[s].count})`, tone: accTone(bs[s].accuracy) }))),
    weekday: bars(keysOf(wd).map(k => ({ key: k, label: k, value: wd[k], tone: 'accent' }))),
    forecast: bars([{ key: '0', label: '今日', value: fc['0'], tone: 'warning' },
      ...[1, 2, 3, 4, 5, 6, 7].map(i => ({ key: String(i), label: `+${i}天`, value: fc[String(i)], tone: 'info' })),
      { key: '7+', label: '7天+', value: fc['7+'], tone: 'success' }]),
  };
}

/** 24 小时热力：级别 0–4 按该小时次数占峰值的比例。 */
export function hours(byHour) {
  const counts = Array.from({ length: 24 }, (_, h) => num((byHour || {})[h] ?? (byHour || {})[String(h)]));
  const max = Math.max(1, ...counts);
  return counts.map((count, h) => ({ hour: h, label: String(h).padStart(2, '0'), count, level: count ? Math.max(1, Math.ceil(count / max * 4)) : 0 }));
}

export function alerts(al = {}) {
  return [
    { key: 'overdue', label: '逾期', value: num(al.overdue), tone: 'danger' },
    { key: 'today', label: '今日到期', value: num(al.due_today), tone: 'warning' },
    { key: 'd3', label: '未来 3 天到期', value: num(al.due_next_3_days), tone: 'warning' },
    { key: 'd7', label: '未来 7 天到期', value: num(al.due_next_7_days), tone: 'info' },
    { key: 'low', label: '未到期低熟练度', value: num(al.low_mastery_not_due), tone: 'accent' },
    { key: 'leech', label: '顽固题', value: num(al.leech), tone: 'accent' },
  ];
}

/** 标记分布（来自统计快照）：未停用题上的用户标记计数，降序，同数按名称。 */
export function labelCounts(items) {
  const counts = {};
  (items || []).filter(item => !item.suspended).forEach(item => (item.labels || []).forEach(label => {
    const name = String(label || '').trim();
    if (name) counts[name] = (counts[name] || 0) + 1;
  }));
  const rows = Object.entries(counts).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN'));
  const max = Math.max(1, ...rows.map(r => r[1]));
  return rows.map(([name, count]) => ({ name, count, pct: Math.round(count / max * 100) }));
}

/** 每日练习趋势（统计快照的 daily_trend）：日期升序，另给合计、最后一天、单日最高。 */
export function trend(daily) {
  const dates = keysOf(daily).sort();
  const points = dates.map(date => ({ date, value: num(daily[date]) }));
  return { points, total: points.reduce((s, p) => s + p.value, 0), last: points.length ? points[points.length - 1].value : 0,
    max: Math.max(0, ...points.map(p => p.value)) };
}

/** 难度 × 熟练度气泡：难度取整到 1–10，熟练度分 5 档；每格给题数与平均熟练度。 */
export function scatterBins(items, bands = 5) {
  const bins = {};
  (items || []).filter(p => p && p.difficulty != null && p.mastery != null).forEach(p => {
    const d = Math.max(1, Math.min(10, Math.round(num(p.difficulty, 5))));
    const m = Math.max(0, Math.min(1, num(p.mastery)));
    const b = Math.min(bands - 1, Math.floor(m * bands));
    const key = `${d}_${b}`;
    bins[key] ||= { key, d, b, count: 0, sum: 0 };
    bins[key].count += 1;
    bins[key].sum += m;
  });
  return Object.values(bins).map(o => ({ ...o, avg: o.sum / o.count })).sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

export const subjectsSorted = rows => [...(rows || [])].filter(s => s && s.subject).sort((a, b) => String(a.subject).localeCompare(String(b.subject), 'zh-CN'));
