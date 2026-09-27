/**
 * 展示板三区模型的回归测试。
 *
 * 重构把「状态 / 呈现 / 设置」分到状态条、舞台、检查器三处，靠三条不变量维持：
 *   INV-1 舞台只呈现——舞台渲染出的 HTML 里不出现任何设置控件；
 *   INV-2 一个设置只有一个入口——题后留白只有检查器能写，板级留白只有一个滑/框；
 *   INV-3 状态与行动同处——全页只有一个主行动按钮，文案由状态机决定。
 * 这三条一旦被下一次改动破坏，页面看起来还能用，但「能做什么随视图变」的老毛病会悄悄回来，
 * 所以这里既测纯函数，也对渲染函数的源码做静态检查（与 test_css_collisions.js 同一路数）。
 */
// P7 第 1 步由 tests/test_board_regions.js 迁来，用例原样保留：状态机测 features/board/model.js。P7 第 5 轮起状态条、
// 舞台头与面板骨架改查 features/board/view.js / state.js；第 6 轮旧 assets/board.js 删除，列表 / 画廊与检查器也改查 view.js，
// 「继承读数统一刷新」改为「三处读数同出 state.js 的 gapReadout」（整页 morph 重绘，不再有单独的读数刷新函数）。
import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const __dirname = path.dirname(fileURLToPath(import.meta.url));
import { boardStatusModel } from '../../assets/app/features/board/model.js';

const FEATURE = name => fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'app', 'features', 'board', name), 'utf8');
const VIEW = FEATURE('view.js');
const STATE = FEATURE('state.js');
const DETAIL = FEATURE('detail.js');
const SOURCE = VIEW;

/** 取出某个函数的源码（到下一个顶格 function / const 为止），用于静态检查渲染产物。 */
function bodyOf(name, source = SOURCE) {
  const start = source.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `找不到函数 ${name}，重构时改名了就同步这里`);
  const rest = source.slice(start + 1);
  const next = rest.search(/\n(?:function |const |async function )/);
  return next === -1 ? rest : rest.slice(0, next);
}

const summary = extra => ({ pages: 0, count: 0, new_count: 0, changed_count: 0, ...extra });

// ---------- 打印状态机 ----------

test('状态机：没有纸面记录时提示第一次打印', () => {
  const model = boardStatusModel({ items: [1, 2, 3], printed_summary: summary() }, 'all', null);
  assert.equal(model.action.type, 'preview');
  assert.equal(model.action.label, '🖨 打印全部');
  assert.equal(model.scope, 'all');
  assert.deepEqual(model.chips.map(chip => chip.text), ['还没打印过', '3 题']);
  assert.match(model.why, /记录纸面/);
});

test('状态机：纸面是最新的时候不催打印', () => {
  const model = boardStatusModel({ items: [1], printed_summary: summary({ pages: 2, count: 1 }) }, 'all', null);
  assert.equal(model.action.label, '🖨 打印全部');
  assert.deepEqual(model.chips.map(chip => chip.text), ['已印 1 题 / 2 页']);
  assert.match(model.why, /没有新增题需要补印/);
});

test('状态机：有新增题时，「打印全部」要说清会作废写过的纸', () => {
  const board = { items: new Array(9), printed_summary: summary({ pages: 2, count: 5, new_count: 4, cursor: { page: 2 } }) };
  const all = boardStatusModel(board, 'all', null);
  assert.equal(all.scope, 'all');
  assert.equal(all.action.label, '🖨 打印全部');
  assert.match(all.why, /作废/);
  assert.deepEqual(all.chips.map(chip => chip.text), ['已印 5 题 / 2 页', '新增 4 题未印']);
});

test('状态机：切到「仅新增」时主按钮变成补印，并说明接在第几页', () => {
  const board = { items: new Array(9), printed_summary: summary({ pages: 2, count: 5, new_count: 4, cursor: { page: 2 } }) };
  const model = boardStatusModel(board, 'new', null);
  assert.equal(model.scope, 'new');
  assert.equal(model.action.label, '🖨 补印新增 4 题');
  assert.match(model.why, /第 2 页/);
});

test('状态机：没有新增题时「仅新增」无效，自动落回打印全部', () => {
  const board = { items: new Array(5), printed_summary: summary({ pages: 2, count: 5, new_count: 0 }) };
  assert.equal(boardStatusModel(board, 'new', null).scope, 'all');
  // 没有纸面记录时同理：'new' 不是一个可用的范围
  assert.equal(boardStatusModel({ items: [1], printed_summary: summary() }, 'new', null).scope, 'all');
});

test('状态机：打印过还没记录时，主按钮翻成「记录纸面」', () => {
  const board = { items: new Array(9), printed_summary: summary({ pages: 2, count: 5, new_count: 4, cursor: { page: 2 } }) };
  const model = boardStatusModel(board, 'new', { boardId: 'B1', mode: 'new' });
  assert.equal(model.action.type, 'mark-printed');
  assert.equal(model.action.label, '✓ 记录纸面');
  assert.ok(model.chips.some(chip => chip.kind === 'wait'));
});

test('状态机：effectiveMode 与状态条同源，记录完纸面后不会再按「仅新增」导出', () => {
  // 记录纸面后打印范围仍是 'new'，但新增数已归零；两处判断若不同源，
  // 状态条写着「打印全部」、导出却拿 mode:'new' 去跑，预览直接报「没有新增题目需要打印」。
  // P7 第 6 轮起导出的范围是 detail.js 的 effectiveMode（原 board.js 的 boardEffectiveMode）。
  assert.match(DETAIL, /const effectiveMode = \(\) => boardStatusModel\(/, 'effectiveMode 必须复用状态机的 scope');
  const done = { items: new Array(9), printed_summary: summary({ pages: 3, count: 9, new_count: 0 }) };
  assert.equal(boardStatusModel(done, 'new', null).scope, 'all');
});

test('状态机：正文改过的题在任何状态下都单独挂一个 chip', () => {
  const board = { items: new Array(6), printed_summary: summary({ pages: 1, count: 6, changed_count: 2 }) };
  const chips = boardStatusModel(board, 'all', null).chips;
  assert.ok(chips.some(chip => chip.kind === 'changed' && chip.text === '2 题已改动'));
});

test('状态机：拿到空板 / 空数据也不抛', () => {
  const model = boardStatusModel(null, 'all', null);
  assert.equal(model.scope, 'all');
  assert.deepEqual(model.chips.map(chip => chip.text), ['还没打印过', '0 题']);
});

// ---------- INV-1 舞台只呈现 ----------

test('INV-1：舞台渲染函数里不出现任何设置控件', () => {
  // 视图只决定「怎么看」。设置一旦回到舞台，三个视图的能力就又不一样了。
  const forbidden = [
    ['data-board-print', '板级版式字段'],
    ['type="range"', '滑杆'],
    ['data-board-modes', '打印范围分段'],
    ['data-board-inspect-gap', '题后留白输入框'],
  ];
  for (const [fn, source] of [['stageHead', VIEW], ['rowHtml'], ['galleryCard'], ['contentBody'], ['rowMeta']]) {
    const body = bodyOf(fn, source);
    for (const [needle, label] of forbidden) {
      assert.ok(!body.includes(needle), `${fn} 里出现了${label}（${needle}）：设置属于检查器，不属于舞台`);
    }
  }
});

test('INV-1：翻页条里的数字框是页码跳转，不是设置', () => {
  const body = bodyOf('pager', VIEW);
  const numbers = body.match(/type="number"/g) || [];
  assert.equal(numbers.length, 1, '翻页条只该有页码跳转这一个数字框');
  assert.ok(body.includes('data-board-page-input'), '页码框要带 data-board-page-input，静态检查靠它把它和设置类输入框区分开');
});

// ---------- INV-2 一个设置只有一个入口 ----------

test('INV-2：题后留白的写入口只有检查器一个', () => {
  // 原来列表行数字框、检视条、拖切割线三处都能改，彼此不可见，改了不同步。
  // 只数「渲染成属性」的那种，不数 [data-board-inspect-gap="..."] 这类查询选择器
  const writers = VIEW.match(/[^[]data-board-inspect-gap="\$\{/g) || [];
  assert.equal(writers.length, 1, '渲染出的题后留白输入框应当只有一个');
  assert.ok(bodyOf('inspectorItem').includes('data-board-inspect-gap="'), '它应当在检查器的「选中的题」一段里');
  assert.ok(!VIEW.includes('data-board-gap="'), '列表行的旧留白数字框应当已经删掉（现在是 data-board-gap-view 只读回显）');
});

test('INV-2：板级题间留白也只渲染一次，并且和只读回显区分得开', () => {
  assert.equal((VIEW.match(/data-board-print="gap_lines"/g) || []).length, 1);
  assert.ok(bodyOf('inspectorLayout').includes('data-board-print="gap_lines"'));
  // 只读回显要挂钩子（E2E 与冒烟测试按它找），板级留白一改它们随整页重绘一起变
  assert.ok(bodyOf('rowHtml').includes('data-board-gap-view='));
  assert.ok(bodyOf('galleryCard').includes('data-board-gap-view='));
});

test('INV-2：继承来的留白读数三处同出 gapReadout，改板级字段后整页重绘', () => {
  // 板级留白改了，「继承」的单题读数必须跟着变；原型阶段这里错过一次。现在列表行、画廊卡与检查器的数字都由
  // state.js 的 gapReadout 算，模板只画 r.gap / it.gap，不自己算留白。
  assert.ok(bodyOf('contentView', STATE).includes('gapReadout('), '列表 / 画廊的留白要来自 gapReadout');
  assert.ok(bodyOf('inspectorView', STATE).includes('gapReadout('), '检查器的留白要来自 gapReadout');
  for (const fn of ['rowHtml', 'galleryCard', 'inspectorItem']) {
    assert.ok(!/boardEffectiveGap|gap_lines/.test(bodyOf(fn)), `${fn} 不许自己算留白`);
  }
  for (const key of ['item-gap', 'gap-lines', 'col-width']) assert.ok(VIEW.includes(`data-board-live="${key}"`), `缺少 ${key} 读数`);
  // 写入流程在 features/board/settings.js；改板级字段后的界面刷新是 detail.js 注入的 printApplied 钩子 → changed()（整页重绘）
  assert.match(DETAIL, /printApplied: \(\) => changed\(\)/, '改板级字段后要重绘');
});

// ---------- INV-3 状态与行动同处 ----------

test('INV-3：全页只有一个主行动按钮，文案来自状态机', () => {
  assert.equal((VIEW.match(/data-board-primary/g) || []).length, 1);
  assert.ok(bodyOf('statusBar', VIEW).includes('data-board-primary'), '主行动按钮在状态条上');
  assert.ok(bodyOf('statusView', STATE).includes('boardStatusModel('), '状态条要直接读状态机，不许另算一套');
  assert.ok(bodyOf('statusBar', VIEW).includes('data-board-modes'), '打印范围分段在状态条上，不在浮层里');
});

test('版式与打印浮层已经整套移除', () => {
  for (const gone of ['boardSettingsPopHtml', 'boardPopOpen', 'boardPopClose', 'BOARD_POP', 'data-board-pop']) {
    assert.ok(!SOURCE.includes(gone), `${gone} 还在：浮层删干净才算重构完，否则会退回两套入口`);
  }
  const css = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'styles.css'), 'utf8');
  assert.ok(!/\.bd-pop[\s.,{:]/.test(css), 'styles.css 里还留着浮层样式');
  const html = fs.readFileSync(path.join(__dirname, '..', '..', 'omrs_dashboard.html'), 'utf8');
  const skeleton = bodyOf('view', VIEW);
  assert.ok(skeleton.includes('id="bd-statusbar"') && skeleton.includes('id="bd-inspector"'), '面板骨架要有状态条与检查器两个常驻节点');
  assert.ok(!VIEW.includes('data-board-pop'), '新模板里也不许有浮层');
  assert.ok(!html.includes('id="bd-inspect"'), '旧的检视条节点应当已经移除');
});

test('嵌入式预览收起导出模板自带的动作条', () => {
  // 那一条带着「打印 / 导出 PDF」和「已打印，记录纸面」，嵌在舞台里就是第二套入口。
  const preview = fs.readFileSync(path.join(__dirname, '..', '..', 'assets', 'app', 'features', 'board', 'preview.js'), 'utf8');
  assert.match(preview, /omrs-board-view[\s\S]{0,200}embedded: true/);
  const template = fs.readFileSync(path.join(__dirname, '..', '..', 'omrs', 'export_templates', 'board.js'), 'utf8');
  assert.ok(template.includes('classList.toggle("embedded"'), '模板要认 embedded 标志');
  const css = fs.readFileSync(path.join(__dirname, '..', '..', 'omrs', 'export_templates', 'board.css'), 'utf8');
  assert.match(css, /body\.embedded #bar\{display:none;\}/);
});
