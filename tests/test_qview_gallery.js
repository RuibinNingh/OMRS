// 共享画廊卡片：题目库画廊、展示板画廊、选题弹窗画廊共用同一副骨架。
// 骨架只认「已经算好的 HTML 片段」，不读任何题库全局——这条约束一破，三处又会各自长出一份模板。
const assert = require('node:assert/strict');
const test = require('node:test');

global.escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
global.escapeAttr = global.escapeHtml;
global.document = { addEventListener() {}, querySelectorAll() { return []; } };

const { qvGalleryCard, qvGalleryIdHtml } = require('../assets/qview.js');

test('card renders the shared skeleton and drops empty optional slots', () => {
  const html = qvGalleryCard({ uid: 'Q1', previewHtml: '<p>题面</p>' });
  assert.match(html, /class="gallery-card /);
  assert.match(html, /<div class="gallery-head">/);
  assert.match(html, /<div class="gc-foot">/);
  assert.match(html, /data-question-preview-uid="Q1"/);
  assert.match(html, /data-lbl-target="Q1"/);
  assert.match(html, /<p>题面<\/p>/);
  assert.doesNotMatch(html, /gc-meta/);          // 没给元信息就整行不渲染
  assert.doesNotMatch(html, /gc-more/);          // 没给菜单就不留空壳
});

test('missing preview falls back to the loading placeholder', () => {
  assert.match(qvGalleryCard({ uid: 'Q1' }), /preview-placeholder/);
  assert.match(qvGalleryCard({ uid: 'Q1', previewHtml: '' }), /preview-placeholder/);
});

test('caller-supplied slots land in their documented places', () => {
  const html = qvGalleryCard({
    uid: 'Q2', className: 'bd-gallery-card is-selected', rowAttr: 'data-board-row="Q2"',
    leadHtml: '<span class="bd-gc-no">3</span>', idHtml: '<b>ID</b>', flagsHtml: '<i>已印</i>',
    menuHtml: '<button>⌖</button>', metaHtml: '物理 · 力学', previewClass: 'board-gallery-preview',
    previewHtml: '正文', footHtml: '<span>脚注</span>', labelsHtml: '<em>标记</em>',
  });
  assert.match(html, /class="gallery-card bd-gallery-card is-selected"/);
  assert.match(html, /data-board-row="Q2"/);
  assert.match(html, /<span class="bd-gc-no">3<\/span>\s*<span class="gc-id"><b>ID<\/b><\/span>/);
  assert.match(html, /<span class="gc-flags"><i>已印<\/i><\/span>/);
  assert.match(html, /<span class="gc-more"><button>⌖<\/button><\/span>/);
  assert.match(html, /<div class="gc-meta">物理 · 力学<\/div>/);
  assert.match(html, /class="gallery-preview board-gallery-preview"/);
  assert.match(html, /<span>脚注<\/span>/);
  assert.match(html, /<em>标记<\/em>/);
});

test('uid that repeats its category is split so the prefix stops being noise', () => {
  assert.equal(qvGalleryIdHtml('运动学12', '运动学'),
    '<span class="gc-cat">运动学</span><span class="gc-num">12</span>');
  assert.equal(qvGalleryIdHtml('运动学-12', '运动学'),
    '<span class="gc-cat">运动学</span><span class="gc-num">12</span>');   // 分隔符吃掉
  assert.equal(qvGalleryIdHtml('运动学', '运动学'), '<span class="gc-cat">运动学</span>');
  assert.equal(qvGalleryIdHtml('三角函数1', '代数'), '<span class="gc-num">三角函数1</span>');
  assert.equal(qvGalleryIdHtml('Q1', ''), '<span class="gc-num">Q1</span>');
  assert.equal(qvGalleryIdHtml('', ''), '<span class="gc-num"></span>');
});

test('untrusted text is escaped everywhere the card interpolates a value', () => {
  const html = qvGalleryCard({ uid: '"><img src=x onerror=alert(1)>' });
  assert.doesNotMatch(html, /<img src=x/);
  assert.match(html, /&quot;&gt;&lt;img/);
  assert.match(qvGalleryIdHtml('<script>', ''), /&lt;script&gt;/);
  assert.match(qvGalleryIdHtml('<b>x', '<b>'), /<span class="gc-cat">&lt;b&gt;<\/span>/);
});
