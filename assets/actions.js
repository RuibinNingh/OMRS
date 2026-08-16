// === assets/actions.js — 行动推荐：把统计数据翻译成「现在该做什么」 ===
// 纯前端派生模块。数据来自已经加载好的 DATA（/api/stats）与 SESSIONS（/api/sessions），
// 不新增接口、不写 Ledger。刷新时机跟着 renderDash()，所以和仪表盘看到的是同一份快照。

let ACTION_PLAN = [];
let ACTION_SHOW_ALL = false;

const ACTION_LEVEL_META = {
  urgent: { label: '紧急', rank: 0 },
  warn: { label: '建议', rank: 1 },
  info: { label: '可选', rank: 2 },
  good: { label: '状态良好', rank: 3 },
};

// ── 跳转辅助：带着筛选条件落到能立刻动手的页面 ──
function actionResetQuestionFilters() {
  const ids = ['q-search', 'q-filter-subj', 'q-filter-category', 'q-filter-tag', 'q-filter-ktag',
    'q-filter-diff-min', 'q-filter-diff-max', 'q-filter-mastery-min', 'q-filter-mastery-max', 'q-filter-due'];
  ids.forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  const sort = document.getElementById('q-sort');
  if (sort) sort.value = 'mastery-asc';
}
function actionGoQuestions(preset) {
  actionResetQuestionFilters();
  Object.entries(preset || {}).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  });
  switchTab('questions');
  if (typeof renderQ === 'function') renderQ();
}
function actionGoInstant(preset) {
  ['inst-subject', 'inst-category', 'inst-ktag'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  Object.entries(preset || {}).forEach(([id, value]) => {
    const el = document.getElementById(id);
    if (el) el.value = value;
  });
  switchTab('instant');
  if (typeof instLoadPractice === 'function') instLoadPractice();
}
function actionGoReview() {
  switchTab('schedule');
  if (typeof showRecommendPanel === 'function') showRecommendPanel();
}
function actionGoFeedback(sessionId) {
  if (sessionId && typeof feedbackSession === 'function') { feedbackSession(sessionId); return; }
  switchTab('feedback');
}

// ── 派生指标 ──
function actionActiveItems() {
  return getItems().filter(item => !isKilledItem(item));
}
function actionRecentReviewCount(days) {
  const trend = DATA?.daily_trend || {};
  const today = new Date();
  let sum = 0;
  for (let offset = 0; offset < days; offset++) {
    const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() - offset);
    const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    sum += asNumber(trend[key], 0);
  }
  return sum;
}
function actionDaysSinceLastReview() {
  const trend = DATA?.daily_trend || {};
  const keys = Object.keys(trend).filter(key => asNumber(trend[key], 0) > 0).sort();
  if (!keys.length) return null;
  return daysSinceReview(keys[keys.length - 1], 0);
}
// 按维度找最薄弱的一组（题量够多才有参考价值，否则一两道题就能把均值拉到底）
function actionWeakestGroup(items, field, minCount) {
  const groups = {};
  items.forEach(item => {
    const key = (item[field] || '').trim();
    if (!key) return;
    if (!groups[key]) groups[key] = { key, count: 0, sum: 0 };
    groups[key].count += 1;
    groups[key].sum += asNumber(item.decayed_mastery, asNumber(item.mastery, 0));
  });
  const rows = Object.values(groups)
    .filter(row => row.count >= minCount)
    .map(row => ({ ...row, avg: row.sum / row.count }))
    .sort((a, b) => a.avg - b.avg);
  return rows.length > 1 ? rows[0] : null;
}

// ── 规则集：每条规则返回一条建议或 null ──
function buildActionPlan() {
  const items = getItems();
  const active = actionActiveItems();
  const alert = DATA?.review_alert || {};
  const plan = [];
  const push = (row) => { if (row) plan.push(row); };

  if (!items.length) {
    return [{
      key: 'empty', level: 'info', icon: '＋', metric: '0',
      title: '题库还是空的',
      detail: '先录入几道错题，推荐、调度和复盘才有东西可算。',
      actions: [{ label: '去录入题目', primary: true, run: () => switchTab('create') }],
    }];
  }

  // 1. 逾期：最该先清的一批
  const overdue = active.filter(item => { const d = getDueDays(item); return d !== null && d < 0; });
  if (overdue.length) {
    const worst = Math.max(...overdue.map(item => Math.abs(getDueDays(item))));
    push({
      key: 'overdue', level: 'urgent', icon: '!', metric: String(overdue.length),
      title: `${overdue.length} 道题已经逾期`,
      detail: `最久的一道逾期 ${worst} 天。逾期越久衰减越多，先清这批的收益最高。`,
      actions: [
        { label: '立刻练逾期题', primary: true, run: () => actionGoInstant({}) },
        { label: '在题库查看', run: () => actionGoQuestions({ 'q-filter-due': 'overdue', 'q-sort': 'due-asc' }) },
      ],
    });
  }

  // 2. 今日到期
  const dueToday = active.filter(item => getDueDays(item) === 0);
  if (dueToday.length) {
    push({
      key: 'due_today', level: 'warn', icon: '◷', metric: String(dueToday.length),
      title: `今天有 ${dueToday.length} 道题到期`,
      detail: '按 SM-2 排的今日份，今天做完就能把间隔顺延到下一档。',
      actions: [
        { label: '开始常规复习', primary: true, run: actionGoReview },
        { label: '查看清单', run: () => actionGoQuestions({ 'q-filter-due': 'today', 'q-sort': 'mastery-asc' }) },
      ],
    });
  }

  // 3. 有 Session 做完了没反馈——不反馈就不进算法，等于白做
  const pending = (SESSIONS || []).filter(session => (session.status || 'active') === 'active');
  if (pending.length) {
    const first = pending[0];
    const totalQuestions = pending.reduce((sum, session) => sum + asNumber(session.count, 0), 0);
    push({
      key: 'pending_feedback', level: 'warn', icon: '✓', metric: String(pending.length),
      title: `${pending.length} 个 Session 还没录反馈`,
      detail: `共 ${totalQuestions} 道题。没有反馈就不会更新熟练度和到期日，练了也不算数。`,
      actions: [{ label: '去录反馈', primary: true, run: () => actionGoFeedback(first.session_id) }],
    });
  }

  // 4. 顽固题：反复错，靠再刷一遍通常没用，要换方法
  const leeches = items.filter(item => item.is_leech);
  if (leeches.length) {
    push({
      key: 'leech', level: 'urgent', icon: '⟳', metric: String(leeches.length),
      title: `${leeches.length} 道顽固题卡住了`,
      detail: '这些题错的次数明显偏多。与其再刷一遍，不如回去补前置知识点，或者把解法重新拆一遍写进错因。',
      actions: [
        { label: '看顽固题清单', primary: true, run: () => switchTab('data') },
        { label: '按熟练度排题库', run: () => actionGoQuestions({ 'q-sort': 'mastery-asc' }) },
      ],
    });
  }

  // 5. 录进来就没练过
  const untouched = active.filter(item => asNumber(item.attempts, 0) === 0);
  if (untouched.length >= 3) {
    push({
      key: 'untouched', level: 'info', icon: '○', metric: String(untouched.length),
      title: `${untouched.length} 道题录入后一次都没练`,
      detail: '没有一次反馈，算法就没有起点，这些题不会主动出现在推荐里。',
      actions: [{ label: '挑出来练一轮', primary: true, run: () => actionGoQuestions({ 'q-sort': 'date-desc' }) }],
    });
  }

  // 6. 长期冷落
  const cold = active.filter(item => item.last_review && daysSinceReview(item.last_review, 0) > 30);
  if (cold.length >= 3) {
    push({
      key: 'cold', level: 'warn', icon: '❄', metric: String(cold.length),
      title: `${cold.length} 道题超过 30 天没碰`,
      detail: '衰减公式下这批题的实际掌握度已经掉了一大截，即使标记是已掌握也不一定还在。',
      actions: [{ label: '按最近复习排序', primary: true, run: () => actionGoQuestions({ 'q-sort': 'date-desc' }) }],
    });
  }

  // 7. 最近有没有在练
  const last7 = actionRecentReviewCount(7);
  const idleDays = actionDaysSinceLastReview();
  if (idleDays !== null && idleDays >= 3) {
    push({
      key: 'idle', level: idleDays >= 7 ? 'warn' : 'info', icon: '…', metric: `${idleDays}天`,
      title: `已经 ${idleDays} 天没有练习记录`,
      detail: '断得越久，回来时到期队列越长。先做 5 道，把手感和队列一起找回来。',
      actions: [{ label: '做 5 道找回手感', primary: true, run: () => actionGoInstant({ 'inst-count': '5' }) }],
    });
  } else if (last7 === 0 && idleDays === null) {
    push({
      key: 'never', level: 'info', icon: '▶', metric: '0',
      title: '还没有任何练习记录',
      detail: '录完题之后练一轮，熟练度、EF 和到期日才会开始跑。',
      actions: [{ label: '开始第一轮练习', primary: true, run: () => actionGoInstant({}) }],
    });
  }

  // 8. 未到期但已经掉下来的
  const lowNotDue = active.filter(item => {
    const d = getDueDays(item);
    return d !== null && d > 0 && asNumber(item.decayed_mastery, 1) < 0.5;
  });
  if (lowNotDue.length >= 3) {
    push({
      key: 'low_not_due', level: 'info', icon: '↓', metric: String(lowNotDue.length),
      title: `${lowNotDue.length} 道题没到期但已经掉到一半以下`,
      detail: '排期还没轮到，衰减后的熟练度却已经低于 50%。有余力时可以提前捞一遍。',
      actions: [{ label: '按衰减挑题', primary: true, run: () => actionGoQuestions({ 'q-filter-due': 'future', 'q-sort': 'mastery-asc' }) }],
    });
  }

  // 9/10. 最薄弱的科目与分类
  const weakSubject = actionWeakestGroup(active, 'subject', 3);
  if (weakSubject && weakSubject.avg < 0.55) {
    push({
      key: 'weak_subject', level: 'info', icon: '◆', metric: `${(weakSubject.avg * 100).toFixed(0)}%`,
      title: `${weakSubject.key} 是目前最薄弱的科目`,
      detail: `${weakSubject.count} 道未击杀题，衰减后平均熟练度 ${(weakSubject.avg * 100).toFixed(0)}%，明显落后于其他科目。`,
      actions: [
        { label: `专练 ${weakSubject.key}`, primary: true, run: () => actionGoInstant({ 'inst-subject': weakSubject.key }) },
        { label: '看该科目题目', run: () => actionGoQuestions({ 'q-filter-subj': weakSubject.key }) },
      ],
    });
  }
  const weakCategory = actionWeakestGroup(active, 'category', 3);
  if (weakCategory && weakCategory.avg < 0.45) {
    push({
      key: 'weak_category', level: 'info', icon: '◇', metric: `${(weakCategory.avg * 100).toFixed(0)}%`,
      title: `分类「${weakCategory.key}」整体偏低`,
      detail: `${weakCategory.count} 道题，衰减后平均 ${(weakCategory.avg * 100).toFixed(0)}%。整块偏低往往是知识点没通，不是手生。`,
      actions: [{ label: '专练这一类', primary: true, run: () => actionGoInstant({ 'inst-category': weakCategory.key }) }],
    });
  }

  // 11. 都清完了就说清完了，不硬凑建议
  if (!plan.some(row => row.level === 'urgent' || row.level === 'warn')) {
    plan.unshift({
      key: 'all_good', level: 'good', icon: '✓', metric: `${last7}`,
      title: '没有积压，节奏正常',
      detail: `近 7 天完成 ${last7} 次复习，逾期和今日到期都已清空。想加练可以直接挑熟练度最低的几道。`,
      actions: [{ label: '加练几道', primary: true, run: () => actionGoInstant({}) }],
    });
  }

  return plan.sort((a, b) => ACTION_LEVEL_META[a.level].rank - ACTION_LEVEL_META[b.level].rank);
}

// ── 渲染 ──
function actionTodayTarget() {
  const active = actionActiveItems();
  const due = active.filter(item => { const d = getDueDays(item); return d !== null && d <= 0; }).length;
  const leech = active.filter(item => item.is_leech).length;
  return Math.min(20, due + Math.min(3, leech));
}
function renderActionPlan() {
  const box = document.getElementById('action-plan');
  if (!box) return;
  ACTION_PLAN = buildActionPlan();
  const target = actionTodayTarget();
  const visible = ACTION_SHOW_ALL ? ACTION_PLAN : ACTION_PLAN.slice(0, 4);
  const hidden = ACTION_PLAN.length - visible.length;

  const rows = visible.map((row, index) => {
    const buttons = (row.actions || []).map((action, order) =>
      `<button class="btn sm${action.primary ? ' primary' : ''}" onclick="runActionPlanItem(${index},${order})">${escapeHtml(action.label)}</button>`
    ).join('');
    return `<div class="act-item lv-${row.level}">
      <div class="act-rail"></div>
      <div class="act-icon">${escapeHtml(row.icon || '·')}</div>
      <div class="act-body">
        <div class="act-title">${escapeHtml(row.title)}<span class="act-level">${ACTION_LEVEL_META[row.level].label}</span></div>
        <div class="act-detail">${escapeHtml(row.detail)}</div>
      </div>
      <div class="act-metric">${escapeHtml(row.metric || '')}</div>
      <div class="act-buttons">${buttons}</div>
    </div>`;
  }).join('');

  const more = hidden > 0
    ? `<button class="btn sm act-more" onclick="toggleActionPlanAll()">还有 ${hidden} 条建议，展开 ↓</button>`
    : (ACTION_SHOW_ALL && ACTION_PLAN.length > 4
      ? '<button class="btn sm act-more" onclick="toggleActionPlanAll()">收起 ↑</button>' : '');

  box.innerHTML = `<div class="act-head">
      <div>
        <div class="card-title" style="margin-bottom:2px">行动推荐</div>
        <div class="act-sub">按当前题库状态排出的优先级，从上往下做就行。</div>
      </div>
      <div class="act-target"><span class="act-target-num">${target}</span><span class="act-target-label">建议今天练</span></div>
    </div>
    <div class="act-list">${rows}</div>${more}`;
}
function runActionPlanItem(index, order) {
  const action = ACTION_PLAN?.[index]?.actions?.[order];
  if (action && typeof action.run === 'function') action.run();
}
function toggleActionPlanAll() {
  ACTION_SHOW_ALL = !ACTION_SHOW_ALL;
  renderActionPlan();
}
