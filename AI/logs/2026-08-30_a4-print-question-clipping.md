# 2026-08-30 A4 打印题目裁切修复

## 变更摘要

- 修复 A4 导出中普通文字题按平级块排版导致的栏底裁切风险。
- 纯文字题现在先整体测量题头、题干、选项/小问和错因；临近栏底时整题换栏，并预留 32px 打印重排余量。
- 初次排版等待图片、字体和两帧浏览器布局稳定；进入打印媒体或触发 `beforeprint` 时清空旧页面并按最终打印态重新排版。
- 保留含图片题的长图切片路径；超高文字题回退到原有逐块/公式续栏逻辑。

## 根因

题目正文由多个独立块组成，原排版器只对题头应用 `keepNext`，没有把题干、(1)、(2) 和错因作为同一道题处理。第 15 题靠近栏底时，屏幕态测量留下的余量不足以覆盖打印态重排，后续小问落入固定 `.col { overflow: hidden }` 的裁剪区，因此打印时可能直接看不到 `(1)`。

## 修改文件

- `omrs/export_templates/a4.js`
  - 新增 `question-group` 整题测量与换栏。
  - 新增 `QUESTION_SLACK = 32`。
  - 新增打印前重排、字体稳定等待和旧页面清理。
  - 抽出普通块/内容块放置逻辑，保留图片与超高文本回退路径。
- `omrs/export_templates/a4.css`
  - 增加 `question-group` 的分页避免规则。
  - 增加打印按钮加载期间的禁用样式。
- `tests/test_report_export.py`
  - 增加整题分组、打印前重排和字体等待的模板回归断言。
- `AI/export.md`
  - 同步 A4 排版和打印前重排行为。
- `README.md`
  - 同步 A4 导出用户可见行为。

## 验证

- `node --check omrs/export_templates/a4.js`：通过。
- `uv run --with pytest python -m pytest -q tests/test_report_export.py`：6 passed。
- `uv run --with pytest python -m pytest -q`：23 passed。
- 使用原 30 题导出数据重建临时 HTML，并切换 Chromium `print` media：
  - 页面仍为 4 页；
  - 题头数量为 30；
  - 第 15 题被整体移到下一栏；
  - 第 15 题 `(1)`、`(2)` 均存在且同处 `question-group`；
  - `question-group` 栏底越界数量为 0；
  - 手动触发 `beforeprint` 后上述结果保持不变。
- `git diff --check`：通过。

## 备注

- 本次未修改题库 Markdown、Ledger、生产数据或 systemd 服务。
- 系统 Python 缺少 pytest，测试通过 `uv run --with pytest` 的临时环境执行。
