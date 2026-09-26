// domain/labels/（P5 第 4 轮起）：芯片、颜色、运行时样式表、选择器与管理的数据部分。
// 前 5 个用例从 tests/test_labels_ui.js 迁入（该文件已删除），断言按新结构改写：颜色写 data-lbl-c、solid 前景是 token 引用。
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import { hexKey, rgbOf, lblInk, labelFg, chipBackground, contrastRatio, presetColors, defaultColor, normalizeColor, setTokenReader } from '../../assets/app/domain/labels/color.js';
import { chipHtml, chipsHtml } from '../../assets/app/domain/labels/chips.js';
import { colorRule, ensureColor, registeredColors } from '../../assets/app/domain/labels/sheet.js';
import * as model from '../../assets/app/domain/labels/model.js';

const read = rel => fs.readFileSync(new URL(rel, import.meta.url), 'utf8');
const tokens = read('../../assets/app/styles/tokens.css');
setTokenReader(name => (tokens.match(new RegExp(`${name}\\s*:\\s*([^;]+);`)) || [])[1]?.trim() || '');
const PRESETS = presetColors();

test('lblInk reaches AA contrast for presets and extreme colors in both themes', () => {
  for (const color of [...PRESETS, '#ffff00', '#000000', '#ffffff']) {
    for (const theme of ['light', 'dark']) {
      assert.ok(contrastRatio(rgbOf(lblInk(color, theme)), chipBackground(color, theme)) >= 4.5, `${color} ${theme}`);
    }
  }
});

test('labelFg picks the dark token on light colors and the light token on dark colors', () => {
  assert.equal(labelFg('#ffff00'), 'var(--lbl-fg-dark)');
  assert.equal(labelFg('#fbbf24'), 'var(--lbl-fg-dark)');
  assert.equal(labelFg('#ca8a04'), 'var(--lbl-fg-light)');
  assert.equal(labelFg('#dc2626'), 'var(--lbl-fg-light)');
  assert.equal(labelFg('#2563eb'), 'var(--lbl-fg-light)');
});

test('chipHtml escapes text, writes the color as data-lbl-c (no style=) and supports variants', () => {
  const html = chipHtml({ name: '<危险>', color: '#DC2626' });
  assert.match(html, /&lt;危险&gt;/);
  assert.doesNotMatch(html, /<危险>/);
  assert.match(html, /data-lbl-c="dc2626"/);
  assert.doesNotMatch(html, /style=/);
  assert.match(html, /class="lbl"/);
  assert.match(chipHtml({ name: 'A', color: '#16a34a' }, { variant: 'solid', lg: true }), /class="lbl solid lg"/);
  assert.match(chipHtml({ name: 'A', color: '#16a34a' }, { print: true }), /class="lbl print"/);
  assert.equal(chipHtml({ name: '   ', color: '#16a34a' }), '');
  assert.doesNotMatch(chipHtml({ name: '没颜色', color: 'red' }), /data-lbl-c/, '不合法的颜色退回 .lbl 默认灰');
});

test('chipsHtml adds a + entry, caps visible chips and wraps with a delegated target', () => {
  const html = chipsHtml(['A', 'B', 'C', 'D', 'E'], { add: true, max: 3, uid: 'U"1' }, []);
  assert.match(html, /data-lbl-target="U&quot;1"/);
  assert.match(html, /data-lbl-add="1"/);
  assert.match(html, />\+2</);
  assert.equal((html.match(/data-lbl-name=/g) || []).length, 3);
  assert.match(chipsHtml([], { add: true }), /＋ 标记/);
  assert.equal(chipsHtml([]), '');
  assert.match(chipsHtml(['甲'], {}, [{ name: '甲', color: '#2563eb' }]), /data-lbl-c="2563eb"/, '按名称查定义取颜色');
});

test('filterItems supports label any/all and keeps search compatibility', () => {
  const sandbox = { console, Date, Math, Set, Object, String, Number, Array, document: { addEventListener() {} }, localStorage: { getItem: () => null, setItem() {} } };
  vm.createContext(sandbox);
  vm.runInContext(`${read('../../assets/core.js')}\nthis.__filterItems = filterItems;`, sandbox);
  const items = [
    { uid: 'U1', labels: ['A', 'B'], difficulty: 5, mastery: 0.2, tag: '#状态/待攻克', due_date: '' },
    { uid: 'U2', labels: ['A'], difficulty: 5, mastery: 0.2, tag: '#状态/待攻克', due_date: '' },
    { uid: 'U3', labels: ['C'], difficulty: 5, mastery: 0.2, tag: '#状态/待攻克', due_date: '' },
  ];
  const base = { text: '', subject: '', category: '', tag: '', knowledgeTag: '', difficultyMin: 0, difficultyMax: 10, masteryMin: null, masteryMax: null, dueFilter: '', suspended: '', sort: 'mastery-asc' };
  assert.deepEqual(Array.from(sandbox.__filterItems(items, { ...base, labels: ['A', 'B'], labelMode: 'any' }), item => item.uid), ['U1', 'U2']);
  assert.deepEqual(Array.from(sandbox.__filterItems(items, { ...base, labels: ['A', 'B'], labelMode: 'all' }), item => item.uid), ['U1']);
  assert.deepEqual(Array.from(sandbox.__filterItems(items, { ...base, labels: [], labelMode: 'any', text: 'c' }), item => item.uid), ['U3']);
});

test('presets come from tokens.css (10 colors, #9 is the default grey); domain/labels JS has no color literals', () => {
  assert.equal(PRESETS.length, 10);
  assert.ok(PRESETS.every(color => /^#[0-9a-f]{6}$/.test(color)));
  assert.equal(defaultColor(), PRESETS[8]);
  assert.equal(normalizeColor('ABC'), '#aabbcc');
  assert.equal(normalizeColor('nope'), PRESETS[8]);
  assert.equal(hexKey(' #12AB3f '), '12ab3f');
  const dir = new URL('../../assets/app/domain/labels/', import.meta.url);
  for (const name of fs.readdirSync(dir).filter(f => f.endsWith('.js'))) {
    const text = fs.readFileSync(new URL(name, dir), 'utf8').replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, '');
    assert.doesNotMatch(text, /(?<![\w&-])#[0-9a-fA-F]{3,8}(?![\w-])|\brgba?\(/, `${name} 里不应有颜色字面量`);
  }
});

test('colorRule / ensureColor: one runtime rule per color with all chip variables; invalid colors are ignored', () => {
  const rule = colorRule('dc2626');
  for (const part of ['[data-lbl-c="dc2626"]', '--lbl-c:#dc2626', '--lbl-rgb:220,38,38', '--lbl-fg:var(--lbl-fg-light)', `--lbl-ink-l:${lblInk('#dc2626', 'light')}`, `--lbl-ink-d:${lblInk('#dc2626', 'dark')}`]) {
    assert.ok(rule.includes(part), part);
  }
  assert.equal(ensureColor('#0D9488'), '0d9488');
  assert.equal(ensureColor('0d9488'), '0d9488');
  assert.equal(registeredColors().filter(key => key === '0d9488').length, 1);
  assert.equal(ensureColor('not-a-color'), '');
});

test('pickerOptions filters unarchived labels case-insensitively and offers "create" only without an exact match', () => {
  const list = [{ name: 'Alpha' }, { name: '考前必看' }, { name: 'alpha 旧', archived: true }];
  assert.deepEqual(model.pickerOptions(list, ' al ').matches.map(l => l.name), ['Alpha']);
  assert.equal(model.pickerOptions(list, ' al ').create, 'al');
  assert.equal(model.pickerOptions(list, '考前必看').create, '');
  assert.deepEqual(model.pickerOptions(list, '').matches.map(l => l.name), ['Alpha', '考前必看']);
  assert.equal(model.pickerOptions(list, '').create, '');
});

test('recent labels: touchRecent dedupes, caps at 6 and drops unknown names; quickList puts recent first', () => {
  const store = new Map();
  const storage = { getItem: key => store.get(key) ?? null, setItem: (key, value) => store.set(key, value) };
  const list = 'ABCDEFGH'.split('').map(name => ({ name, color: '' }));
  model.touchRecent(storage, ['A', 'B'], list);
  model.touchRecent(storage, ['C', 'A', 'Z'], list);
  assert.deepEqual(model.readRecent(storage, list), ['C', 'A', 'B']);
  model.touchRecent(storage, ['D', 'E', 'F', 'G'], list);
  assert.equal(model.readRecent(storage, list).length, 6);
  assert.deepEqual(model.quickList(list, ['C', 'A'], 4).map(l => l.name), ['C', 'A', 'B', 'D']);
  assert.deepEqual(model.readRecent({ getItem: () => '{bad json' }, list), []);
});

test('nextColor takes the first unused preset, then rotates; applyBatch / formValues / sort / upsert', () => {
  assert.equal(model.nextColor([{ color: PRESETS[0] }, { color: PRESETS[1].toUpperCase() }], PRESETS), PRESETS[2]);
  const full = PRESETS.map(color => ({ color }));
  assert.equal(model.nextColor([...full, { color: '#123456' }], PRESETS), PRESETS[11 % 10]);
  assert.equal(model.nextColor([], []), '');
  const items = [{ uid: 'U1', labels: ['A', 'B'] }, { uid: 'U2', labels: [] }, { uid: 'U3', labels: ['A'] }];
  assert.deepEqual(model.applyBatch(items, ['U1', 'U2'], ['C', 'A'], ['B']), { U1: ['A', 'C'], U2: ['C', 'A'] });
  assert.deepEqual(model.formValues({ name: '  考前  ', color: 'F00', bonus: '1.7' }, '#64748b'), { name: '考前', color: '#ff0000', priority_bonus: 1 });
  assert.deepEqual(model.formValues({ name: 'x', color: '', bonus: 'abc' }, '#64748b'), { name: 'x', color: '#64748b', priority_bonus: 0 });
  const sorted = model.sortLabels([{ name: '乙', order: 2 }, { name: 'B', order: 1 }, { name: 'A', order: 1 }]);
  assert.deepEqual(sorted.map(l => l.name), ['A', 'B', '乙']);
  assert.deepEqual(model.upsertLabel(sorted, { id: 'x', name: 'B', order: 0 }).map(l => l.name), ['B', 'A', '乙']);
});
