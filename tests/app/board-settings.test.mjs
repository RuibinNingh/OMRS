// 展示板版面设置与锁定保护（assets/app/features/board/settings.js，P7 第 5 步）。
// 与 board-locked.test.mjs 互补：那边在 vm 里真跑旧 board.js 的各入口，这里直接测模块的规范化、确认合并与钩子顺序。
import assert from 'node:assert/strict';
import test from 'node:test';
import { boardNormalizePrint, boardPrintFieldSavesNow, createBoardSettings } from '../../assets/app/features/board/settings.js';

const PRINT = { note_ratio: 0.5, gap_lines: 2, answers: 'none', show_labels: true, show_meta: true, cut_line: 'dash', cut_label: false, locked: false };
function harness({ locked = false, paper = false, confirm = true } = {}) {
  const log = { confirms: 0, dirty: [], flush: 0, relayout: 0, hooks: [] };
  const board = { id: 'B1', print: { ...PRINT, locked }, printed_summary: { pages: paper ? 1 : 0 }, printed: { items: [{ question_id: 'OP-1' }] },
    items: [{ uid: 'A', question_id: 'OP-1', printed: paper, gap_lines: null }, { uid: 'B', question_id: 'OP-2', printed: false, gap_lines: null }] };
  let release;
  const settings = createBoardSettings({
    detail: () => board,
    confirm: () => { log.confirms += 1; return confirm === 'manual' ? new Promise(resolve => { release = resolve; }) : Promise.resolve(confirm); },
    markDirty: kind => log.dirty.push(kind),
    flush: async () => { log.flush += 1; return true; },
    relayout: () => { log.relayout += 1; },
    printApplied: (field, print) => log.hooks.push(['printApplied', field, print[field]]),
    printRejected: () => log.hooks.push(['printRejected']),
    gapApplied: (uid, item, options) => log.hooks.push(['gapApplied', uid, item.gap_lines, options]),
    gapRejected: (uid, item) => log.hooks.push(['gapRejected', uid, item.gap_lines]),
  });
  return { settings, board, log, release: ok => release(ok) };
}

test('字段规范化：钳值、枚举兜底、未知字段与未变化返回 null', () => {
  assert.equal(boardNormalizePrint(PRINT, 'note_ratio', 42).note_ratio, 0.42);
  assert.equal(boardNormalizePrint(PRINT, 'note_ratio', 99).note_ratio, 0.55);
  assert.equal(boardNormalizePrint(PRINT, 'note_ratio', 'x'), null, '非数字回默认 50%，与原值相同即不改');
  assert.equal(boardNormalizePrint(PRINT, 'gap_lines', 99).gap_lines, 24);
  assert.equal(boardNormalizePrint(PRINT, 'gap_lines', 'x'), null, '非数字回默认 2，与原值相同即不改');
  assert.equal(boardNormalizePrint(PRINT, 'answers', 'append').answers, 'append');
  assert.equal(boardNormalizePrint({ ...PRINT, answers: 'append' }, 'answers', 'bogus').answers, 'none');
  assert.equal(boardNormalizePrint(PRINT, 'cut_line', 'wavy'), null, '非法切割线回 dash，与原值相同');
  assert.equal(boardNormalizePrint(PRINT, 'cut_line', 'solid').cut_line, 'solid');
  assert.equal(boardNormalizePrint(PRINT, 'locked', 1).locked, true);
  assert.equal(boardNormalizePrint(PRINT, 'mystery', 1), null);
  assert.equal(boardNormalizePrint(PRINT, 'show_meta', true), null);
  const next = boardNormalizePrint(PRINT, 'show_meta', false);
  assert.notEqual(next, PRINT);
  assert.equal(PRINT.show_meta, true, '不改传入的对象');
  assert.equal(boardPrintFieldSavesNow('answers') && boardPrintFieldSavesNow('show_labels'), true);
  assert.equal(boardPrintFieldSavesNow('note_ratio') || boardPrintFieldSavesNow('show_meta'), false);
});

test('锁定保护：未锁定、无纸面、改动不影响旧纸面都直接放行', async () => {
  assert.equal(await harness({ paper: true }).settings.allow({ print: { ...PRINT, note_ratio: 0.3 } }), true);
  const noPaper = harness({ locked: true });
  assert.equal(await noPaper.settings.allow({ print: { ...PRINT, locked: true, note_ratio: 0.3 } }), true);
  const safe = harness({ locked: true, paper: true });
  assert.equal(await safe.settings.allow({ print: { ...PRINT, locked: true, answers: 'append' } }), true);
  assert.equal(safe.log.confirms + noPaper.log.confirms, 0);
});

test('锁定保护：同一轮输入共用一个确认框；确认后本轮不再问，revoke 后重新问', async () => {
  const h = harness({ locked: true, paper: true, confirm: 'manual' });
  const change = { print: { ...PRINT, locked: true, note_ratio: 0.3 } };
  const first = h.settings.allow(change), second = h.settings.allow(change);
  assert.equal(h.log.confirms, 1);
  h.release(true);
  assert.deepEqual(await Promise.all([first, second]), [true, true]);
  assert.equal(h.settings.granted(), true);
  assert.equal(await h.settings.allow(change), true);
  assert.equal(h.log.confirms, 1);
  h.settings.revoke();
  assert.equal(h.settings.granted(), false);
  const third = h.settings.allow(change);
  assert.equal(h.log.confirms, 2);
  h.release(false);
  assert.equal(await third, false);
  assert.equal(h.settings.granted(), false, '取消不授权');
});

test('正在上锁（本次改动里 locked 变 true）也按锁定判断', async () => {
  const h = harness({ paper: true, confirm: false });
  assert.equal(await h.settings.allow({ print: { ...PRINT, locked: true, note_ratio: 0.3 } }), false);
  assert.equal(h.log.confirms, 1);
});

test('applyPrintField：几何字段记脏并重排；答案开关立即保存；未变化不动；被拒只回钩子', async () => {
  const h = harness();
  assert.equal(await h.settings.applyPrintField('note_ratio', 42), true);
  assert.equal(h.board.print.note_ratio, 0.42);
  assert.deepEqual(h.log.dirty, ['print']);
  assert.equal(h.log.relayout, 1);
  assert.equal(h.log.flush, 0);
  assert.deepEqual(h.log.hooks[0], ['printApplied', 'note_ratio', 0.42]);
  await h.settings.applyPrintField('answers', 'append');
  assert.equal(h.log.flush, 1);
  assert.equal(h.log.relayout, 1);
  assert.equal(await h.settings.applyPrintField('answers', 'append'), false);
  assert.equal(await h.settings.applyPrintField('bogus', 1), false);
  assert.equal(h.log.dirty.length, 2);
  const locked = harness({ locked: true, paper: true, confirm: false });
  assert.equal(await locked.settings.applyPrintField('note_ratio', 30), false);
  assert.equal(locked.board.print.note_ratio, 0.5);
  assert.deepEqual(locked.log.hooks, [['printRejected']]);
  assert.deepEqual(locked.log.dirty, []);
});

test('setItemGap：按 uid 或 question_id 找题，null = 继承、数字钳到 0–48；被拒时不改题', async () => {
  const h = harness();
  assert.equal(await h.settings.setItemGap('nope', 3), null);
  const item = await h.settings.setItemGap('OP-2', 99, { keepFocus: true });
  assert.equal(item.gap_lines, 48);
  assert.deepEqual(h.log.hooks.at(-1), ['gapApplied', 'OP-2', 48, { keepFocus: true }]);
  assert.deepEqual(h.log.dirty, ['items']);
  assert.equal(h.log.relayout, 1);
  assert.equal((await h.settings.setItemGap('B', null)).gap_lines, null);
  const locked = harness({ locked: true, paper: true, confirm: false });
  assert.equal(await locked.settings.setItemGap('A', 9), null);
  assert.equal(locked.board.items[0].gap_lines, null);
  assert.deepEqual(locked.log.hooks, [['gapRejected', 'A', null]]);
  assert.equal(await locked.settings.setItemGap('B', 9) !== null, true, '未印题的留白不受锁定保护');
});
