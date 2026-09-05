const assert = require('node:assert/strict');
const test = require('node:test');

global.document = { addEventListener() {}, getElementById() { return null }, querySelectorAll() { return [] }, querySelector() { return null } };
global.localStorage = { getItem() { return null }, setItem() {} };
global.window = {};
global.escapeHtml = value => String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
global.escapeAttr = global.escapeHtml;
global.asNumber = (value, fallback = 0) => { const n = Number(value); return Number.isFinite(n) ? n : fallback };

const { renderMdContent, mdLineBreakMode } = require('../assets/questions.js');

const CHOICES = ['下列说法正确的是（　）', 'A. 甲', 'B. 乙', 'C. 丙'].join('\n');

test('blank lines become paragraphs, never a full blank line of <br><br>', () => {
  const html = renderMdContent('第一段。\n\n第二段。', 'lean');
  assert.equal(html, '<p class="md-p">第一段。</p><p class="md-p">第二段。</p>');
  assert.ok(!html.includes('<br>'));
});

test('consecutive blank lines still collapse into a single paragraph break', () => {
  assert.equal(renderMdContent('甲\n\n\n\n乙', 'lean'), renderMdContent('甲\n\n乙', 'lean'));
});

test('lean mode joins single newlines, full mode keeps every one', () => {
  assert.equal(renderMdContent(CHOICES, 'lean'),
    '<p class="md-p">下列说法正确的是（　） A. 甲 B. 乙 C. 丙</p>');
  assert.equal(renderMdContent(CHOICES, 'full'),
    '<p class="md-p">下列说法正确的是（　）<br>A. 甲<br>B. 乙<br>C. 丙</p>');
});

test('trailing hard break before a blank line does not leak an extra empty line', () => {
  ['lean', 'full'].forEach(mode => {
    assert.equal(renderMdContent('标题。  \n\n正文。', mode),
      '<p class="md-p">标题。</p><p class="md-p">正文。</p>');
  });
});

test('a hard break inside a paragraph survives in both modes', () => {
  ['lean', 'full'].forEach(mode => {
    assert.ok(renderMdContent('甲。  \n乙。', mode).includes('甲。<br>乙。'));
  });
});

test('tables stay their own block with no stray <br> around them', () => {
  const html = renderMdContent('说明：\n| 项 | 值 |\n| --- | --- |\n| a | 1 |\n结论。', 'full');
  assert.ok(html.startsWith('<p class="md-p">说明：</p><div class="md-table-wrap">'));
  assert.ok(html.endsWith('<p class="md-p">结论。</p>'));
  assert.ok(!html.includes('<br></p>'));
});

test('mode falls back to lean when the preference global is absent', () => {
  assert.equal(mdLineBreakMode(), 'lean');
  assert.equal(renderMdContent(CHOICES), renderMdContent(CHOICES, 'lean'));
});

test('empty input renders nothing at all', () => {
  assert.equal(renderMdContent(''), '');
  assert.equal(renderMdContent('\n\n\n'), '');
});
