# 2026-06-12 题目内容图片与 LaTeX 渲染修复

## 背景

题目库点击「查看」后，Modal 中的备注和答案仍按纯文本输出：`![[...]]` / `![...](...)` 不会变成图片，`$...$` / `$$...$$` 也不会进入公式渲染。即时练习的题面与答案已复用 `renderMdContent()`，但备注仍是纯文本；复习调度的预览/完整查看依赖同一题目渲染链路，需要一起确认。

## 改动

- `assets/questions.js`
  - 将 `renderMdContent()` 从「只替换图片」升级为统一安全渲染器：普通文本先转义，只放行图片与 LaTeX 受控输出。
  - 支持 Obsidian 图片 `![[name.png]]`、`![[name.png|300]]` 与 Markdown 图片 `![alt](path)`，统一走 `/api/image?name=...`。
  - 支持行内 `$...$` 与行间 `$$...$$`。KaTeX 可用时调用 `katex.renderToString()`；不可用时降级为 `.math` 公式片段。
  - 题目库 Modal 的备注、答案改用 `renderMdContent()`，不再用 `<pre>${escapeHtml(...)}</pre>`。
- `assets/instant.js`
  - 即时练习展开答案后，备注同样走 `renderMdContent()`，可显示图片和 LaTeX。
- `assets/styles.css`
  - 新增 `.math` / `.math.display` 降级样式和 KaTeX display 间距。
  - 补齐 Modal 备注/答案、即时练习备注中的图片样式。
- `omrs_dashboard.html` / `assets/vendor/katex/`
  - 将 KaTeX CSS/JS 与字体作为本地静态资源加载；加载失败时仍保留降级显示。
- `AI/frontend.md` / `AI/README.md`
  - 更新前端渲染契约与依赖边界说明。

## 影响范围

- 题目库：表格/画廊进入的「查看详情」中，题面、备注、答案统一支持图片与 LaTeX。
- 复习调度：画廊预览继续复用题面渲染；「预览/完整查看」进入同一 Modal，因此备注和答案同步修复。
- 即时练习：题面、答案、备注统一支持图片与 LaTeX。
