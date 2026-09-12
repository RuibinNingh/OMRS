// 展示板实时预览的消息协议：几何改动零请求、内容改动才重新导出、iframe 回传能到宿主。
// 这一层几乎全是副作用，所以用最小的 DOM / fetch 替身把 assets/board_preview.js 真跑起来。
const assert = require('node:assert/strict');
const test = require('node:test');

const POSTED = [];          // iframe 收到的 postMessage
const FETCHED = [];         // 真正发出去的 /api/export 请求
let MESSAGE_HANDLER = null; // board_preview.js 注册的 window message 监听

function fakeFrame() {
  return {
    className: '', srcdoc: '', parentNode: null, style: {},
    setAttribute() {}, contentWindow: { postMessage: message => POSTED.push(message) },
  };
}

const FRAME = fakeFrame();
const CONTAINER = { clientWidth: 1000, appendChild(node) { node.parentNode = CONTAINER; } };

global.window = {
  addEventListener(type, handler) { if (type === 'message') MESSAGE_HANDLER = handler; },
};
global.document = {
  createElement: () => FRAME,
  // 预览只在展示板 Tab 前台时排版；测试里恒定「在前台」
  getElementById: id => (id === 'panel-board' ? { classList: { contains: () => true } } : null),
  addEventListener() {}, querySelectorAll() { return []; },
};
global.fetch = async (url, options) => {
  const body = JSON.parse(options.body);
  FETCHED.push(body);
  return { ok: true, text: async () => `<html data-board="${body.board_id}" data-mode="${body.mode}"></html>` };
};

const bp = require('../assets/board_preview.js');

// iframe「排完版了」：board_preview.js 只认来自自己 contentWindow 的消息
function emitLayout(layout) {
  MESSAGE_HANDLER({ source: FRAME.contentWindow, data: { type: 'omrs-board-layout', layout } });
}
const LAYOUT = { board_id: 'B1', mode: 'all', pages: 3, page_numbers: [1, 2, 3] };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

test('mount reuses the single iframe instead of rebuilding it', () => {
  assert.equal(bp.boardPreviewMount(CONTAINER), FRAME);
  assert.equal(bp.boardPreviewMount(CONTAINER), FRAME);   // 重建 = 近 1MB 的字体重解码一次
  assert.equal(bp.boardPreviewMount(null), null);
});

test('content fingerprint ignores print geometry but tracks items and paper time', () => {
  const base = bp.boardPreviewKey('B1', 'all', 'Q1,Q2', '2026-09-09T00:00:00Z');
  assert.equal(bp.boardPreviewKey('B1', 'all', 'Q1,Q2', '2026-09-09T00:00:00Z'), base);
  assert.notEqual(bp.boardPreviewKey('B1', 'all', 'Q1,Q2,Q3', '2026-09-09T00:00:00Z'), base);
  assert.notEqual(bp.boardPreviewKey('B1', 'new', 'Q1,Q2', '2026-09-09T00:00:00Z'), base);
  assert.notEqual(bp.boardPreviewKey('B1', 'all', 'Q1,Q2', ''), base);
  assert.equal(bp.boardPreviewKey('', '', '', ''), '|all||');
});

test('setBoard fetches once per fingerprint; geometry changes never reach the network', async () => {
  FETCHED.length = 0;
  await bp.boardPreviewSetBoard('B1', 'all', { signature: 'Q1,Q2', printedAt: '' });
  emitLayout(LAYOUT);
  assert.equal(FETCHED.length, 1);
  assert.deepEqual(FETCHED[0], { board_id: 'B1', format: 'board', mode: 'all' });
  assert.equal(FRAME.srcdoc, '<html data-board="B1" data-mode="all"></html>');
  assert.equal(bp.boardPreviewIsReady(), true);

  // 同一指纹再来一次：命中缓存，不重新拉那份将近 1MB 的导出
  await bp.boardPreviewSetBoard('B1', 'all', { signature: 'Q1,Q2', printedAt: '' });
  assert.equal(FETCHED.length, 1);

  // 拖版面滑块 → relayout，全程零请求
  POSTED.length = 0;
  bp.boardPreviewRelayout({ note_ratio: .5 }, { Q1: 4 });
  bp.boardPreviewRelayout({ note_ratio: .55, cut_line: 'solid' }, { Q1: 6, Q2: null });
  assert.deepEqual(POSTED, []);                       // 去抖窗口内一条都不发
  await sleep(200);
  assert.equal(FETCHED.length, 1);
  assert.equal(POSTED.length, 1);                     // 连续拖动合并成一次重排
  assert.deepEqual(POSTED[0], {
    type: 'omrs-board-relayout',
    print: { note_ratio: .55, cut_line: 'solid' },
    gaps: { Q1: 6, Q2: null },                        // null 原样传：继承当前全局，不是 0 行
  });
});

test('content change invalidates the fingerprint and re-exports', async () => {
  FETCHED.length = 0;
  await bp.boardPreviewSetBoard('B1', 'all', { signature: 'Q1,Q2,Q3', printedAt: '' });
  emitLayout(LAYOUT);
  assert.equal(FETCHED.length, 1);
  await bp.boardPreviewSetBoard('B1', 'new', { signature: 'Q1,Q2,Q3', printedAt: '' });
  emitLayout({ ...LAYOUT, mode: 'new' });
  assert.equal(FETCHED.length, 2);
  bp.boardPreviewInvalidate();                        // 题目正文单独改过：缓存不能再用
  await bp.boardPreviewSetBoard('B1', 'new', { signature: 'Q1,Q2,Q3', printedAt: '' });
  assert.equal(FETCHED.length, 3);
});

test('goto / step / view speak the documented message protocol', async () => {
  await bp.boardPreviewSetBoard('B1', 'all', { signature: 'paging', printedAt: '' });
  emitLayout(LAYOUT);
  POSTED.length = 0;

  bp.boardPreviewGoto(2);
  bp.boardPreviewGoto('Q7');                          // 非数字 = 跳到某道题
  bp.boardPreviewStep(1);                             // 从第 2 页往后
  bp.boardPreviewStep(99);                            // 越界收敛到末页，不发越界页码
  assert.deepEqual(POSTED.map(m => m.type), Array(4).fill('omrs-board-goto'));
  assert.deepEqual(POSTED.map(m => m.page ?? m.uid), [2, 'Q7', 3, 3]);

  POSTED.length = 0;
  bp.boardPreviewSetView({ single: true, page: 1 });
  assert.deepEqual(POSTED[0], { type: 'omrs-board-view', single: true, page: 1, scale: 1 });
  assert.deepEqual(bp.boardPreviewPages(), [1, 2, 3]);
  assert.equal(bp.boardPreviewView().single, true);
});

test('fit scale is derived from the container width, not from the layout', async () => {
  POSTED.length = 0;
  const scale = bp.boardPreviewScale('fit');          // (1000 - 24) / 793.7 ≈ 1.23
  assert.equal(scale.toFixed(2), '1.23');
  assert.equal(POSTED[0].scale, 1.23);
  assert.equal(bp.boardPreviewScale(1), 1);
});

test('select messages reach the host, and handlers can be registered after load', () => {
  // board.js 排在 board_preview.js 之前，注册必须能晚到；早到的消息不该炸
  MESSAGE_HANDLER({ source: FRAME.contentWindow, data: { type: 'omrs-board-select', uid: '早到' } });
  const seen = [];
  bp.boardPreviewOn({ onSelect: message => seen.push(message.uid) });
  MESSAGE_HANDLER({ source: FRAME.contentWindow, data: { type: 'omrs-board-select', uid: 'Q9', idx: 3, page: 2 } });
  assert.deepEqual(seen, ['Q9']);
  // 打印预览窗口另有链路：不是本 iframe 发的消息一律忽略
  MESSAGE_HANDLER({ source: {}, data: { type: 'omrs-board-select', uid: '别的窗口' } });
  MESSAGE_HANDLER({ source: FRAME.contentWindow, data: null });
  assert.deepEqual(seen, ['Q9']);
});

test('layout callback fires on every layout report and keeps the page in range', async () => {
  const pages = [];
  bp.boardPreviewOn({ onLayout: layout => pages.push(layout?.pages ?? null) });
  await bp.boardPreviewSetBoard('B1', 'all', { signature: 'shrink', printedAt: '' });
  bp.boardPreviewSetView({ page: 3 });
  emitLayout({ ...LAYOUT, pages: 1, page_numbers: [1] });   // 删了两页，当前页号已不存在
  assert.deepEqual(pages, [1]);
  assert.equal(bp.boardPreviewView().page, 1);
});
