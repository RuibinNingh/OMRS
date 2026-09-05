# 2026-09-05 展示板打印设置契约纠正

## 变更摘要

根据当前产品需求，展示板不需要打孔标记。修正文档中对 `binding_marks`、`3hole`、
`26hole` 的描述，明确展示板仅保留 `binding_mm` 装订边距；题间留白继续使用
`gap_lines`，默认值为 2 行。

## 行为与兼容性

- 展示板打印不绘制打孔圈或其他打孔辅助标记。
- 展示板版面仍支持 `gap_lines`（默认 2）和 `binding_mm`（默认 22mm）等几何设置。
- 保留上一份功能修复日志，不改写其历史事实；本日志记录本次文档契约纠偏。

## 修改文件

- `AI/README.md`
- `AI/board.md`
- `AI/data.md`
- `AI/api.md`
- `AI/export.md`
- `AI/logs/log.md`
- `AI/logs/2026-09-05_functional-bug-fixes-2.md`

## 验证

- `python3 -m unittest tests.test_boards -v`：7 passed
- `node --check assets/board.js`：通过
- `node --check assets/recommend_v2.js`：通过
- `git diff --check`：通过

## 同步过的文档

已同步展示板、数据、API、导出文档及 AI 文档索引；未修改源代码或测试。
