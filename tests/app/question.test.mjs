// 共享题目视图 domain/question 的纯函数：Markdown 渲染与缓存、练习记录、qview HTML、画廊卡骨架。
// 由 tests/test_md_linebreaks.js、test_question_record_ui.js、test_qview_gallery.js 合并迁入（P5），用例只增不减。
import assert from 'node:assert/strict';
import test from 'node:test';
import {
  renderMd, renderMdUncached, mdLineBreakMode, mdCacheStats, clearMdCache, hashText,
  parseQHistory, qRecordsFromDetail, qHistoryStats, qStreakHtml,
  qvHtml, qvRecordHtml, qvGalleryCard, qvGalleryIdHtml, QV_CARD_OPTS,
} from '../../assets/app/domain/question/index.js';

// ── Markdown：换行模式与段落 ──
const CHOICES = ['下列说法正确的是（　）', 'A. 甲', 'B. 乙', 'C. 丙'].join('\n');

test('blank lines become paragraphs, never a full blank line of <br><br>', () => {
  const html = renderMd('第一段。\n\n第二段。', 'lean');
  assert.equal(html, '<p class="md-p">第一段。</p><p class="md-p">第二段。</p>');
  assert.ok(!html.includes('<br>'));
});

test('consecutive blank lines still collapse into a single paragraph break', () => {
  assert.equal(renderMd('甲\n\n\n\n乙', 'lean'), renderMd('甲\n\n乙', 'lean'));
});

test('full mode keeps ordinary newlines while lean remains an explicit compatibility mode', () => {
  assert.equal(renderMd(CHOICES, 'lean'), '<p class="md-p">下列说法正确的是（　） A. 甲 B. 乙 C. 丙</p>');
  assert.equal(renderMd(CHOICES, 'full'), '<p class="md-p">下列说法正确的是（　）<br>A. 甲<br>B. 乙<br>C. 丙</p>');
});

test('trailing hard break before a blank line does not leak an extra empty line', () => {
  ['lean', 'full'].forEach(mode => {
    assert.equal(renderMd('标题。  \n\n正文。', mode), '<p class="md-p">标题。</p><p class="md-p">正文。</p>');
  });
});

test('a hard break inside a paragraph survives in both modes', () => {
  ['lean', 'full'].forEach(mode => assert.ok(renderMd('甲。  \n乙。', mode).includes('甲。<br>乙。')));
});

test('tables stay their own block with no stray <br> around them', () => {
  const html = renderMd('说明：\n| 项 | 值 |\n| --- | --- |\n| a | 1 |\n结论。', 'full');
  assert.ok(html.startsWith('<p class="md-p">说明：</p><div class="md-table-wrap">'));
  assert.ok(html.endsWith('<p class="md-p">结论。</p>'));
  assert.ok(!html.includes('<br></p>'));
});

test('the default mode preserves ordinary newlines and still treats blank lines as Markdown paragraphs', () => {
  assert.equal(mdLineBreakMode(), 'full');
  assert.equal(renderMd(CHOICES), renderMd(CHOICES, 'full'));
  assert.equal(renderMd('题干\n\nA. 甲\nB. 乙'), '<p class="md-p">题干</p><p class="md-p">A. 甲<br>B. 乙</p>');
});

test('empty input renders nothing at all', () => {
  assert.equal(renderMd(''), '');
  assert.equal(renderMd('\n\n\n'), '');
});

// ── Markdown：内容哈希缓存（P5 新增）──
test('same text renders once per mode; the cached result is identical to a fresh render', () => {
  clearMdCache();
  const text = '缓存题面：\n| a | b |\n| --- | --- |\n| 1 | 2 |';
  const first = renderMd(text, 'lean');
  const second = renderMd(text, 'lean');
  assert.equal(first, second);
  assert.equal(first, renderMdUncached(text, 'lean'));
  assert.deepEqual([mdCacheStats().hits, mdCacheStats().misses], [1, 1]);
  renderMd(text, 'full');                                  // 换行模式是缓存键的一部分
  assert.equal(mdCacheStats().misses, 2);
});

test('math is not cached while KaTeX is missing, so the source fallback never sticks', () => {
  clearMdCache();
  const html = renderMd('求 $x^2$ 的值', 'lean');
  assert.ok(html.includes('<span class="math ">x^2</span>'));
  renderMd('求 $x^2$ 的值', 'lean');
  assert.equal(mdCacheStats().size, 0);
  assert.equal(mdCacheStats().hits, 0);
});

test('hash is stable and distinguishes near-identical texts', () => {
  assert.equal(hashText('二倍角公式'), hashText('二倍角公式'));
  assert.notEqual(hashText('二倍角公式'), hashText('二倍角公式。'));
});

test('images use a class and width attribute, never an inline style', () => {
  const html = renderMd('![[图 1.png|300]] 与 ![说明](sub/图2.png)', 'lean');
  assert.ok(html.includes('class="md-img"'));
  assert.ok(html.includes('width="300"'));
  assert.ok(html.includes('data-omrs-image="图2.png"'));
  assert.ok(!/style=/.test(html));
  assert.ok(renderMd('![[大图.png|9999]]').includes('width="600"'));   // 上限 600 与旧实现一致
});

// ── 练习记录 ──
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
  assert.equal(stats.tailWrong, 2);
  assert.equal(stats.avgGap, 15);
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

test('streak bar height is a data-h level (0–9), not an inline style', () => {
  const html = qStreakHtml([{ date: '2026-01-01', score: 0, correct: false }, { date: '2026-01-02', score: 10, correct: true }]);
  assert.ok(html.includes('data-h="0"'));
  assert.ok(html.includes('data-h="9"'));
  assert.ok(!/style=/.test(html));
});

test('record module reports the losing streak and the newest three rows', () => {
  const html = qvRecordHtml({ history: HISTORY }, { uid: '三角函数7', attempts: 4 });
  assert.ok(html.includes('最近连错 2 次'));
  assert.ok(html.includes('端点没验'));
  assert.ok(html.includes('其余 1 条'));
  assert.ok(html.includes('qv-rec-num bad'));
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

const LEDGER_RECORDS = [
  { log_id: 'C1-001', date: '2026-04-02', time: '20:11', score: 3, correct: false, note: '辅助角公式方向记反', session_id: 'S1' },
  { log_id: 'C2-001', date: '2026-04-09', time: '', score: 6, correct: true, note: '', session_id: 'S2' },
  { log_id: 'C3-001', date: '2026-04-24', time: '21:03', score: 5, correct: false, note: '又漏了定义域', session_id: 'S3' },
];

test('qRecordsFromDetail prefers records[] and reports its source', () => {
  const fromLedger = qRecordsFromDetail({ history: HISTORY, records: LEDGER_RECORDS });
  assert.equal(fromLedger.source, 'ledger');
  assert.equal(fromLedger.length, 3);
  assert.deepEqual({ ...fromLedger[0] }, { date: '2026-04-02', time: '20:11', score: 3, correct: false, note: '辅助角公式方向记反', session_id: 'S1' });
  const fromMarkdown = qRecordsFromDetail({ history: HISTORY });
  assert.equal(fromMarkdown.source, 'markdown');
  assert.equal(fromMarkdown.length, 4);
  assert.equal(qRecordsFromDetail({ history: HISTORY, records: [] }).length, 0);
  assert.equal(qRecordsFromDetail({ records: [{ date: '', score: 5 }, { date: '2026-01-01', score: '99' }] })[0].score, 10);
});

test('empty records[] shows the plain empty state — no stale markdown text', () => {
  const html = qvRecordHtml({ history: '2026 年春天做过一次', records: [] }, { uid: '电解池3', attempts: 2 });
  assert.ok(html.includes('还没练过。'));
  assert.ok(!html.includes('熟练度表'));
  assert.ok(!html.includes('qv-rec-raw'));
});

test('record module is a full-width section after the answer, and opt-out still works', () => {
  const detail = { uid: '三角函数7', question: '题面', answer: '答案', history: HISTORY };
  const withRecord = qvHtml(detail, { uid: '三角函数7' }, {});
  assert.ok(withRecord.indexOf('qv-rec') > withRecord.indexOf('qv-a'));
  assert.ok(!qvHtml(detail, { uid: '三角函数7' }, { showHistory: false }).includes('qv-rec'));
});

test('creation information follows records, renders empty records, and hides in cards', () => {
  const detail = { uid: 'Q-1', question: '题面', answer: '答案', records: [], entry_date: '2026-09-30', created_at: '2026-09-30T01:02:03+00:00' };
  const html = qvHtml(detail, { uid: 'Q-1' }, {});
  assert.ok(html.indexOf('qv-creation') > html.indexOf('qv-rec'));
  assert.ok(html.includes('录入日期') && html.includes('2026-09-30'));
  assert.ok(html.includes('创建时间') && html.includes('2026-09-30 09:02:03'));
  assert.ok(qvHtml({ ...detail, entry_date: '', created_at: '' }, { uid: 'Q-1' }, {}).includes('>—</dd>'));
  assert.ok(!qvHtml(detail, { uid: 'Q-1' }, QV_CARD_OPTS).includes('qv-creation'));
});

// ── qview HTML（P5 新增）──
test('clamp becomes a data-clamp level on the question body, never an inline style', () => {
  const html = qvHtml({ uid: 'Q1', question: '题面' }, { uid: 'Q1' }, QV_CARD_OPTS);
  assert.ok(html.includes('qv-clamp'));
  assert.ok(html.includes('data-clamp="5"'));
  assert.ok(!/style=/.test(html));
  assert.ok(qvHtml({ uid: 'Q1', question: '题面' }, {}, { clamp: 99 }).includes('data-clamp="12"'));
});

test('reveal:false renders no answer DOM, only the reveal button', () => {
  const html = qvHtml({ uid: 'Q1', question: '题', answer: '秘密答案' }, {}, { reveal: false });
  assert.ok(html.includes('data-qv-act="reveal"'));
  assert.ok(!html.includes('秘密答案'));
});

test('fallback detail renders the retry state instead of fake content', () => {
  const html = qvHtml({ uid: 'Q1', _fallback: true, question: '（无法加载题目预览）' }, {}, {});
  assert.ok(html.includes('data-qv-act="retry"'));
  assert.ok(!html.includes('qv-q'));
});

// ── 画廊卡骨架 ──
test('card renders the shared skeleton and drops empty optional slots', () => {
  const html = qvGalleryCard({ uid: 'Q1', previewHtml: '<p>题面</p>' });
  assert.match(html, /class="gallery-card /);
  assert.match(html, /<div class="gallery-head">/);
  assert.match(html, /<div class="gc-foot">/);
  assert.match(html, /data-question-preview-uid="Q1"/);
  assert.match(html, /data-lbl-target="Q1"/);
  assert.match(html, /<p>题面<\/p>/);
  assert.doesNotMatch(html, /gc-meta/);
  assert.doesNotMatch(html, /gc-more/);
});

test('missing preview falls back to the loading placeholder', () => {
  assert.match(qvGalleryCard({ uid: 'Q1' }), /preview-placeholder/);
  assert.match(qvGalleryCard({ uid: 'Q1', previewHtml: '' }), /preview-placeholder/);
});

test('caller-supplied slots land in their documented places', () => {
  const html = qvGalleryCard({
    uid: 'Q2', className: 'bd-gallery-card is-selected', rowAttr: 'data-board-row="Q2"',
    leadHtml: '<span class="bd-gc-no">3</span>', idHtml: '<b>ID</b>', flagsHtml: '<i>已印</i>',
    menuHtml: '<button>⌖</button>', metaHtml: '物理 · 力学', previewClass: 'board-gallery-preview',
    previewHtml: '正文', footHtml: '<span>脚注</span>', labelsHtml: '<em>标记</em>',
  });
  assert.match(html, /class="gallery-card bd-gallery-card is-selected"/);
  assert.match(html, /data-board-row="Q2"/);
  assert.match(html, /<span class="bd-gc-no">3<\/span>\s*<span class="gc-id"><b>ID<\/b><\/span>/);
  assert.match(html, /<span class="gc-flags"><i>已印<\/i><\/span>/);
  assert.match(html, /<span class="gc-more"><button>⌖<\/button><\/span>/);
  assert.match(html, /<div class="gc-meta">物理 · 力学<\/div>/);
  assert.match(html, /class="gallery-preview board-gallery-preview"/);
  assert.match(html, /<span>脚注<\/span>/);
  assert.match(html, /<em>标记<\/em>/);
});

test('uid that repeats its category is split so the prefix stops being noise', () => {
  assert.equal(qvGalleryIdHtml('运动学12', '运动学'), '<span class="gc-cat">运动学</span><span class="gc-num">12</span>');
  assert.equal(qvGalleryIdHtml('运动学-12', '运动学'), '<span class="gc-cat">运动学</span><span class="gc-num">12</span>');
  assert.equal(qvGalleryIdHtml('运动学', '运动学'), '<span class="gc-cat">运动学</span>');
  assert.equal(qvGalleryIdHtml('三角函数1', '代数'), '<span class="gc-num">三角函数1</span>');
  assert.equal(qvGalleryIdHtml('Q1', ''), '<span class="gc-num">Q1</span>');
  assert.equal(qvGalleryIdHtml('', ''), '<span class="gc-num"></span>');
});

test('untrusted text is escaped everywhere the card interpolates a value', () => {
  const html = qvGalleryCard({ uid: '"><img src=x onerror=alert(1)>' });
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&quot;&gt;&lt;img/);
  assert.match(qvGalleryIdHtml('<script>', ''), /&lt;script&gt;/);
  assert.match(qvGalleryIdHtml('<b>x', '<b>'), /<span class="gc-cat">&lt;b&gt;<\/span>/);
});

// 画廊脚注战绩带的两个用例随题库页迁到 tests/app/questions.test.mjs（P5 第 2 轮）。
