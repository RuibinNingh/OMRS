const assert = require('node:assert/strict');
const test = require('node:test');

global.document = { addEventListener() {}, getElementById() { return null }, querySelectorAll() { return [] }, querySelector() { return null } };
global.localStorage = { getItem() { return null }, setItem() {} };
global.window = {};

const { parseQHistory, qRecordsFromDetail, qHistoryStats, qStreakHtml } = require('../assets/core.js');

// core.js 把工具函数放在全局作用域供后续脚本直接调用；node 下手动补齐这层
global.parseQHistory = parseQHistory;
global.qRecordsFromDetail = qRecordsFromDetail;
global.qHistoryStats = qHistoryStats;
global.qStreakHtml = qStreakHtml;
global.escapeHtml = value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
global.escapeAttr = global.escapeHtml;
global.asNumber = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback };
global.renderMdContent = value => String(value ?? '');
global.getItemByUid = () => ({});
global.getDueDays = () => null;
global.QUESTION_CACHE = {};

const { galleryFootHtml, galleryStreakBodyHtml } = require('../assets/questions.js');
const { qvRecordHtml, qvHtml } = require('../assets/qview.js');

const HISTORY = [
  '2026-04-02 主观:3, 错, 备注:辅助角公式方向记反',
  '2026-04-09 主观:6, 对',
  '2026-04-24 主观:5, 错, 备注:又漏了定义域',
  '2026-05-18 主观:4, 错, 备注:端点没验',
].join('\n');

test('parseQHistory matches the backend parse_history_lines() format', () => {
  const records = parseQHistory(HISTORY);
  assert.equal(records.length, 4);
  assert.deepEqual(records[0], { date: '2026-04-02', score: 3, correct: false, note: '辅助角公式方向记反' });
  assert.deepEqual(records[1], { date: '2026-04-09', score: 6, correct: true, note: '' });
});

test('unparseable and blank lines are dropped, not guessed at', () => {
  assert.deepEqual(parseQHistory(''), []);
  assert.deepEqual(parseQHistory('随手写的一行\n\n2026-01-01 做过了'), []);
  assert.equal(parseQHistory(`乱写\n${HISTORY}`).length, 4);
});

test('qHistoryStats derives count, rate, average score, tail streak and gap', () => {
  const stats = qHistoryStats(parseQHistory(HISTORY));
  assert.equal(stats.count, 4);
  assert.equal(stats.correct, 1);
  assert.equal(stats.rate, 25);
  assert.equal(stats.avgScore, 4.5);
  assert.equal(stats.tailWrong, 2);          // 末尾连错 2 次
  assert.equal(stats.avgGap, 15);            // (7 + 15 + 24) / 3
  assert.equal(stats.last.date, '2026-05-18');
});

test('no records returns only count:0 so callers show the empty state', () => {
  assert.deepEqual(qHistoryStats([]), { count: 0 });
  assert.deepEqual(qHistoryStats(null), { count: 0 });
});

test('streak strip encodes one bar per attempt, capped at max, coloured by correctness', () => {
  const html = qStreakHtml(parseQHistory(HISTORY));
  assert.equal((html.match(/<i /g) || []).length, 4);
  assert.equal((html.match(/class="bad/g) || []).length, 3);
  assert.ok(html.includes('aria-label="最近 4 次'));
  const long = qStreakHtml(Array.from({ length: 20 }, () => ({ date: '2026-01-01', score: 8, correct: true })), 8);
  assert.equal((long.match(/<i /g) || []).length, 8);
  assert.equal(qStreakHtml([]), '');
});

test('record module reports the losing streak and the newest three rows', () => {
  const html = qvRecordHtml({ history: HISTORY }, { uid: '三角函数7', attempts: 4 });
  assert.ok(html.includes('最近连错 2 次'));
  assert.ok(html.includes('端点没验'));
  assert.ok(html.includes('其余 1 条'));           // 4 条 = 首屏 3 + 折叠 1
  assert.ok(html.includes('qv-rec-num bad'));      // 正确率 25% < 60% 标红
});

test('a clean record adds no warning line', () => {
  const clean = ['2026-04-09 主观:8, 对', '2026-05-18 主观:9, 对'].join('\n');
  const html = qvRecordHtml({ history: clean }, { uid: '导数应用2', attempts: 2 });
  assert.ok(!html.includes('连错'));
  assert.ok(!html.includes('qv-rec-num bad'));
  assert.ok(!html.includes('其余'));
});

test('never-practised question gets an empty state, unparseable history is kept verbatim (legacy backend only)', () => {
  assert.ok(qvRecordHtml({ history: '' }, { uid: '电解池3', attempts: 0 }).includes('还没练过'));
  const odd = qvRecordHtml({ history: '2026 年春天做过一次' }, { uid: '电解池3', attempts: 1 });
  assert.ok(odd.includes('qv-rec-raw'));
  assert.ok(odd.includes('2026 年春天做过一次'));
});

// ── v1.16.1：正式记录来自 GET /api/question 的 records[]（Ledger 投影），Markdown # 历史 只是兜底 ──
const LEDGER_RECORDS = [
  { log_id: 'C1-001', date: '2026-04-02', time: '20:11', score: 3, correct: false, note: '辅助角公式方向记反', session_id: 'S1' },
  { log_id: 'C2-001', date: '2026-04-09', time: '', score: 6, correct: true, note: '', session_id: 'S2' },
  { log_id: 'C3-001', date: '2026-04-24', time: '21:03', score: 5, correct: false, note: '又漏了定义域', session_id: 'S3' },
];

test('qRecordsFromDetail prefers records[] and reports its source', () => {
  const fromLedger = qRecordsFromDetail({ history: HISTORY, records: LEDGER_RECORDS });
  assert.equal(fromLedger.source, 'ledger');
  assert.equal(fromLedger.length, 3);                       // 不会把 Markdown 的 4 行混进来
  assert.deepEqual(fromLedger[0], { date: '2026-04-02', time: '20:11', score: 3, correct: false, note: '辅助角公式方向记反', session_id: 'S1' });
  const fromMarkdown = qRecordsFromDetail({ history: HISTORY });
  assert.equal(fromMarkdown.source, 'markdown');
  assert.equal(fromMarkdown.length, 4);
  assert.equal(qRecordsFromDetail({ history: HISTORY, records: [] }).length, 0); // 空数组 = 后端明确说没练过
  assert.equal(qRecordsFromDetail({ records: [{ date: '', score: 5 }, { date: '2026-01-01', score: '99' }] })[0].score, 10);
});

test('empty records[] shows the plain empty state — no "熟练度表记了 N 次" leak, no stale markdown text', () => {
  const html = qvRecordHtml({ history: '2026 年春天做过一次', records: [] }, { uid: '电解池3', attempts: 2 });
  assert.ok(html.includes('还没练过。'));
  assert.ok(!html.includes('熟练度表'));
  assert.ok(!html.includes('qv-rec-raw'));
});

test('ledger records drive the record module and the gallery streak, markdown history is ignored', () => {
  const detail = { history: HISTORY, records: LEDGER_RECORDS };
  const html = qvRecordHtml(detail, { uid: '三角函数7', attempts: 3 });
  assert.ok(html.includes('<b>3</b>'));                    // 练习次数 3，不是 Markdown 的 4
  assert.ok(html.includes('20:11'));                       // 明细行带时间
  assert.ok(!html.includes('端点没验'));                   // Markdown 独有的那条不出现
  const streak = galleryStreakBodyHtml({ uid: '三角函数7', attempts: 3 }, detail);
  assert.equal((streak.match(/<i /g) || []).length, 3);
  assert.ok(streak.includes('3 次'));
});

test('record module is a full-width section after the answer, and opt-out still works', () => {
  const detail = { uid: '三角函数7', question: '题面', answer: '答案', history: HISTORY };
  const withRecord = qvHtml(detail, { uid: '三角函数7' }, {});
  assert.ok(withRecord.indexOf('qv-rec') > withRecord.indexOf('qv-a'));
  assert.ok(!qvHtml(detail, { uid: '三角函数7' }, { showHistory: false }).includes('qv-rec'));
});

test('gallery foot swaps the plain count for a streak slot, filled once the detail lands', () => {
  const item = { uid: '三角函数7', mastery: 0.34, difficulty: 6, attempts: 4 };
  const slot = galleryFootHtml(item);
  assert.ok(slot.includes('gc-streak-slot'));
  assert.ok(slot.includes('4 次'));
  assert.ok(!slot.includes('q-streak'));           // 详情未到时只出占位数字
  const filled = galleryStreakBodyHtml(item, { history: HISTORY });
  assert.ok(filled.includes('q-streak'));
  assert.ok(filled.includes('连错 2'));
  assert.ok(galleryFootHtml({ uid: '电解池3', mastery: 0, difficulty: 5, attempts: 0 }).includes('未练习'));
});
