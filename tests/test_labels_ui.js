const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');

global.escapeHtml = value => String(value ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
global.escapeAttr = global.escapeHtml;

const { lblInk, lblChip, lblChips, labelFg, LABEL_PRESETS } = require('../assets/labels.js');

function luminance(rgb) {
  const values = rgb.map(value => { const v = value / 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
}
function contrast(a, b) { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
function hexRgb(value) { const hex = value.replace('#', ''); return [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16)); }
function chipBackground(color, theme) {
  const base = theme === 'dark' ? [33, 31, 29] : [255, 255, 255];
  const alpha = theme === 'dark' ? 0.24 : 0.16;
  return hexRgb(color).map((value, index) => Math.round(value * alpha + base[index] * (1 - alpha)));
}

test('lblInk reaches AA contrast for presets and extreme colors in both themes', () => {
  for (const color of [...LABEL_PRESETS, '#ffff00', '#000000', '#ffffff']) {
    for (const theme of ['light', 'dark']) {
      assert.ok(contrast(hexRgb(lblInk(color, theme)), chipBackground(color, theme)) >= 4.5, `${color} ${theme}`);
    }
  }
});

test('labelFg picks dark text on light colors and white on dark colors', () => {
  assert.equal(labelFg('#ffff00'), '#1a1c1f');
  assert.equal(labelFg('#fbbf24'), '#1a1c1f');
  assert.equal(labelFg('#ca8a04'), '#ffffff');
  assert.equal(labelFg('#dc2626'), '#ffffff');
  assert.equal(labelFg('#2563eb'), '#ffffff');
});

test('lblChip escapes text, injects color variables and supports variants', () => {
  const html = lblChip({ name: '<危险>', color: '#dc2626' });
  assert.match(html, /&lt;危险&gt;/);
  assert.doesNotMatch(html, /<危险>/);
  assert.match(html, /--lbl-rgb:220,38,38/);
  assert.match(html, /--lbl-c:#dc2626/);
  assert.match(html, /class="lbl"/);
  assert.match(lblChip({ name: 'A', color: '#16a34a' }, { variant: 'solid', lg: true }), /class="lbl solid lg"/);
  assert.match(lblChip({ name: 'A', color: '#16a34a' }, { print: true }), /class="lbl print"/);
  assert.equal(lblChip({ name: '   ', color: '#16a34a' }), '');
});

test('lblChips adds a + entry, caps visible chips and wraps with a delegated target', () => {
  const html = lblChips(['A', 'B', 'C', 'D', 'E'], { add: true, max: 3, uid: 'U"1' });
  assert.match(html, /data-lbl-target="U&quot;1"/);
  assert.match(html, /data-lbl-add="1"/);
  assert.match(html, />\+2</);
  assert.equal((html.match(/data-lbl-name=/g) || []).length, 3);
  assert.match(lblChips([], { add: true }), /＋ 标记/);
  assert.equal(lblChips([]), '');
});

test('filterItems supports label any/all and keeps search compatibility', () => {
  const source = fs.readFileSync(require.resolve('../assets/core.js'), 'utf8');
  const sandbox = { console, Date, Math, Set, Object, String, Number, Array, document: { addEventListener() {} }, localStorage: { getItem: () => null, setItem() {} } };
  vm.createContext(sandbox);
  vm.runInContext(`${source}\nthis.__filterItems = filterItems;`, sandbox);
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
