// 题库页（assets/app/features/questions）：state.js 纯函数全覆盖 + 列表模板的关键约束。
// 由 tests/test_qtable_ui.js（3 个用例）与 question.test.mjs 里旧 questions.js 画廊脚注（2 个用例）迁入（P5 第 2 轮），用例只增不减。
import assert from 'node:assert/strict';
import test from 'node:test';
import * as S from '../../assets/app/features/questions/state.js';
import { filterItems } from '../../assets/app/domain/items.js';
import { tableView, galleryView, streakFoot } from '../../assets/app/features/questions/list.js';

const base = { text: '', subject: '', category: '', tag: '', knowledgeTag: '', labels: [], labelMode: 'any',
  difficultyMin: 1, difficultyMax: 10, masteryMin: 0, masteryMax: 1, dueFilter: '', suspended: '', sort: 'mastery-asc' };
const memory = (seed = {}) => { const m = new Map(Object.entries(seed)); return { getItem: k => (m.has(k) ? m.get(k) : null), setItem: (k, v) => m.set(k, String(v)), removeItem: k => m.delete(k), map: m }; };

// ── 迁自 tests/test_qtable_ui.js ──
test('sliders at both ends and empty selects count as no filter', () => {
  assert.deepEqual(S.activeFilters(base), []);
  assert.equal(S.filterCount(base), 0);
  assert.deepEqual(S.activeFilters(S.toItemFilters(S.defaultFilters())), []);
});

test('active filters produce one chip per condition with readable labels', () => {
  const active = S.activeFilters({ ...base, subject: '数学', labels: ['考前必看', '压轴'], labelMode: 'all',
    difficultyMin: 3, masteryMax: 0.4, dueFilter: 'overdue', tag: '易错', suspended: 'suspended', text: 'sin' });
  assert.deepEqual(active.map(entry => entry.label || entry.chip), ['搜索：sin', '科目：数学', '考前必看', '压轴', '标记：全部命中', '难度 3–10', '熟练度 0–40%', '到期：逾期', '状态：易错坑', '题目：仅停用题目']);
  assert.equal(S.filterCount({ ...base, labels: ['A'] }), 1);
});

test('default columns keep select/main/actions even if hidden by prefs', () => {
  const columns = S.visibleColumns(null);
  assert.deepEqual([...columns], S.DEFAULT_COLUMNS);
  assert.ok(['select', 'main', 'actions'].every(key => S.visibleColumns(['ef']).has(key)));
  assert.deepEqual(S.toggleColumn(null, 'select', false), S.DEFAULT_COLUMNS);
  assert.deepEqual(S.columnList(S.toggleColumn(null, 'ef', true)).slice(-2), ['ef', 'actions']);
  assert.ok(!S.toggleColumn(null, 'labels', false).includes('labels'));
});

// ── 迁自 question.test.mjs（旧 questions.js 画廊脚注）──
const HISTORY = ['2026-04-02 主观:3, 错, 备注:辅助角公式方向记反', '2026-04-09 主观:6, 对', '2026-04-24 主观:5, 错, 备注:又漏了定义域', '2026-05-18 主观:4, 错, 备注:端点没验'].join('\n');
const LEDGER_RECORDS = [
  { log_id: 'C1-001', date: '2026-04-02', time: '20:11', score: 3, correct: false, note: '辅助角公式方向记反', session_id: 'S1' },
  { log_id: 'C2-001', date: '2026-04-09', time: '', score: 6, correct: true, note: '', session_id: 'S2' },
  { log_id: 'C3-001', date: '2026-04-24', time: '21:03', score: 5, correct: false, note: '又漏了定义域', session_id: 'S3' },
];

test('ledger records drive the gallery streak, markdown history is ignored', () => {
  const foot = streakFoot({ uid: '三角函数7', attempts: 3 }, { history: HISTORY, records: LEDGER_RECORDS });
  assert.equal((foot.streak.match(/<i /g) || []).length, 3);
  assert.equal(foot.text, '3 次');
});

test('gallery foot shows the plain count until the detail lands, then the streak and losing-run warning', () => {
  const item = { uid: '三角函数7', mastery: 0.34, difficulty: 6, attempts: 4 };
  assert.deepEqual(streakFoot(item, null), { text: '4 次' });
  const filled = streakFoot(item, { history: HISTORY });
  assert.ok(filled.streak.includes('q-streak'));
  assert.equal(filled.warn, '连错 2');
  assert.deepEqual(streakFoot(item, { history: HISTORY }, false), { text: '4 次' });
  assert.equal(streakFoot({ uid: 'x', attempts: 0 }, null), null);
  const env = galleryEnv([{ uid: '电解池3', category: '电解池', mastery: 0, difficulty: 5, attempts: 0 }]);
  assert.ok(String(galleryView(env.rows, env)).includes('未练习'));
});

// ── 筛选 ──
test('toItemFilters maps page filters onto the shared filterItems shape', () => {
  const f = { ...S.defaultFilters(), text: '  SIN ', ktag: '诱导公式', diffMin: 3, masteryMax: 40, due: 'today', labels: ['A'], labelMode: 'all' };
  const out = S.toItemFilters(f);
  assert.equal(out.text, 'sin');
  assert.equal(out.knowledgeTag, '诱导公式');
  assert.equal(out.difficultyMin, 3);
  assert.equal(out.masteryMax, 0.4);
  assert.equal(out.dueFilter, 'today');
  assert.deepEqual(out.labels, ['A']);
  assert.equal(out.labelMode, 'all');
  assert.equal(S.toItemFilters(S.withLive(f, { diffMin: 5 })).difficultyMin, 5);
});

test('created date sorting prefers precise time, falls back to entry date, and closes ties by UID', () => {
  const items = [
    { uid: 'b', created_at: '2026-01-02T00:00:00+00:00', entry_date: '2026-01-01', mastery: 0, difficulty: 5 },
    { uid: 'a', created_at: '2026-01-02T00:00:00+00:00', entry_date: '2026-01-01', mastery: 0, difficulty: 5 },
    { uid: 'c', created_at: '', entry_date: '2025-12-31', mastery: 0, difficulty: 5 },
    { uid: 'd', created_at: '', entry_date: '', mastery: 0, difficulty: 5 },
  ];
  const baseFilters = { suspended: '', text: '', subject: '', category: '', tag: '', knowledgeTag: '', labels: [], labelMode: 'any', difficultyMin: 0, difficultyMax: 10, masteryMin: null, masteryMax: null, dueFilter: '' };
  assert.deepEqual(filterItems(items, { ...baseFilters, sort: 'created-asc' }).map(item => item.uid), ['c', 'a', 'b', 'd']);
  assert.deepEqual(filterItems(items, { ...baseFilters, sort: 'created-desc' }).map(item => item.uid), ['a', 'b', 'c', 'd']);
});

test('clearFilter undoes exactly one condition; reset keeps the sort (and optionally the search)', () => {
  const f = { ...S.defaultFilters(), text: 'x', subject: '数学', labels: ['A', 'B'], diffMin: 4, diffMax: 8, masteryMin: 20, due: 'overdue', sort: 'due-asc' };
  assert.deepEqual(S.clearFilter(f, 'label', 'A').labels, ['B']);
  assert.equal(S.clearFilter(f, 'subject').subject, '');
  assert.deepEqual([S.clearFilter(f, 'diff').diffMin, S.clearFilter(f, 'diff').diffMax], [1, 10]);
  assert.equal(S.clearFilter(f, 'mastery').masteryMin, 0);
  assert.equal(S.clearFilter(f, 'due').due, '');
  assert.equal(S.clearFilter(f, 'all').sort, 'due-asc');
  assert.equal(S.clearFilter(f, 'all').text, '');
  assert.equal(S.resetFilters(f, true).text, 'x');
  assert.deepEqual(S.toggleLabel(S.toggleLabel(f, 'C'), 'C').labels, ['A', 'B']);
});

test('dual slider keeps lo ≤ hi by pushing the other end', () => {
  assert.deepEqual(S.rangeValues('diff', 7, 5, 'lo'), { diffMin: 7, diffMax: 7 });
  assert.deepEqual(S.rangeValues('diff', 7, 5, 'hi'), { diffMin: 5, diffMax: 5 });
  assert.deepEqual(S.rangeValues('mastery', -5, 140, 'lo'), { masteryMin: 0, masteryMax: 100 });
});

test('quick filters reset everything but the search, toggle off on a second click, and leech is a post-filter', () => {
  const f = { ...S.defaultFilters(), text: 'sin', subject: '数学' };
  const on = S.applyQuick(f, '', 'overdue');
  assert.equal(on.quick, 'overdue');
  assert.equal(on.filters.due, 'overdue');
  assert.equal(on.filters.subject, '');
  assert.equal(on.filters.text, 'sin');
  assert.equal(S.applyQuick(on.filters, 'overdue', 'overdue').quick, '');
  assert.equal(S.applyQuick(f, '', 'suspended').filters.suspended, 'suspended');
  assert.equal(S.applyQuick(f, '', 'attack').filters.tag, '待攻克');
  assert.deepEqual(S.postFilter([{ uid: 'a', is_leech: true }, { uid: 'b' }], 'leech').map(i => i.uid), ['a']);
  assert.equal(S.quickAfterEdit('leech'), 'leech');
  assert.equal(S.quickAfterEdit('overdue'), '');
});

test('counts ignore suspended questions except the suspended count itself', () => {
  const items = [{ uid: 'a', tag: '待攻克', due: -2 }, { uid: 'b', is_leech: true, due: 3 }, { uid: 'c', suspended: true, is_leech: true, tag: '待攻克', due: -9 }];
  assert.deepEqual(S.countsOf(items, item => item.due), { total: 3, overdue: 1, attack: 1, leech: 1, suspended: 1 });
});

// ── 预设与视图 ──
test('legacy presets (old element ids) replace every filter, so a stale "suspended" filter never leaks through', () => {
  const f = S.filtersFromFields({ 'q-filter-due': 'overdue', 'q-sort': 'due-asc' });
  assert.equal(f.due, 'overdue');
  assert.equal(f.sort, 'due-asc');
  assert.equal(f.suspended, '');
  assert.equal(S.filtersFromFields({ 'q-filter-diff-min': '', 'q-filter-mastery-max': '250', 'q-sort': 'bogus' }).diffMin, 1);
  assert.equal(S.filtersFromFields({ 'q-filter-mastery-max': '250' }).masteryMax, 100);
  assert.equal(S.filtersFromFields({ 'q-sort': 'bogus' }).sort, 'mastery-asc');
});

test('view presets round-trip in the legacy storage format and are recognised as current', () => {
  const filters = { ...S.defaultFilters(), subject: '数学', labels: ['考前必看'], due: 'overdue' };
  const prefs = { ...S.defaultPrefs(), view: 'gallery', density: 'compact', galleryCols: 3, streak: false };
  const snap = S.snapshot(filters, prefs, 'full');
  assert.equal(snap.fields['q-filter-subj'], '数学');
  assert.equal(snap.fields['q-filter-diff-min'], '1');
  const back = S.applySnapshot(JSON.parse(JSON.stringify(snap)), S.defaultPrefs());
  assert.ok(S.sameFilters(back.filters, filters));
  assert.deepEqual([back.prefs.view, back.prefs.density, back.prefs.galleryCols, back.prefs.streak, back.mdMode], ['gallery', 'compact', 3, false, 'full']);
  const views = { 考前: snap, 空: S.snapshot(S.defaultFilters(), prefs) };
  assert.equal(S.currentViewName(views, { ...filters, labels: ['考前必看'] }), '考前');
  assert.equal(S.currentViewName(views, { ...filters, subject: '物理' }), '');
  assert.equal(S.describeView(snap), '数学 · 标记 考前必看 · 逾期');
  assert.equal(S.describeView(views.空), '无筛选条件');
  const store = memory();
  S.writeViews(store, views);
  assert.deepEqual(Object.keys(S.readViews(store)), ['考前', '空']);
  assert.deepEqual(S.readViews(memory({ [S.VIEWS_KEY]: '[1,2]' })), {});
  assert.deepEqual(S.readViews(memory({ [S.VIEWS_KEY]: '{bad' })), {});
});

test('prefs persist under the legacy keys and fall back to defaults on garbage', () => {
  const store = memory({ 'omrs-q-view': 'gallery', 'omrs-qb-density': 'compact', 'omrs-qb-streak': '0', 'omrs-qb-gallery-cols': '9', 'omrs-qb-columns': '["ef","nope"]' });
  const prefs = S.readPrefs(store);
  assert.deepEqual([prefs.view, prefs.density, prefs.streak, prefs.galleryCols, prefs.columns], ['gallery', 'compact', false, 6, ['ef']]);
  assert.deepEqual(S.readPrefs(memory({ 'omrs-qb-columns': '{oops' })), S.defaultPrefs());
  assert.deepEqual(S.readPrefs(null), S.defaultPrefs());
  const out = memory();
  S.writePrefs(out, { ...S.defaultPrefs(), galleryDetail: true });
  assert.equal(out.map.get('omrs-qb-gallery-detail'), '1');
  assert.ok(!out.map.has('omrs-qb-columns'));
  assert.deepEqual(S.resetLayout({ ...prefs }), { ...S.defaultPrefs(), view: 'gallery' });
  assert.deepEqual([S.clampCols('x'), S.clampCols(-3), S.stepCols(0, 1), S.stepCols(0, -1), S.stepCols(1, -1), S.stepCols(6, 1)], [0, 0, 1, 6, 0, 6]);
});

// ── 选择、光标 ──
test('selection state, select-all over the visible rows and cursor movement', () => {
  const sel = new Set(['a', 'z']);
  assert.deepEqual(S.selectionOf(sel, ['a', 'b']), { count: 2, all: false, some: true });
  const all = S.toggleAll(sel, ['a', 'b'], true);
  assert.deepEqual(S.selectionOf(all, ['a', 'b']), { count: 3, all: true, some: false });
  assert.deepEqual([...S.toggleAll(all, ['a', 'b'], false)], ['z']);
  assert.equal(S.moveCursor(['a', 'b', 'c'], '', 1), 'a');
  assert.equal(S.moveCursor(['a', 'b', 'c'], '', -1), 'c');
  assert.equal(S.moveCursor(['a', 'b', 'c'], 'c', 1), 'c');
  assert.equal(S.moveCursor([], 'a', 1), '');
  assert.equal(S.cursorOrFirst(['a', 'b'], 'gone'), 'a');
});

// ── 展示用纯函数 ──
test('due, status, revive, flags and menu items read the item the way the list shows it', () => {
  assert.deepEqual(S.dueInfo(-3), { text: '逾期 3 天', tone: 'overdue' });
  assert.equal(S.dueInfo(0).tone, 'today');
  assert.deepEqual([S.dueInfo(2).tone, S.dueInfo(6).tone, S.dueInfo(20).tone, S.dueInfo(null).tone], ['soon', 'week', 'later', 'none']);
  assert.deepEqual(S.statusOf({ tag: '#状态/已击杀' }), { label: '已击杀', kind: 'kill' });
  assert.equal(S.statusOf({ tag: '易错坑' }).kind, 'trap');
  assert.deepEqual(S.statusOf({ suspended: true, tag: '已击杀' }), { label: '停用', kind: 'suspended' });
  assert.equal(S.statusOf({}).label, '待攻克');
  assert.deepEqual(S.reviveOf({ is_revived: true, kill_count: 2, dormant_days: 45, next_revive_date: '2026-09-01' }), { label: '复燃 ×2', title: '第 2 次击杀后休眠 45 天复燃 · 原定 2026-09-01' });
  assert.equal(S.reviveOf({ is_revived: true, suspended: true }), null);
  assert.deepEqual(S.galleryFlags({ is_leech: true }, -2, false).map(f => f.text), ['逾期 2 天', '顽固']);
  assert.deepEqual(S.galleryFlags({ is_revived: true }, -30, false).map(f => f.text), ['复燃']);
  assert.deepEqual(S.galleryFlags({}, 4, false), []);
  assert.deepEqual(S.galleryFlags({}, 4, true).map(f => f.text), ['4 天后']);
  assert.deepEqual([S.masteryTone(90), S.masteryTone(50), S.masteryTone(10)], ['success', 'warning', 'danger']);
  const clampOf = p => S.galleryCardOpts({ ...S.defaultPrefs(), ...p }).clamp;
  assert.deepEqual([clampOf({}), clampOf({ density: 'compact' }), clampOf({ galleryDetail: true }), clampOf({ galleryDetail: true, density: 'compact' })], [5, 3, 8, 6]);
  assert.ok(S.rowMenuItems({ suspended: true }).some(i => i.value === 'resume'));
  assert.ok(S.rowMenuItems({}).some(i => i.value === 'suspend'));
  assert.ok(S.rowMenuItems({}).find(i => i.value === 'delete').danger);
});

test('batch label dialog values become add / remove / create lists', () => {
  const names = ['A', 'B', 'C'];
  const plan = S.batchLabelPlan({ 'qlb-lbl-add-0': true, 'qlb-lbl-add-2': false, 'qlb-lbl-rm-1': true, 'qlb-lbl-new': ' 新的 ' }, names);
  assert.deepEqual(plan, { add: ['A', '新的'], remove: ['B'], create: '新的' });
  assert.deepEqual(S.batchLabelPlan({ 'qlb-lbl-new': 'A', 'qlb-lbl-rm-0': true }, names), { add: ['A'], remove: [], create: '' });
  assert.deepEqual(S.batchLabelPlan({}, names), { add: [], remove: [], create: '' });
});

// ── 列表模板 ──
function galleryEnv(rows, extra = {}) {
  return { rows, total: rows.length, prefs: S.defaultPrefs(), columns: S.columnList(null), selected: new Set(), cursor: '', sel: { count: 0, all: false, some: false }, dueDays: () => null, detailOf: () => null, ...extra };
}

test('table rows carry data-label for the narrow-screen card list, escape text and never write style=', () => {
  const rows = [{ uid: '<b>x</b>', subject: '数学', category: '函数', mastery: 0.5, labels: [], tag: '待攻克' }];
  const env = galleryEnv(rows, { selected: new Set(['<b>x</b>']), cursor: '<b>x</b>' });
  const out = String(tableView(rows, env));
  assert.ok(out.includes('data-label="熟练度"'));
  assert.ok(out.includes('&lt;b&gt;x&lt;/b&gt;'));
  assert.ok(!out.includes('<b>x</b>'));
  assert.ok(!/\sstyle=/.test(out));
  assert.ok(out.includes('aria-selected="true"') && out.includes('data-cursor="1"'));
  assert.ok(out.includes('checked'));
  const none = String(tableView([], galleryEnv([], { total: 3 })));
  assert.ok(none.includes('没有匹配的题目') && none.includes('questions.clearAll'));
  assert.ok(String(tableView([], galleryEnv([]))).includes('题库里还没有题目'));
});

test('gallery preview hosts are morph-skipped and keyed by uid + clamp, so density changes remount them', () => {
  const rows = [{ uid: '数列3', category: '数列', mastery: 0.2, attempts: 2 }];
  const comfy = String(galleryView(rows, galleryEnv(rows)));
  const compact = String(galleryView(rows, galleryEnv(rows, { prefs: { ...S.defaultPrefs(), density: 'compact' } })));
  assert.ok(comfy.includes('data-morph="skip"') && comfy.includes('data-key="pv:数列3:5"'));
  assert.ok(compact.includes('data-key="pv:数列3:3"'));
  assert.ok(!/\sstyle=/.test(comfy));
  assert.ok(comfy.includes('data-cols="auto"'));
});
