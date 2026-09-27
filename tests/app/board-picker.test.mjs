// 选板浮层（P7 第 4 轮原生，assets/app/domain/board/picker*.js）：行模型与点击决策（model.js）、模板（picker-view.js），
// 以及不需要 DOM 的控制器路径（Shift 直接加入、一个板都没有时直接新建）。浮层挂载、键盘与点外面关闭见 tests/e2e/board_picker.py。
import assert from 'node:assert/strict';
import test from 'node:test';
import * as domain from '../../assets/app/domain/board/model.js';
import * as view from '../../assets/app/domain/board/picker-view.js';
import * as picker from '../../assets/app/domain/board/picker.js';

const boards = [
  { id: 'b1', name: '三角', folder_id: 'f1', order: 0, count: 2, uids: ['Q1', 'Q2'], updated_at: '2026-09-01' },
  { id: 'b2', name: '数列', folder_id: 'f1', order: 1, count: 1, uids: ['Q3'], updated_at: '2026-09-03', printed_summary: { pages: 2 } },
  { id: 'b3', name: '散题', folder_id: '', order: 0, count: 0, uids: [], missing: 1, updated_at: '2026-09-02' },
];
const folders = [{ id: 'f1', name: '高三', order: 0 }];

test('picker items：有文件夹时带组标题，未归档在最后；key 带分区前缀', () => {
  const model = domain.boardPickerItems({ boards, folders, uids: ['Q1'] });
  assert.deepEqual(model.items.map(item => item.key), ['g:f1', 'b:b1', 'b:b2', 'g:~unfiled', 'b:b3']);
  assert.equal(model.rows.length, 3);
  assert.equal(model.items[3].plain, true);
  assert.equal(model.rows[0].state.kind, 'full');
  assert.equal(model.empty, '');
});

test('picker items：没有文件夹时不显示组标题；折叠的文件夹只留标题', () => {
  const flat = domain.boardPickerItems({ boards: boards.map(b => ({ ...b, folder_id: '' })), folders: [], uids: ['Q9'] });
  assert.ok(flat.items.every(item => item.type === 'row'));
  const folded = domain.boardPickerItems({ boards, folders, uids: ['Q9'], collapsed: new Set(['f1']) });
  assert.deepEqual(folded.items.map(item => item.key), ['g:f1', 'g:~unfiled', 'b:b3']);
  assert.equal(folded.items[0].folded, true);
});

test('picker items：板多于 6 个时才有「最近」，同一个板在「最近」与组里 key 不同', () => {
  const many = Array.from({ length: 7 }, (_, i) => ({ id: `m${i}`, name: `板${i}`, folder_id: '', order: i, uids: [], updated_at: `2026-09-0${i + 1}` }));
  const model = domain.boardPickerItems({ boards: many, folders: [], uids: ['Q1'], lastId: 'm2' });
  assert.deepEqual(model.items.slice(0, 3).map(item => item.key), ['g:~recent', 'r:m2', 'r:m6']);
  assert.ok(model.items.some(item => item.key === 'b:m2'));
  assert.equal(domain.boardPickerItems({ boards: many.slice(0, 6), folders: [], uids: ['Q1'] }).items[0].key, 'b:m0');
});

test('picker items：过滤态展平并带文件夹名；无匹配与空列表给出提示', () => {
  const hit = domain.boardPickerItems({ boards, folders, uids: ['Q1'], query: ' 高三 ' });
  assert.deepEqual(hit.rows.map(row => [row.board.id, row.folderName]), [['b1', '高三'], ['b2', '高三']]);
  assert.equal(domain.boardPickerItems({ boards, folders, uids: ['Q1'], query: '物理' }).empty, '没有匹配「物理」的板');
  assert.equal(domain.boardPickerItems({ boards: [], folders: [], uids: ['Q1'] }).empty, '还没有展示板：下面新建一个。');
});

test('picker 高亮：默认第一个点了有用的行；↑↓ 循环；折叠目标是高亮行所在的文件夹', () => {
  const model = domain.boardPickerItems({ boards, folders, uids: ['Q1', 'Q2'] });
  assert.equal(domain.boardPickerDefaultActive(model.rows), 1);   // b1 已全部在板中
  assert.equal(domain.boardPickerDefaultActive([]), -1);
  assert.equal(domain.boardPickerDefaultActive([{ state: { kind: 'full' } }]), 0);
  assert.equal(domain.boardPickerStep(2, 1, 3), 0);
  assert.equal(domain.boardPickerStep(0, -1, 3), 2);
  assert.equal(domain.boardPickerStep(-1, 1, 3), 0);
  assert.equal(domain.boardPickerFoldTarget(model.items, 'b:b2'), 'f1');
  assert.equal(domain.boardPickerFoldTarget(model.items, 'b:b3'), '');   // 未归档不能折叠
  assert.equal(domain.boardPickerFoldTarget(model.items, 'nope'), '');
  // 折叠 / 展开后高亮落点：展开时是组里第一行，折叠时是组后面的第一行，后面没有行时取前面最后一行
  assert.equal(domain.boardPickerRowAfterGroup(model.items, 'f1'), 'b:b1');
  const folded = domain.boardPickerItems({ boards, folders, uids: ['Q1'], collapsed: new Set(['f1']) });
  assert.equal(domain.boardPickerRowAfterGroup(folded.items, 'f1'), 'b:b3');
  const tail = [{ type: 'row', key: 'r:x' }, { type: 'group', id: 'f9', plain: false }];
  assert.equal(domain.boardPickerRowAfterGroup(tail, 'f9'), 'r:x');
  assert.equal(domain.boardPickerRowAfterGroup(tail, 'nope'), '');
});

test('picker 点击决策：全部在板中 → 打开；⌘ 点本次加过的 → 撤回；其余加入（只加缺的）', () => {
  const added = new Map([['b1', ['Q1']]]);
  assert.deepEqual(domain.boardPickerPlan(boards[0], { uids: ['Q1'], added: new Map() }), { kind: 'open' });
  assert.deepEqual(domain.boardPickerPlan(boards[0], { uids: ['Q1'], added }, true), { kind: 'undo', uids: ['Q1'] });
  assert.deepEqual(domain.boardPickerPlan(boards[0], { uids: ['Q1'], added }, false), { kind: 'add', uids: ['Q1'], additive: false });
  assert.deepEqual(domain.boardPickerPlan(boards[1], { uids: ['Q3', 'Q4'] }, true), { kind: 'add', uids: ['Q4'], additive: true });
});

test('picker 位置：左对齐锚点、不出视口，下方放不下时翻到上方', () => {
  const viewport = { width: 1000, height: 800 };
  assert.deepEqual(domain.boardPickerPosition({ left: 100, top: 50, bottom: 80 }, { width: 320, height: 300 }, viewport), { left: 100, top: 86 });
  assert.deepEqual(domain.boardPickerPosition({ left: 900, top: 50, bottom: 80 }, { width: 320, height: 300 }, viewport), { left: 670, top: 86 });
  assert.deepEqual(domain.boardPickerPosition({ left: 10, top: 700, bottom: 730 }, { width: 320, height: 300 }, viewport), { left: 10, top: 394 });
});

test('picker 模板：高亮、提示符、行尾说明、aria-activedescendant，全部转义', () => {
  const model = domain.boardPickerItems({ boards: [...boards, { id: 'x', name: '<b>', folder_id: '', uids: [] }], folders, uids: ['Q1'], added: new Map([['b3', ['Q1']]]) });
  const out = view.boardPickerView({ title: '加入展示板', count: 1, query: '', items: model.items, rows: model.rows, active: 1, empty: model.empty, addedCount: 1, idBase: 't' }).text;
  assert.match(out, /aria-activedescendant="t-b:b2"/);
  assert.match(out, /class="bpicker-opt is-active" data-key="b:b2"/);
  assert.match(out, /data-bpk-board="b1"[^>]*>.*?<span class="bpicker-cue" aria-hidden="true">↗<\/span>/);
  assert.match(out, /is-added[^>]*>.*?<span class="bpicker-cue" aria-hidden="true">✓<\/span>/);
  assert.match(out, /已印 2 页/);
  assert.match(out, /缺失 1/);
  assert.match(out, /已加入 <b>1<\/b> 个板/);
  assert.match(out, /&lt;b&gt;/);
  assert.doesNotMatch(out, /style=/);
  assert.match(out, /data-bpk-fold="f1" aria-expanded="true"/);
});

test('picker 模板：部分已在板中与空态；新建按钮与新建表单', () => {
  const state = domain.boardPickerRowState({ uids: ['Q1'] }, ['Q1', 'Q2']);
  assert.match(view.boardPickerMeta({ count: 1 }, state).map(String).join(''), /已有 1\/2/);
  assert.equal(view.boardPickerNewLabel('  速览 '), '＋ 新建《速览》并加入');
  assert.equal(view.boardPickerNewLabel(''), '＋ 新建板并加入…');
  const empty = view.boardPickerView({ title: 't', count: 1, query: 'zz', items: [], rows: [], active: -1, empty: '没有匹配「zz」的板', addedCount: 0, idBase: 'e' }).text;
  assert.match(empty, /bpicker-empty/);
  assert.doesNotMatch(empty, /aria-activedescendant/);
  const form = view.boardPickerNewBody({ seed: 'a"b', folders, current: 'f1' }).text;
  assert.match(form, /value="a&quot;b"/);
  assert.match(form, /<option value="f1" selected>/);
  assert.doesNotMatch(view.boardPickerNewBody({ folders: [] }).text, /select/);
});

function fakes(list = boards) {
  const calls = [];
  const data = { boards: list.slice(), folders: folders.slice() };
  const source = {
    boards: () => data.boards, folders: () => data.folders, adopt: next => { calls.push(['adopt']); Object.assign(data, next); },
    lastId: () => 'b2', remember: id => calls.push(['remember', id]), collapsed: () => new Set(), toggleFolder: () => {},
    add: async (id, uids, options) => { calls.push(['add', id, uids, options]); return { id, name: '数列', items: [{}, {}], added_uids: uids }; },
    reload: async () => calls.push(['reload']), open: async id => calls.push(['open', id]), adoptDetail: board => calls.push(['detail', board.id]),
  };
  const toasts = [];
  picker.configureBoardPicker({
    source,
    get: async () => ({ ok: true, data }),
    post: async (path, body) => { calls.push(['post', path, body]); return { ok: true, data: { board: { id: 'new', items: body.uids || [] } } }; },
    toast: (text, options) => toasts.push([text, options]),
    prompt: async () => '新板',
    dialog: async () => ({ ok: false }),
  });
  return { calls, toasts };
}

test('picker 控制器：Shift 直接加入上次的板，toast 给出撤销与换个板', async () => {
  const { calls, toasts } = fakes();
  await picker.boardPickerOpen(['Q7', 'Q7', ' '], { direct: true });
  assert.deepEqual(calls.find(call => call[0] === 'add'), ['add', 'b2', ['Q7'], { silent: true }]);
  assert.equal(toasts[0][0], '已直接加入《数列》（现共 2 题）');
  assert.deepEqual(toasts[0][1].actions.map(action => action.label), ['撤销', '换个板…']);
  await toasts[0][1].actions[0].onClick();
  assert.deepEqual(calls.find(call => call[0] === 'post'), ['post', '/api/board/items/remove', { id: 'b2', uids: ['Q7'] }]);
  assert.equal(toasts.at(-1)[0], '已撤销加入');
  assert.equal(picker.boardPickerIsOpen(), false);
  picker.configureBoardPicker(null);
});

test('picker 控制器：一个板都没有时直接弹「新建」，建好后记住并刷新', async () => {
  const { calls, toasts } = fakes([]);
  await picker.boardPickerOpen('Q1');
  assert.deepEqual(calls.find(call => call[0] === 'post'), ['post', '/api/board/create', { name: '新板', uids: ['Q1'] }]);
  assert.ok(calls.some(call => call[0] === 'remember' && call[1] === 'new'));
  assert.ok(calls.some(call => call[0] === 'reload'));
  assert.equal(toasts.at(-1)[0], '已新建《新板》，加入 1 题');
  assert.equal(picker.boardPickerIsOpen(), false);
  await picker.boardPickerOpen([]);   // 没有题目：什么都不做
  picker.configureBoardPicker(null);
});
