/**
 * 即时练习：状态与纯逻辑（不碰 DOM、不碰旧全局，由 tests/app/instant.test.mjs 在 node 里覆盖）。
 * 状态是模块单例：离开页面再回来，队列、判定与筛选都还在（与迁移前一致）。
 *
 * 流程：/api/recommend 取到期与熟练度两个列表 → 按全站筛选语义过滤 → 合并去重、截到题数 → 逐题翻答案、判对错、打分
 * → 「提交」把已判定未提交的题发给 /api/feedback（session_id 为 IMM-时间戳，不建调度 Session）。
 * 已提交的题锁定：不能再改判定，也不会被下一次提交重复发送。
 */
export const COUNT_MIN = 1;
export const COUNT_MAX = 50;
export const COUNT_DEFAULT = 10;

/** 仪表盘等旧入口传来的预设沿用旧元素 id 作键（'inst-subject' 等），这里翻成筛选字段。 */
const PRESET_FIELDS = {
  'inst-subject': 'subject', 'inst-category': 'category', 'inst-ktag': 'ktag', 'inst-count': 'count',
  subject: 'subject', category: 'category', ktag: 'ktag', count: 'count',
};

export function createState() {
  return {
    filters: { subject: '', category: '', ktag: '', labels: [], labelMode: 'any', count: COUNT_DEFAULT },
    phase: 'idle', // idle | loading（超过 300ms 才进入，显示骨架屏）| ready | empty | error
    loading: false, // 取题请求进行中（按钮加载态）
    error: '',
    queue: [], // 推荐条目 + _source（'due' | 'proficiency'）
    index: 0,
    results: {}, // uid → { revealed, correct: true | false | null, score: 0–10 | null, submitted }
    sessionId: '',
    submitting: false,
    submitError: '',
    lastSubmit: [], // /api/feedback 的 results
    cardId: '', attemptId: '', cardTitle: '', unavailable: [], chatDeleted: false, progressSeq: 0,
    roundVersion: 0,
  };
}

export const state = createState();

export function clampCount(value) {
  const n = Math.floor(Number(value));
  return Number.isFinite(n) ? Math.min(COUNT_MAX, Math.max(COUNT_MIN, n)) : COUNT_DEFAULT;
}

export function buildParams(filters) {
  const count = String(clampCount(filters.count));
  const params = new URLSearchParams({ due_count: count, prof_count: count });
  if (filters.subject) params.set('subject', filters.subject);
  if (filters.category) params.set('category', filters.category);
  if (filters.ktag) params.set('knowledge_tag', filters.ktag);
  (filters.labels || []).forEach(label => params.append('label', label));
  return params;
}

/** 到期列表在前、熟练度列表在后，按 uid 去重，截到 count 道。 */
export function mergeRecommendations({ due = [], proficiency = [] } = {}, count = COUNT_DEFAULT) {
  const rows = [];
  const seen = new Set();
  const add = (items, source) => (items || []).forEach(item => {
    if (!item?.uid || seen.has(item.uid)) return;
    seen.add(item.uid);
    rows.push({ ...item, _source: source });
  });
  add(due, 'due');
  add(proficiency, 'proficiency');
  return rows.slice(0, clampCount(count));
}

/** 预设：先清空科目 / 分类 / 知识点（标记与题数不动），再套上预设里给出的字段。 */
export function applyPreset(filters, preset = {}) {
  const next = { ...filters, subject: '', category: '', ktag: '' };
  Object.entries(preset || {}).forEach(([key, value]) => {
    const field = PRESET_FIELDS[key];
    if (!field) return;
    next[field] = field === 'count' ? clampCount(value) : String(value ?? '');
  });
  return next;
}

export function sessionId(date = new Date()) {
  const p = n => String(n).padStart(2, '0');
  return `IMM-${date.getFullYear()}${p(date.getMonth() + 1)}${p(date.getDate())}${p(date.getHours())}${p(date.getMinutes())}${p(date.getSeconds())}`;
}

export const defaultScore = correct => (correct ? 8 : 4);
export const isJudged = row => !!row && (row.correct === true || row.correct === false);

export function resultOf(s, uid) {
  if (!s.results[uid]) s.results[uid] = { revealed: false, correct: null, score: null, submitted: false };
  return s.results[uid];
}

export const currentItem = s => s.queue[s.index] || null;

export function counts(s) {
  let judged = 0;
  let submitted = 0;
  s.queue.forEach(item => {
    const row = s.results[item.uid];
    if (isJudged(row) || row?.submitted) judged += 1;
    if (row?.submitted) submitted += 1;
  });
  return { total: s.queue.length, judged, submitted, pending: judged - submitted };
}

/** 从 index 的下一题起循环找第一道「没判定、也没提交」的题；没有返回 -1。 */
export function nextOpenIndex(queue, results, index) {
  for (let step = 1; step <= queue.length; step += 1) {
    const i = (index + step) % queue.length;
    const row = results[queue[i].uid];
    if (!isJudged(row) && !row?.submitted) return i;
  }
  return -1;
}

export function reveal(s, uid) { resultOf(s, uid).revealed = true; }

/** 判对错：顺带翻开答案；用户还没打过分时，对给 8 分、错给 4 分。已提交的题不改，返回 false。 */
export function setVerdict(s, uid, correct) {
  const row = resultOf(s, uid);
  if (row.submitted) return false;
  row.revealed = true;
  row.correct = !!correct;
  if (row.score == null) row.score = defaultScore(row.correct);
  return true;
}

export function setScore(s, uid, value) {
  const row = resultOf(s, uid);
  if (row.submitted) return false;
  const n = Math.round(Number(value));
  row.score = Number.isFinite(n) ? Math.max(0, Math.min(10, n)) : 5;
  return true;
}

/** 待提交的反馈行：已判定、未提交，按队列顺序。 */
export function submitRows(s) {
  return s.queue.filter(item => {
    const row = s.results[item.uid];
    return isJudged(row) && !row.submitted;
  }).map(item => {
    const row = s.results[item.uid];
    return {
      ...(item.question_id ? { question_id: item.question_id } : { uid: item.uid }),
      ...(s.attemptId ? { entry_id: item.question_id } : {}),
      sub_score: row.score == null ? defaultScore(row.correct) : row.score,
      is_correct: row.correct,
      source: item._source || 'due',
      note: '即时练习',
    };
  });
}

export function markSubmitted(s, rows) {
  rows.forEach(row => {
    if (row.status && row.status !== 'ok') return;
    const item = s.queue.find(i => row.question_id && i.question_id === row.question_id) || s.queue.find(i => i.uid === row.uid);
    if (item) resultOf(s, item.uid).submitted = true;
  });
}

/** 开始一轮新的练习（载入新队列）。 */
export function startRound(s, queue, now = new Date()) {
  s.roundVersion = (s.roundVersion || 0) + 1;
  s.submitting = false;
  s.queue = queue;
  s.index = 0;
  s.results = {};
  s.sessionId = sessionId(now);
  s.cardId = ''; s.attemptId = ''; s.cardTitle = ''; s.unavailable = []; s.chatDeleted = false;
  s.submitError = '';
  s.lastSubmit = [];
  s.error = '';
  s.phase = queue.length ? 'ready' : 'empty';
}

export function startPractice(s, data) {
  startRound(s, data.items || []);
  s.cardId = data.card?.card_id || '';
  s.cardTitle = data.card?.title || '';
  s.attemptId = data.attempt_id || '';
  s.sessionId = data.session_id || '';
  s.unavailable = data.unavailable || [];
  s.chatDeleted = !!data.deleted;
  const saved = data.progress?.results || {};
  s.results = Object.fromEntries(s.queue.map(item => [item.uid, saved[item.question_id] || saved[item.uid] || {}]));
  s.progressSeq = Number(data.progress?.seq) || 0;
  s.index = Math.min(Math.max(0, Number(data.progress?.index) || 0), Math.max(0, s.queue.length - 1));
  for (const item of s.queue) {
    resultOf(s, item.uid).submitted = (data.submitted || []).includes(item.question_id);
  }
  s.phase = s.queue.length ? 'ready' : 'empty';
}
