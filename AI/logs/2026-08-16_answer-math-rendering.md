# 2026-08-16：答案跨行 LaTeX 渲染修复

## 背景

OMRS 答案导出截图中，行内公式能渲染，但独立行的 `$$...$$` 被拆成 `$$`、公式正文、`$$` 三类普通文本；分段函数的 cases 环境因此直接显示源码。题目 16、3、54 都能复现。

## 根因

`omrs/exporting.py::_text_to_blocks()` 原先按物理行切分文本，而 A4/屏幕模板的 `mathText()` 需要在同一个字符串中看到成对的 `$$`。仪表盘 `assets/questions.js::renderMdContent()` 也逐行调用行内渲染器，页面端存在同类问题。

## 变更

- `omrs/exporting.py`：统计未转义的 `$$` 分隔符，将跨行行间公式合并为一个文字块；未闭合公式保持原有安全降级行为。
- `assets/questions.js`：在逐行渲染前合并跨行 `$$` 块，表格处理路径保持不变。
- `tests/test_report_export.py`：增加跨行 display-math 与 cases 环境回归断言。
- `AI/export.md`、`AI/frontend.md`：补充跨行公式的块化与渲染约定。

## 验证

- `python3 -m py_compile omrs/exporting.py tests/test_report_export.py`：通过。
- `node --check assets/questions.js`：通过。
- `python3 -m unittest discover -s tests -q`：15 项通过。
- pytest 风格导出测试中的表格测试与跨行公式测试：直接调用通过；环境未安装 pytest。
- Node 最小 DOM/Katex 桩测试：跨行 cases 只调用一次 display-mode KaTeX，且传入真实换行；通过。
- 用三个实际错题样例生成 A4 自包含 HTML：成功生成约 1.75 MB 文件，后端答案块均保持完整的 `$$...$$`。

## 未验证与上线边界

- 浏览器截图验收未完成：当前环境没有 Chrome/Edge，`browser-use --doctor` 报 chrome、daemon、active connection 均失败；连最小静态页面的 browser_exec 也超时。因此没有把浏览器自动化故障冒充为视觉验收通过。
- 本次只修改工作区源码、测试和文档，没有重启 `omrs.service`，也没有切换生产部署；需要上线时应单独按部署流程验收。
