import test from 'node:test';
import assert from 'node:assert/strict';
import { richMarkdown } from '../../assets/app/domain/rich-markdown.js';
import { markdown as problemMarkdown } from '../../assets/app/domain/problems.js';

test('备注的代码保留Markdown与公式源码，HTML只作为文字显示', () => {
  const out = richMarkdown('`**原样** $x$`\n\n```md\n## 原样\n<script>bad()</script>\n\\(x\\)\n```\n\n<img src=x onerror=bad()>');
  assert.match(out, /<code>\*\*原样\*\* \$x\$<\/code>/);
  assert.match(out, /<pre><code>## 原样\n&lt;script&gt;bad\(\)&lt;\/script&gt;\n\\\(x\\\)<\/code><\/pre>/);
  assert.ok(!out.includes('<script>') && !out.includes('<img'));
});

test('标题和加粗内渲染公式，多行展示公式不被拆成列表', () => {
  const out = richMarkdown('## 检查 \\(x\\)\n\n**先验 $x < 0$**\n\n\\[\na\\\\\n- b\n\\]');
  assert.match(out, /<h2>检查 <span class="math ">x<\/span><\/h2>/);
  assert.match(out, /<strong>先验 <span class="math ">x &lt; 0<\/span><\/strong>/);
  assert.match(out, /<span class="math display">\na\\\\\n- b\n<\/span>/);
  assert.ok(!out.includes('<li>'));
});

test('备注沿用完整或简略换行，硬换行在两种模式下保留', () => {
  assert.equal(richMarkdown('甲\n乙', 'full'), '<p class="md-p">甲<br>乙</p>');
  assert.equal(richMarkdown('甲\n乙', 'lean'), '<p class="md-p">甲 乙</p>');
  assert.equal(richMarkdown('甲  \n乙', 'lean'), '<p class="md-p">甲<br>乙</p>');
  assert.equal(richMarkdown(''), '');
});

test('备注题图保持原入口，问题说明单独映射PA私有附件', () => {
  const name = `PA-${'a'.repeat(64)}.svg`;
  assert.match(richMarkdown(`![[${name}|300]]`), /src="\/api\/image\?name=PA-/);
  assert.match(problemMarkdown(`![[${name}|300]]`), /src="\/api\/problem-asset\?name=PA-/);
  assert.match(richMarkdown('![[图 1.png|300]]'), /width="300"/);
  assert.ok(!richMarkdown('[危险](javascript:alert(1))').includes('href='));
  assert.match(richMarkdown('[参考](https://example.invalid)'), /rel="noopener noreferrer"/);
});

test('备注兼容表格、引用和有序列表', () => {
  const out = richMarkdown('| 检查 | 依据 |\n| --- | --- |\n| 符号 | $x$ |\n\n> 先验证\n\n1. 代入\n2. 核对');
  assert.match(out, /class="md-table"/);
  assert.match(out, /<td><span class="math ">x<\/span><\/td>/);
  assert.match(out, /<blockquote>先验证<\/blockquote>/);
  assert.match(out, /<ol><li>代入<\/li><li>核对<\/li><\/ol>/);
});
