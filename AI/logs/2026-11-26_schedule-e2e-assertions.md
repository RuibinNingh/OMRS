# 2026-11-26 修复调度端到端回归断言

> **任务**
> - 标识：schedule-e2e-assertions
> - 状态：已交付

## 背景

用户在追查 PDF 导出交付记录中的三项调度回归失败后问「那么能不能进行修复」。完整模式，基线 `683d3df`。界面自 `97c1681` 起以「原计划 N 题」显示正式计划原题数，暂停反馈时隐藏提交按钮。旧断言仍等待「共 N 题」及禁用按钮。

## 行为变化

生成计划的回归按真实创建回执中的计划编号匹配已打开的详情，并核对题目行数。多题场景还验证双击只发一次请求、只生成一份计划，返回安排页后已清空选择。暂停场景检查恢复提示与提交入口隐藏。

## 影响文件

- `tests/e2e/schedule.py` 更新三项回归及失败诊断。
- `AI/frontend/architecture.md`、`AI/frontend/review.md` 与 `AI/frontend/feedback.md` 同步测试契约、进度文案和暂停时的提交入口。

## 已执行验证

- 临时 Vault 与 Chromium 运行 `python tests/e2e/schedule.py`，54 项通过，0 失败。
- `python tests/e2e/schedule_export.py` 39 项通过，覆盖 PDF 与 HTML 下载。
- `node --test tests/app/schedule.test.mjs tests/app/arrange.test.mjs tests/app/feedback.test.mjs` 42 项通过。
- 生成日志索引，`python3 tests/check_docs.py --diff 683d3df` 与 `git diff --check` 通过。

## 未执行验证

未运行全仓门禁。改动范围为调度回归脚本与文档，浏览器验证使用合成题库与随机端口。未执行生产发布。
