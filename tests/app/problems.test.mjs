import test from 'node:test';
import assert from 'node:assert/strict';
import { markdown } from '../../assets/app/domain/problems.js';

test('问题Markdown支持标题、列表、代码与安全链接，HTML转义且附件走私有入口', () => {
  const src = '# 处理办法\n\n**先看符号**\n\n- 负数变号\n- 检查边界\n\n```text\n<script>bad()</script>\n```\n\n[参考](https://example.invalid/doc)\n![](PA-'+ 'a'.repeat(64)+'.svg)';
  const out = markdown(src);
  assert.match(out,/<h1>处理办法<\/h1>/);
  assert.match(out,/<strong>先看符号<\/strong>/);
  assert.match(out,/<li>负数变号<\/li>/);
  assert.match(out,/<pre><code>/);
  assert.ok(!out.includes('<script>'));
  assert.match(out,/\/api\/problem-asset\?name=PA-/);
  assert.ok(!markdown('[危险](javascript:alert(1))').includes('href="javascript:'));
});
