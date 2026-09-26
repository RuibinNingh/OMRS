// core/html.js 的纯逻辑单测：node --test tests/*.js tests/app/*.test.mjs
import test from 'node:test';
import assert from 'node:assert/strict';
import { html, raw, escape, isHtml, cls, HtmlResult } from '../../assets/app/core/html.js';

test('插值默认转义 & < > " \' 与反引号', () => {
  assert.equal(html`<p>${'<a href="x">&\'`'}</p>`.text, '<p>&lt;a href=&quot;x&quot;&gt;&amp;&#39;&#96;</p>');
});

test('属性里的插值同样转义，不能闭合引号注入事件', () => {
  const out = html`<b title="${'" onclick="alert(1)'}"></b>`.text;
  assert.equal(out, '<b title="&quot; onclick=&quot;alert(1)"></b>');
});

test('raw 原样输出；嵌套 html 结果不二次转义', () => {
  assert.equal(html`<div>${raw('<b>粗</b>')}${html`<i>${'<x>'}</i>`}</div>`.text, '<div><b>粗</b><i>&lt;x&gt;</i></div>');
});

test('数组逐项拼接；null / undefined / false / true 输出空，0 输出 "0"', () => {
  assert.equal(html`<ul>${[1, 2].map(n => html`<li>${n}</li>`)}</ul>`.text, '<ul><li>1</li><li>2</li></ul>');
  assert.equal(html`[${null}${undefined}${false}${true}${0}]`.text, '[0]');
  assert.equal(html`${[[html`<a></a>`], '<b>']}`.text, '<a></a>&lt;b&gt;');
});

test('escape / isHtml / toString', () => {
  assert.equal(escape(5), '5');
  assert.equal(escape(null), '');
  assert.ok(isHtml(html`x`));
  assert.ok(!isHtml('x'));
  assert.ok(html`a` instanceof HtmlResult);
  assert.equal(String(html`<p>${'&'}</p>`), '<p>&amp;</p>');
});

test('cls 拼接并忽略假值与嵌套数组', () => {
  assert.equal(cls('a', false && 'b', null, ['c', ['d', '']], 0), 'a c d');
});
