/**
 * 仪表盘：模块状态 + 纯函数（「今天」卡、概览数字、30 天热力、最薄弱科目、最近动态），node 单测全覆盖。
 * 数据来自 store.data（domain/data.js 的快照）与 Session 列表；不新增接口、不写 Ledger。
 */
import { activeItems, openSessions, dayKey, todayTarget } from './plan.js';

export const state = {
  showAll: false,
  plan: [],
  recent: { phase: 'idle', commits: [], retraction: null, error: '' },
};

const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };
const clamp = (value, min, max) => Math.max(min, Math.min(max, value));
const WEEK = '日一二三四五六';

export const dateStamp = today => `${today.getMonth() + 1} 月 ${today.getDate()} 日 · 星期${WEEK[today.getDay()]}`;

/** 「今天」卡：待复习数、分项、今日进度与建议题量、一句提示、一到两个动作（跳转描述同 plan.js）。 */
export function todaySummary({ items = [], data = {}, sessions = [], dueDays, today = new Date() }) {
  const stamp = dateStamp(today);
  if (!items.length) {
    return { empty: true, stamp, waiting: 0, level: 'empty', splits: [], note: '先录入几道错题，调度、推荐和复盘才有东西可算。',
      actions: [{ label: '去录入题目', primary: true, go: 'page', page: 'create' }] };
  }
  const active = activeItems(items);
  const overdueDays = active.map(dueDays).filter(d => d !== null && d < 0);
  const overdue = overdueDays.length;
  const dueToday = active.filter(item => dueDays(item) === 0).length;
  const waiting = overdue + dueToday;
  const pendingQ = openSessions(sessions).reduce((sum, s) => sum + num(s.pending_count, num(s.count)), 0);
  const done = num((data?.daily_trend || {})[dayKey(today)]);
  const target = todayTarget({ items, dueDays });
  const worst = overdue ? Math.abs(Math.min(...overdueDays)) : 0;
  const splits = [];
  if (overdue) splits.push({ tone: 'danger', label: `逾期 ${overdue}` });
  if (dueToday) splits.push({ tone: 'warning', label: `今日到期 ${dueToday}` });
  if (pendingQ) splits.push({ tone: 'info', label: `未录反馈 ${pendingQ}` });
  if (!splits.length) splits.push({ tone: 'success', label: '没有到期的题' });
  const actions = [waiting
    ? { label: '开始复习', primary: true, go: 'review' }
    : { label: '随便练几题', primary: true, go: 'instant', preset: {} }];
  if (overdue) actions.push({ label: `只看逾期 ${overdue} 题`, go: 'questions', preset: { 'q-filter-due': 'overdue', 'q-sort': 'due-asc' } });
  else if (pendingQ) actions.push({ label: '去录反馈', go: 'page', page: 'feedback' });
  const note = waiting
    ? (overdue ? `最久的一道已经逾期 ${worst} 天，逾期越久熟练度衰减越多。` : '今天做完，这批题的间隔就能顺延到下一档。')
    : '到期队列是空的。想加练可以挑熟练度低的题，或者去录入新题。';
  return { empty: false, stamp, waiting, overdue, dueToday, pendingQ, done, target, worst, splits, note, actions,
    level: waiting ? (overdue ? 'overdue' : 'due') : 'clear', pct: Math.round(clamp(done / Math.max(1, target) * 100, 0, 100)) };
}

export function kpis(data) {
  const d = data || {};
  const total = num(d.total);
  const killed = num(d.killed);
  return [
    { key: 'total', label: '总题数', value: String(total) },
    { key: 'killed', label: '已击杀', value: String(killed), hint: total ? `${(killed / total * 100).toFixed(0)}% 击杀率` : '' },
    { key: 'attack', label: '待攻克', value: String(num(d.attacking)) },
    { key: 'avg', label: '平均熟练度', value: `${(num(d.avg_mastery) * 100).toFixed(0)}%` },
    { key: 'suspended', label: '停用题目', value: String(num(d.suspended)), hint: '不参与复习' },
  ];
}

/** 近 30 天热力：每天一格，级别 0–4 按当天次数占峰值的比例；另给总数、活跃天数、峰值与首尾两个刻度（两行各 15 格，末格是今天）。 */
export function heatmap(activity, today = new Date()) {
  const days = [];
  for (let i = 29; i >= 0; i -= 1) {
    const dt = new Date(today.getFullYear(), today.getMonth(), today.getDate() - i);
    days.push({ key: dayKey(dt), label: `${dt.getMonth() + 1}/${dt.getDate()}`, count: num((activity || {})[dayKey(dt)]) });
  }
  const max = Math.max(1, ...days.map(d => d.count));
  days.forEach(d => { d.level = d.count ? Math.max(1, Math.ceil(d.count / max * 4)) : 0; });
  const peak = days.reduce((best, d) => (d.count > best.count ? d : best), days[0]);
  return { days, total: days.reduce((s, d) => s + d.count, 0), active: days.filter(d => d.count > 0).length, peak: peak.count,
    ticks: [days[0].label, '今天'] };
}

/** 最薄弱的科目：按衰减后熟练度升序，题量 ≥ min 才纳入，最多 6 个。 */
export function weakSubjects(items, min = 5) {
  const groups = {};
  (items || []).filter(item => !item.suspended).forEach(item => {
    const key = String(item.subject || '').trim();
    if (!key) return;
    groups[key] ||= { key, count: 0, sum: 0 };
    groups[key].count += 1;
    groups[key].sum += num(item.decayed_mastery, num(item.mastery));
  });
  return Object.values(groups).filter(r => r.count >= min).map(r => {
    const pct = Math.round(clamp(r.sum / r.count * 100, 0, 100));
    return { key: r.key, count: r.count, pct, tone: pct < 35 ? 'danger' : pct < 60 ? 'warning' : 'success' };
  }).sort((a, b) => a.pct - b.pct || a.key.localeCompare(b.key, 'zh-CN')).slice(0, 6);
}

/** 行动推荐的「展开 / 收起」：默认显示前 4 条。 */
export function visiblePlan(plan, showAll, limit = 4) {
  const rows = showAll ? plan : plan.slice(0, limit);
  return { rows, hidden: plan.length - rows.length, collapsible: showAll && plan.length > limit };
}
