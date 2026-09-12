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
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

global.document = { addEventListener() {}, querySelectorAll() { return []; } };
global.asNumber = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback; };
global.clampNumber = (value, min, max, fallback = 0) => Math.max(min, Math.min(max, global.asNumber(value, fallback)));

const BOARD_PATH = path.join(__dirname, '..', 'assets', 'board.js');
const SOURCE = fs.readFileSync(BOARD_PATH, 'utf8');
const { boardStatusModel } = require('../assets/board.js');

/** 取出某个函数的源码（到下一个顶格 function / const 为止），用于静态检查渲染产物。 */
function bodyOf(name) {
  const start = SOURCE.indexOf(`function ${name}(`);
  assert.notEqual(start, -1, `找不到函数 ${name}，重构时改名了就同步这里`);
  const rest = SOURCE.slice(start + 1);
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
  assert.match(model.why, /纸面是最新的/);
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

test('状态机：boardEffectiveMode 与状态条同源，记录完纸面后不会再按「仅新增」导出', () => {
  // 记录纸面后 BOARD_PRINT_MODE 仍是 'new'，但新增数已归零；两处判断若不同源，
  // 状态条写着「打印全部」、导出却拿 mode:'new' 去跑，预览直接报「没有新增题目需要打印」。
  const body = bodyOf('boardEffectiveMode');
  assert.ok(body.includes('boardStatusModel('), 'boardEffectiveMode 必须复用状态机的 scope');
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
  for (const fn of ['boardStageBarHtml', 'boardRowHtml', 'boardGalleryCardHtml', 'boardContentBodyHtml', 'boardGalleryHtml']) {
    const body = bodyOf(fn);
    for (const [needle, label] of forbidden) {
      assert.ok(!body.includes(needle), `${fn} 里出现了${label}（${needle}）：设置属于检查器，不属于舞台`);
    }
  }
});

test('INV-1：翻页条里的数字框是页码跳转，不是设置', () => {
  const body = bodyOf('boardPagerHtml');
  const numbers = body.match(/type="number"/g) || [];
  assert.equal(numbers.length, 1, '翻页条只该有页码跳转这一个数字框');
  assert.ok(body.includes('data-board-page-input'), '页码框要带 data-board-page-input，静态检查靠它把它和设置类输入框区分开');
});

// ---------- INV-2 一个设置只有一个入口 ----------

test('INV-2：题后留白的写入口只有检查器一个', () => {
  // 原来列表行数字框、检视条、拖切割线三处都能改，彼此不可见，改了不同步。
  // 只数「渲染成属性」的那种，不数 [data-board-inspect-gap="..."] 这类查询选择器
  const writers = SOURCE.match(/[^[]data-board-inspect-gap="\$\{escapeAttr/g) || [];
  assert.equal(writers.length, 1, '渲染出的题后留白输入框应当只有一个');
  assert.ok(bodyOf('boardInspectorItemHtml').includes('data-board-inspect-gap="'), '它应当在检查器的「选中的题」一段里');
  assert.ok(!SOURCE.includes('data-board-gap="'), '列表行的旧留白数字框应当已经删掉（现在是 data-board-gap-view 只读回显）');
});

test('INV-2：板级题间留白也只渲染一次，并且和只读回显区分得开', () => {
  assert.equal((SOURCE.match(/data-board-print="gap_lines"/g) || []).length, 1);
  assert.ok(bodyOf('boardInspectorLayoutHtml').includes('data-board-print="gap_lines"'));
  // 只读回显要挂钩子，板级留白一改它们才能跟着刷新
  assert.ok(bodyOf('boardRowHtml').includes('data-board-gap-view='));
  assert.ok(bodyOf('boardGalleryCardHtml').includes('data-board-gap-view='));
  assert.ok(bodyOf('boardRefreshLiveReadouts').includes('data-board-gap-view'));
});

test('INV-2：继承来的留白读数由 boardRefreshLiveReadouts 统一刷新', () => {
  // 板级留白改了，「继承」的单题读数必须跟着变；原型阶段这里错过一次。
  const body = bodyOf('boardRefreshLiveReadouts');
  for (const key of ['item-gap', 'gap-lines', 'col-width']) {
    assert.ok(body.includes(`'${key}'`), `缺少 ${key} 的读数刷新`);
  }
  assert.ok(bodyOf('boardApplyPrintField').includes('boardRefreshLiveReadouts'), '改板级字段后要刷新读数');
});

// ---------- INV-3 状态与行动同处 ----------

test('INV-3：全页只有一个主行动按钮，文案来自状态机', () => {
  assert.equal((SOURCE.match(/data-board-primary/g) || []).length, 1);
  const body = bodyOf('boardStatusbarHtml');
  assert.ok(body.includes('boardStatusModel('), '状态条要直接读状态机，不许另算一套');
  assert.ok(body.includes('data-board-modes'), '打印范围分段在状态条上，不在浮层里');
});

test('版式与打印浮层已经整套移除', () => {
  for (const gone of ['boardSettingsPopHtml', 'boardPopOpen', 'boardPopClose', 'BOARD_POP', 'data-board-pop']) {
    assert.ok(!SOURCE.includes(gone), `${gone} 还在：浮层删干净才算重构完，否则会退回两套入口`);
  }
  const css = fs.readFileSync(path.join(__dirname, '..', 'assets', 'styles.css'), 'utf8');
  assert.ok(!/\.bd-pop[\s.,{:]/.test(css), 'styles.css 里还留着浮层样式');
  const html = fs.readFileSync(path.join(__dirname, '..', 'omrs_dashboard.html'), 'utf8');
  assert.ok(html.includes('id="bd-statusbar"') && html.includes('id="bd-inspector"'), '面板骨架要有状态条与检查器两个常驻节点');
  assert.ok(!html.includes('id="bd-inspect"'), '旧的检视条节点应当已经移除');
});

test('嵌入式预览收起导出模板自带的动作条', () => {
  // 那一条带着「打印 / 导出 PDF」和「已打印，记录纸面」，嵌在舞台里就是第二套入口。
  const preview = fs.readFileSync(path.join(__dirname, '..', 'assets', 'board_preview.js'), 'utf8');
  assert.match(preview, /omrs-board-view[\s\S]{0,200}embedded: true/);
  const template = fs.readFileSync(path.join(__dirname, '..', 'omrs', 'export_templates', 'board.js'), 'utf8');
  assert.ok(template.includes('classList.toggle("embedded"'), '模板要认 embedded 标志');
  const css = fs.readFileSync(path.join(__dirname, '..', 'omrs', 'export_templates', 'board.css'), 'utf8');
  assert.match(css, /body\.embedded #bar\{display:none;\}/);
});
