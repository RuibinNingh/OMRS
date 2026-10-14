// 前后端共用真实答案夹具，验证定界符转换、渲染与 KaTeX 延迟加载。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import { normalizeMathDelimiters } from '../../assets/app/domain/question/math-text.js';
import { renderMd, renderMdInline, clearMdCache, mdCacheStats } from '../../assets/app/domain/question/markdown.js';
import { renderMd as renderChat, plainOf } from '../../assets/app/features/assistant/md.js';

const cases = JSON.parse(readFileSync(new URL('../fixtures/math_delimiters.json', import.meta.url), 'utf8'));

for (const entry of cases) test(entry.name, () => {
  const actual = normalizeMathDelimiters(entry.source);
  assert.equal(actual, entry.expected);
  assert.equal(normalizeMathDelimiters(actual), actual);
});

test('完整答案在题目与聊天中渲染全部公式，跨行公式保持完整', () => {
  const expected = cases[0].expected;
  for (const render of [renderMd, renderChat]) {
    const out = render(cases[0].source);
    assert.equal(out, render(expected));
    assert.equal((out.match(/class="math /g) || []).length, 16);
    assert.equal((out.match(/class="math display"/g) || []).length, 7);
    assert.ok(out.includes(String.raw`\boxed{\frac{v_0^2}{2g}}`));
    assert.ok(out.includes('故选 AD。'));
    assert.doesNotMatch(out, /\\[()[\]]/);
  }
  assert.equal(renderMdInline(String.raw`求 \(t\)。`), '求 <span class="math ">t</span>。');
  assert.equal(plainOf(String.raw`周期是 \(\pi\)`), '周期是 pi');
  assert.match(renderChat('```tex\n\\(t\\)\n```'), /<pre><code>\\\(t\\\)<\/code><\/pre>/);
  assert.doesNotMatch(renderMd(String.raw`\(<script>\)`), /<script>/);
});

test('KaTeX 延迟加载时不缓存旧定界符的源码降级结果', () => {
  clearMdCache();
  const source = String.raw`求 \(t\)，\[\frac{v_0}{g}\]`;
  renderMd(source);
  renderMd(source);
  assert.equal(mdCacheStats().size, 0);
  const old = globalThis.katex;
  globalThis.katex = { renderToString: (text, options) => `<span class="katex" data-display="${options.displayMode}">${text}</span>` };
  try {
    const out = renderMd(source);
    assert.equal((out.match(/class="katex"/g) || []).length, 2);
    assert.ok(out.includes('data-display="true"'));
    assert.equal(mdCacheStats().size, 1);
  } finally {
    globalThis.katex = old;
    clearMdCache();
  }
});
