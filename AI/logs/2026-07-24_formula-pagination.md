# 2026-07-24 A4 公式续栏与防截断

## 变更摘要

- A4 浏览器排版器会在含 KaTeX 的文字段不能放入当前栏时，按公式起点拆分：前缀保留在当前栏，公式及后文移到下一栏或下一页顶部。
- 页面在测量前立即挂到 `#stage`；每次 DOM 落位后复核实际元素底边。此前页面未挂载就读取矩形导致高度为零、所有内容被排进一页，现已修正为真实高度计算；超出有效栏高会撤回并换栏。
- 纵向题注、表格、展示公式与图片切片间距改为计入块高度的内边距或移除外边距；图片仍沿用既有 Canvas 白缝切片算法。

## 行为与兼容性

- 后端导出数据、HTTP API、CLI 参数与图片 data URI 不变。
- 无公式文字、表格和图片仍按原有规则处理；单个公式本身高过完整栏的极端情况不自动缩放或改写。

## 修改文件

- `omrs/export_templates/a4.js`
- `omrs/export_templates/a4.css`
- `tests/test_report_export.py`
- `AI/export.md`
- `README.md`
- `AI/logs/log.md`

## 验证

- `node --check omrs/export_templates/a4.js`（通过）
- 设置 `PYTHONPATH` 为仓库根目录后运行 `python -m pytest -q tests/test_report_export.py --basetemp=<可写临时目录> -o cache_dir=<可写缓存目录>`（5 passed）
- `git diff --check`（通过）
- 通过 `_build_html()` 回归测试确认生成的 A4 HTML 内联公式续栏和实际落位校验逻辑。
- 尝试使用本机 Chrome 与 Edge 无头渲染临时回归页；受当前 Windows 沙箱的 GPU 进程限制，浏览器在生成截图前退出，未将此项记为通过。

## 同步过的文档

- `AI/export.md`
- `README.md`
- `AI/logs/log.md`