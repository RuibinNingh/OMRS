# 2026-09-05 功能缺陷修复

## 变更摘要

同步本次功能修复后的行为契约：AI 分类读取公开的标记定义查询；推荐数量的负值按 0 处理；推荐和 Session 管理按 `Status == "active"` 排除进行中的题目，不按创建时间隐式套用 7 天过期；推荐 v2 使用私有筛选函数，避免覆盖公共筛选 API；展示板默认题间留白为 6 行，并规范化 `binding_marks`，前端与导出模板支持 `none`、`3hole`、`26hole` 孔位显示。

## 影响文件

- `omrs/ai_assist.py`：分类提示使用 `list_label_defs()`。
- `omrs/scheduling.py`、`omrs/server.py`、`omrs/sessions.py`：推荐数量边界及 active Session 排除契约。
- `assets/recommend_v2.js`：筛选函数私有化。
- `omrs/boards.py`、`assets/board.js`、`omrs/export_templates/board.js`：展示板留白与孔位设置、绘制。
- `tests/test_recommendations.py`、`tests/test_recommend_v2_filters.js` 及 AI taxonomy 测试：回归覆盖。
- 同步文档：`AI/api.md`、`AI/algorithm.md`、`AI/frontend.md`。

## 验证

- `python3 -m unittest discover -s tests -v`：56 passed。
- `for f in tests/*.js; do node --test "$f"; done`：全部通过。
- `python3 -m compileall -q omrs`：通过。
- `node --check assets/recommend_v2.js`：通过。
- `node --check assets/board.js`：通过。
- `git diff --check`：通过。
- `pytest` 未执行，环境没有 pytest。

## 同步过的文档

- `AI/api.md`：推荐数量边界、Session active 生命周期、AI 标记定义查询。
- `AI/algorithm.md`：推荐数量归一化与 active Session 规则。
- `AI/frontend.md`：推荐 v2 私有筛选 API 与脚本索引。

## 勘误（2026-09-05）

本日志初稿误记展示板支持 `binding_marks` 且默认 `gap_lines=6`。按产品需求及当前代码，展示板不绘制打孔标记，仅保留 `binding_mm` 装订边距，`gap_lines` 默认值为 2；修正详情见同日 `functional-bug-fixes-2` 日志。
