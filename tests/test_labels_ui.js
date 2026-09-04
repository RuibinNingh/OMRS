const assert = require('node:assert/strict');
const test = require('node:test');

global.escapeHtml = value => String(value ?? '')
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
global.escapeAttr = global.escapeHtml;

const { lblInk, lblChip } = require('../assets/labels.js');
const fs = require('node:fs');
const vm = require('node:vm');

function luminance(rgb) {
  const values = rgb.map(value => {
    const v = value / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
}

function contrast(a, b) {
  const x = luminance(a), y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

function hexRgb(value) {
  const hex = value.replace('#', '');
  return [0, 2, 4].map(index => parseInt(hex.slice(index, index + 2), 16));
}

function chipBackground(color, theme) {
  const base = theme === 'dark' ? [33, 31, 29] : [255, 255, 255];
  const rgb = hexRgb(color);
  return rgb.map((value, index) => Math.round(value * 0.18 + base[index] * 0.82));
}

test('lblInk reaches AA contrast for preset and extreme colors', () => {
  const colors = ['#dc2626', '#ea580c', '#ca8a04', '#16a34a', '#0d9488',
    '#2563eb', '#7c3aed', '#db2777', '#64748b', '#78716c', '#ffff00', '#000000'];
  for (const color of colors) {
    for (const theme of ['light', 'dark']) {
      assert.ok(
        contrast(hexRgb(lblInk(color, theme)), chipBackground(color, theme)) >= 4.5,
        `${color} ${theme}`,
      );
    }
  }
});

test('lblChip escapes text and has only the 18 percent chip style', () => {
  const html = lblChip({ name: '<危险>', color: '#dc2626' });
  assert.match(html, /&lt;危险&gt;/);
  assert.match(html, /rgba|--lbl-rgb/);
  assert.doesNotMatch(html, /solid|soft|lbl-soft/);
});

test('filterItems supports label any/all and keeps search compatibility', () => {
  const source = fs.readFileSync(require.resolve('../assets/core.js'), 'utf8');
  const sandbox = { console, Date, Math, Set, Object, String, Number, Array };
  vm.createContext(sandbox);
  vm.runInContext(`${source}\nthis.__filterItems = filterItems;`, sandbox);
  const items = [
    { uid: 'U1', labels: ['A', 'B'], difficulty: 5, mastery: 0.2, tag: '#状态/待攻克', due_date: '' },
    { uid: 'U2', labels: ['A'], difficulty: 5, mastery: 0.2, tag: '#状态/待攻克', due_date: '' },
    { uid: 'U3', labels: ['C'], difficulty: 5, mastery: 0.2, tag: '#状态/待攻克', due_date: '' },
  ];
  const base = { text: '', subject: '', category: '', tag: '', knowledgeTag: '',
    difficultyMin: 0, difficultyMax: 10, masteryMin: null, masteryMax: null,
    dueFilter: '', suspended: '', sort: 'mastery-asc' };
  assert.deepEqual(
    Array.from(sandbox.__filterItems(items, { ...base, labels: ['A', 'B'], labelMode: 'any' }), item => item.uid),
    ['U1', 'U2'],
  );
  assert.deepEqual(
    Array.from(sandbox.__filterItems(items, { ...base, labels: ['A', 'B'], labelMode: 'all' }), item => item.uid),
    ['U1'],
  );
  assert.deepEqual(
    Array.from(sandbox.__filterItems(items, { ...base, labels: [], labelMode: 'any', text: 'c' }), item => item.uid),
    ['U3'],
  );
});
