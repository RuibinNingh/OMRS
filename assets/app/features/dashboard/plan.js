/**
 * 仪表盘：行动推荐的规则集（原 assets/actions.js 的 buildActionPlan，逻辑与文案原样搬来），纯函数，node 单测全覆盖。
 * 输入 env = { items, data, sessions, dueDays(item), today }；每条建议 { key, level, icon, metric, title, detail, actions }，
 * actions 里是跳转描述 { label, primary, go, preset|page|session }，由 index.js 执行（不再是闭包）：
 *   go:'questions' 带题库预设（键沿用旧元素 id）；go:'instant' 带练习预设；go:'review' 打开复习调度的安排；
 *   go:'feedback' 带 Session；go:'page' 切到某页。
 */
export const LEVELS = {
  urgent: { label: '紧急', rank: 0, tone: 'danger' },
  warn: { label: '建议', rank: 1, tone: 'warning' },
  info: { label: '可选', rank: 2, tone: 'info' },
  good: { label: '状态良好', rank: 3, tone: 'success' },
};

const num = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };
const pct = value => `${(value * 100).toFixed(0)}%`;

export function dayKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
/** 'YYYY-MM-DD' 或 'YYYY/MM/DD' → 距 today 的整天数（不小于 0）；无法解析时给 fallback。与旧 daysSinceReview 一致。 */
export function daysSince(value, today, fallback = 30) {
  const parts = String(value || '').trim().split(/[-/]/).map(Number);
  if (parts.length !== 3 || !parts.every(Number.isInteger)) return fallback;
  const [y, m, d] = parts;
  const date = new Date(y, m - 1, d);
  if (date.getFullYear() !== y || date.getMonth() !== m - 1 || date.getDate() !== d) return fallback;
  const diff = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()) - Date.UTC(y, m - 1, d);
  return Math.max(0, Math.floor(diff / 86400000));
}
export const isKilled = item => num(item.mastery) >= 1 || String(item.tag || '').includes('已击杀');
export const activeItems = items => (items || []).filter(item => !item.suspended && !isKilled(item));
export const openSessions = sessions => (sessions || []).filter(session => (session.status || 'active') === 'active');

export function recentReviewCount(trend, today, days) {
  let sum = 0;
  for (let offset = 0; offset < days; offset++) {
    sum += num((trend || {})[dayKey(new Date(today.getFullYear(), today.getMonth(), today.getDate() - offset))]);
  }
  return sum;
}
export function daysSinceLastReview(trend, today) {
  const keys = Object.keys(trend || {}).filter(key => num(trend[key]) > 0).sort();
  return keys.length ? daysSince(keys[keys.length - 1], today, 0) : null;
}
/** 按维度找最薄弱的一组：题量够多才有参考价值；只有一组时不算「最薄弱」。 */
export function weakestGroup(items, field, minCount) {
  const groups = {};
  items.forEach(item => {
    const key = String(item[field] || '').trim();
    if (!key) return;
    groups[key] ||= { key, count: 0, sum: 0 };
    groups[key].count += 1;
    groups[key].sum += num(item.decayed_mastery, num(item.mastery));
  });
  const rows = Object.values(groups).filter(row => row.count >= minCount)
    .map(row => ({ ...row, avg: row.sum / row.count })).sort((a, b) => a.avg - b.avg);
  return rows.length > 1 ? rows[0] : null;
}
/** 今天建议练几题：到期（含逾期）+ 最多 3 道顽固题，封顶 20。 */
export function todayTarget({ items, dueDays }) {
  const active = activeItems(items);
  const due = active.filter(item => { const d = dueDays(item); return d !== null && d <= 0; }).length;
  return Math.min(20, due + Math.min(3, active.filter(item => item.is_leech).length));
}

export function buildPlan({ items = [], data = {}, sessions = [], dueDays, today = new Date() }) {
  if (!items.length) {
    return [{ key: 'empty', level: 'info', icon: 'plus', metric: '0', title: '题库还是空的', detail: '先录入几道错题，推荐、调度和复盘才有东西可算。',
      actions: [{ label: '去录入题目', primary: true, go: 'page', page: 'create' }] }];
  }
  const active = activeItems(items);
  const trend = data?.daily_trend || {};
  const plan = [];
  const due = item => dueDays(item);

  const overdue = active.filter(item => { const d = due(item); return d !== null && d < 0; });
  if (overdue.length) {
    const worst = Math.max(...overdue.map(item => Math.abs(due(item))));
    plan.push({ key: 'overdue', level: 'urgent', icon: 'alert-triangle', metric: String(overdue.length), title: `${overdue.length} 道题已经逾期`,
      detail: `最久的一道逾期 ${worst} 天。逾期越久衰减越多，先清这批的收益最高。`,
      actions: [{ label: '立刻练逾期题', primary: true, go: 'instant', preset: {} },
        { label: '在题库查看', go: 'questions', preset: { 'q-filter-due': 'overdue', 'q-sort': 'due-asc' } }] });
  }
  const dueToday = active.filter(item => due(item) === 0);
  if (dueToday.length) {
    plan.push({ key: 'due_today', level: 'warn', icon: 'clock', metric: String(dueToday.length), title: `今天有 ${dueToday.length} 道题到期`,
      detail: '按 SM-2 排的今日份，今天做完就能把间隔顺延到下一档。',
      actions: [{ label: '开始常规复习', primary: true, go: 'review' },
        { label: '查看清单', go: 'questions', preset: { 'q-filter-due': 'today', 'q-sort': 'mastery-asc' } }] });
  }
  const pending = openSessions(sessions);
  if (pending.length) {
    const total = pending.reduce((sum, session) => sum + num(session.count), 0);
    plan.push({ key: 'pending_feedback', level: 'warn', icon: 'check-circle', metric: String(pending.length), title: `${pending.length} 个 Session 还没录反馈`,
      detail: `共 ${total} 道题。没有反馈就不会更新熟练度和到期日，练了也不算数。`,
      actions: [{ label: '去录反馈', primary: true, go: 'feedback', session: pending[0].session_id || '' }] });
  }
  const leeches = active.filter(item => item.is_leech);
  if (leeches.length) {
    plan.push({ key: 'leech', level: 'urgent', icon: 'refresh', metric: String(leeches.length), title: `${leeches.length} 道顽固题卡住了`,
      detail: '这些题错的次数明显偏多。与其再刷一遍，不如回去补前置知识点，或者把解法重新拆一遍写进错因。',
      actions: [{ label: '看顽固题清单', primary: true, go: 'page', page: 'data' },
        { label: '按熟练度排题库', go: 'questions', preset: { 'q-sort': 'mastery-asc' } }] });
  }
  const untouched = active.filter(item => num(item.attempts) === 0);
  if (untouched.length >= 3) {
    plan.push({ key: 'untouched', level: 'info', icon: 'inbox', metric: String(untouched.length), title: `${untouched.length} 道题录入后一次都没练`,
      detail: '没有一次反馈，算法就没有起点，这些题不会主动出现在推荐里。',
      actions: [{ label: '挑出来练一轮', primary: true, go: 'questions', preset: { 'q-sort': 'date-desc' } }] });
  }
  const cold = active.filter(item => item.last_review && daysSince(item.last_review, today, 0) > 30);
  if (cold.length >= 3) {
    plan.push({ key: 'cold', level: 'warn', icon: 'calendar', metric: String(cold.length), title: `${cold.length} 道题超过 30 天没碰`,
      detail: '衰减公式下这批题的实际掌握度已经掉了一大截，即使标记是已掌握也不一定还在。',
      actions: [{ label: '按最近复习排序', primary: true, go: 'questions', preset: { 'q-sort': 'date-desc' } }] });
  }
  const last7 = recentReviewCount(trend, today, 7);
  const idle = daysSinceLastReview(trend, today);
  if (idle !== null && idle >= 3) {
    plan.push({ key: 'idle', level: idle >= 7 ? 'warn' : 'info', icon: 'pause', metric: `${idle}天`, title: `已经 ${idle} 天没有练习记录`,
      detail: '断得越久，回来时到期队列越长。先做 5 道，把手感和队列一起找回来。',
      actions: [{ label: '做 5 道找回手感', primary: true, go: 'instant', preset: { 'inst-count': '5' } }] });
  } else if (last7 === 0 && idle === null) {
    plan.push({ key: 'never', level: 'info', icon: 'play', metric: '0', title: '还没有任何练习记录',
      detail: '录完题之后练一轮，熟练度、EF 和到期日才会开始跑。',
      actions: [{ label: '开始第一轮练习', primary: true, go: 'instant', preset: {} }] });
  }
  const lowNotDue = active.filter(item => { const d = due(item); return d !== null && d > 0 && num(item.decayed_mastery, 1) < 0.5; });
  if (lowNotDue.length >= 3) {
    plan.push({ key: 'low_not_due', level: 'info', icon: 'chevron-down', metric: String(lowNotDue.length), title: `${lowNotDue.length} 道题没到期但已经掉到一半以下`,
      detail: '排期还没轮到，衰减后的熟练度却已经低于 50%。有余力时可以提前捞一遍。',
      actions: [{ label: '按衰减挑题', primary: true, go: 'questions', preset: { 'q-filter-due': 'future', 'q-sort': 'mastery-asc' } }] });
  }
  const subject = weakestGroup(active, 'subject', 3);
  if (subject && subject.avg < 0.55) {
    plan.push({ key: 'weak_subject', level: 'info', icon: 'target', metric: pct(subject.avg), title: `${subject.key} 是目前最薄弱的科目`,
      detail: `${subject.count} 道未击杀题，衰减后平均熟练度 ${pct(subject.avg)}，明显落后于其他科目。`,
      actions: [{ label: `专练 ${subject.key}`, primary: true, go: 'instant', preset: { 'inst-subject': subject.key } },
        { label: '看该科目题目', go: 'questions', preset: { 'q-filter-subj': subject.key } }] });
  }
  const category = weakestGroup(active, 'category', 3);
  if (category && category.avg < 0.45) {
    plan.push({ key: 'weak_category', level: 'info', icon: 'grid', metric: pct(category.avg), title: `分类「${category.key}」整体偏低`,
      detail: `${category.count} 道题，衰减后平均 ${pct(category.avg)}。整块偏低往往是知识点没通，不是手生。`,
      actions: [{ label: '专练这一类', primary: true, go: 'instant', preset: { 'inst-category': category.key } }] });
  }
  if (!plan.some(row => row.level === 'urgent' || row.level === 'warn')) {
    plan.unshift({ key: 'all_good', level: 'good', icon: 'check', metric: String(last7), title: '没有积压，节奏正常',
      detail: `近 7 天完成 ${last7} 次复习，逾期和今日到期都已清空。想加练可以直接挑熟练度最低的几道。`,
      actions: [{ label: '加练几道', primary: true, go: 'instant', preset: {} }] });
  }
  return plan.sort((a, b) => LEVELS[a.level].rank - LEVELS[b.level].rank);
}
