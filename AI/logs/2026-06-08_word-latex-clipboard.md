# 2026-06-08 导出 Word 的 LaTeX 公式渲染 + 剪贴板读取按钮

## 1. 导出 Word：LaTeX → 原生公式（OMML）

**问题**：此前 `exporting._parse_math_runs` 只把 `$...$` / `$$...$$` 当作等距棕色**源码**原样输出，Word 里看到的是 `$\frac{1}{2}$` 字面量，不会排版成公式。

**改动**（`omrs/exporting.py`，仅标准库）：
- `_DOCX_DOC_TEMPLATE` 的 `<w:document>` 根元素新增数学命名空间 `xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math"`。
- 新增 LaTeX→OMML 转换器：`_tokenize_latex` → `_parse_seq` / `_parse_atom`（递归下降）→ `_latex_to_omml`，配 `_LATEX_SYMBOLS`（希腊字母 + 常用运算/关系符）、`_LATEX_FUNCS`（直立函数名）、OMML 构造 `_m_run/_m_run_nor/_m_e`。
  - 覆盖：上标 `^`、下标 `_`、上下标组合（`m:sSup/m:sSub/m:sSubSup`）、分数 `\frac{}{}`（`m:f`）、根号 `\sqrt{}` 与 `\sqrt[n]{}`（`m:rad`，无次幂时 `degHide`）、`{}` 分组、希腊字母、`\times \div \pm \le \ge \neq \approx \cdot \infty \angle \perp \parallel \cong \rightarrow …`、函数名 `\sin \cos \tan \log \ln \lim …`、度数 `^\circ`。
- 重写 `_parse_math_runs`：数学片段 → `<m:oMath>…</m:oMath>` 内联进段落；**任何解析异常都被 try/except 捕获并回退**为原来的等距棕色源码。转换器各 OMML 构造自闭合，输出恒为良构 XML（`.format(body=…)` 不解释 body 内的花括号，OMML 也无花括号，二者均安全）。

**测试**：`_latex_to_omml` 单测（`x^2 / x_i / x_i^2 / \frac / \sqrt / \sqrt[3] / \alpha / 90^\circ / \sin / 嵌套`）+ 全量 docx 构建后逐 part `ET.fromstring` 校验良构、确认含 `m` 命名空间与 `<m:oMath>/<m:f>/<m:sSup>`、`include_answers` 路径同样生效。

> 说明：转换器面向中学/常见数学；极端/少见的 LaTeX 会安全回退为源码，不会损坏文档。Word 渲染未能在本环境内打开校验，但产出的是标准内联 OMML（良构且符合常见结构）。

## 2. 录入页：每个图片区加「📋 从剪贴板读取」按钮

**问题**：Ctrl/⌘+V 落到「当前目标区」（最近点击/聚焦的区），用户「想粘到答案却进了题目」。

**改动**：
- `omrs_dashboard.html`：题目区、答案区各加一个 `📋 从剪贴板读取到「题目/答案」`（`.paste-actions` 内 `.btn.sm`）。
- `assets/app.js`：新增 `crReadClipboard(kind)` —— `navigator.clipboard.read()` 取剪贴板图片，加入**指定区**（同时把该区设为当前目标）；无图 / 浏览器不支持 / 权限被拒时弹中文提示。`crSetPasteTarget(kind)` 改为同时给目标区切换 `.paste-active` 高亮（`init()` 时初始化默认题目区）。
- `assets/styles.css`：`.paste-zone.paste-active`（实线 + accent 边框高亮）、`.paste-actions`。

**测试**（真实源 + mock DOM/navigator）：`crSetPasteTarget` 高亮在正确区切换；`crReadClipboard('a')` 把剪贴板图片读到答案区并设目标；剪贴板无图时提示且不添加。

## 数据/兼容性

- 仅 `exporting.py` 增能与前端增按钮；Markdown 文件格式、CSV、API 请求/返回结构均未变（`/api/create` 字段不变）。`data.md` 增 LaTeX 导出说明，`frontend.md` 增剪贴板/目标区说明。
