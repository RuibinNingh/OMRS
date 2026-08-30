# 2026-08-30 A4 块级防截断修正

## 用户反馈

上一版为了避免第 15 题打印裁切，将整道纯文字题包成 `question-group`，并在栏底额外预留 `QUESTION_SLACK = 32px`。这虽然能防止小问被裁掉，但会造成不必要的栏底留白。

用户明确要求：只保证不截断，不牺牲版面利用率。

## 最终方案

- 移除 `question-group` 整题分组。
- 移除 `QUESTION_SLACK` 及整题整体换栏逻辑。
- 恢复题头、题干、小问、错因等按原有块顺序贪心填栏。
- 每个块先离屏测量，放入后再用真实 DOM 底边校验；当前栏放不下时，只把当前块完整移到下一栏/页。
- 含公式的文字块继续按公式边界拆分，普通无公式文字块整块移动，不会截断。
- 保留图片白缝切片；字体稳定分两阶段等待：先等已有字体，首次生成 KaTeX DOM 后再等一次并重新测量，避免打印时数学字体完成导致栏底内容溢出。移除 `beforeprint` / print media 二次排版，让浏览器预览和打印复用同一份固定页面 DOM。

## 修改文件

- `omrs/export_templates/a4.js`
- `omrs/export_templates/a4.css`
- `tests/test_report_export.py`
- `AI/export.md`
- `README.md`
- `AI/logs/log.md`

## 验证

- `node --check omrs/export_templates/a4.js`：通过。
- `git diff --check`：通过。
- `uv run --with pytest python -m pytest -q`：23 passed。
- 实际生产 `POST /api/export` 返回新版紧凑模板：
  - `question-group` 不存在；
  - `QUESTION_SLACK` 不存在；
  - `beforeprint` 保留；
  - 第 15 题仍在导出响应中。
- 使用该生产响应切换 Chromium `print` media：
  - 页面 4 页；
  - 题头数量 30；
  - 第 15 题 `(1)` 与 `(2)` 是两个独立 `.blk q-text`；
  - 两个小问均在栏底以内；
  - 所有 `.blk` 栏底越界数量为 0；
  - `beforeprint` / print media 二次排版已移除；屏幕与打印复用同一份固定页面 DOM。

## 后续修正

发现打印前二次排版会造成浏览器预览与打印预览使用不同分页。已移除该机制；现在只在字体稳定后排版一次，打印阶段不再调用 `run()`。

## 用户实测问题与最终修正

用户提供了同一页打印前/打印后的对比图：打印前第 15 题的 `(1)` 已在栏底出现半行，打印后该小问被 `.col { overflow: hidden }` 完全裁掉。根因不是截图视口，而是首次 `document.fonts.ready` 发生在 `run()` 之前；`run()` 才创建 KaTeX 数学 DOM，数学字体可能在首次测量后才加载，打印时行高变化导致内容进入裁剪区。

最终改为两阶段启动：先等已有字体并运行一次生成 KaTeX DOM，再等生成后的 `document.fonts.ready` 和两帧布局，随后用最终字体重新运行一次。仍不使用整题分组、额外 slack 或 `beforeprint` 二次排版。

最终生产接口与 Chromium 验证：screen/print 均 4 页、文本分页指纹完全一致，第 15 题两个小问均在第 2 页，所有块栏底越界为 0；全套测试 23 passed。

## 上线边界

本次仍只修改生产服务读取的工作区源码和文档，不修改题库、Ledger 或 systemd 配置；模板会在下一次 `/api/export` 请求时读取。
