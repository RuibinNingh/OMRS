# 2026-09-30 题目创建信息与助手检索增强

## 背景

用户要求在题目详情弹窗的“记录”下面显示录入日期和创建时间，题库支持按创建日期排序，AI 助手 `search_questions` 支持组合筛选与最多三级自定义排序。本轮按完整模式直接在本机 Git 工作区实现；工作区在开工前已有其他任务的未提交改动，均保留。

## 行为变化

- `question_projection.created_at` 为可空字段，旧库启动自动补列；首次 `question.create` / `question.create_external` 使用 Ledger 提交时间，重复创建事件、迁移、元数据修改、停用和恢复不改变首次时间，`legacy.bootstrap` 题目保持空值。
- `/api/stats.items[]`、`/api/question` 和 AI `get_question` 返回 `entry_date` 与 `created_at`。新建题目把录入日期写入 Markdown 元数据；外部扫描题的创建时间是首次纳入 Ledger 的时间。
- 完整 qview 在记录模块之后显示“录入日期”和按现有 Ledger 时区格式化的“创建时间”，没有练习记录也显示；画廊、即时练习等缩略视图隐藏该区块，缺失值显示“—”。
- 题库排序下拉增加“创建日期 ↑ / ↓”，优先精确时间，旧题回退录入日期，空值排最后并按 UID 稳定收尾。
- `search_questions` 增加难度、到期、创建日期范围和多标记 any/all 筛选；独立条件按 AND 组合，兼容旧 `label`。支持最多三级标量字段排序，空值排最后、UID 稳定收尾，排序在分页之前执行；未传排序保留科目 / 分类 / UID 顺序。更新系统提示词，明确自定义检索使用该工具，推荐工具仍保持固定复习优先级。

## 影响文件

- 后端：`omrs/ledger.py`、`omrs/projections.py`、`omrs/creation.py`、`omrs/stats.py`、`omrs/scheduling.py`、`omrs/agent/tools/read.py`。
- 前端：`assets/app/domain/items.js`、`assets/app/domain/question/{index.js,view.js,qview.css}`、`assets/app/features/questions/state.js`。
- 测试：`tests/test_question_creation_metadata.py`、`tests/app/question.test.mjs`、`tests/app/questions.test.mjs`。
- 文档：`AI/api.md`、`AI/agent.md`、`AI/algorithm.md`、`AI/data.md`、`AI/ledger.md`、`AI/frontend/qview.md`、`AI/frontend/library.md`、`omrs/agent/prompts/system.md`。

## 验证

已实际执行：

- `python3 -m unittest discover -s tests -q`：417 个测试通过；目标后端测试 7 个也单独通过。
- `python3 -m unittest tests.test_question_creation_metadata tests.test_agent_tools tests.test_question_records -q`：13 个通过；覆盖旧投影补列、新建 / 外部扫描创建时间、重复创建保持首次时间、移动不变、旧题回退、组合筛选和排序校验。
- `node --test tests/app/question.test.mjs tests/app/questions.test.mjs tests/app/assistant.test.mjs`：70 个通过。
- `python3 tests/app/run_browser.py`：33/33 通过；`python3 tests/e2e/assistant.py`：58/58 通过。
- `python3 tests/check_ui.py`、`python3 tests/check_contrast.py`、`python3 tests/check_docs.py --diff HEAD`：通过（仅保留既有文件过大提醒）。
- `python3 tests/visual/run.py --ref HEAD ...` 首次因测试脚本从未解锁的根路径调用 `window.__omrs.router` 而中止；用同一脚本、同一 fixture 在隔离浏览器中补上 `?unlocked=1#/dashboard` 后重跑 `questions` 桌面 / 手机浅色对比：脚本错误 0、差异 0/2，审计显示页面横向溢出 0、行内样式 0、小目标 0。
- `python3 tests/e2e/questions.py`：工作区原有启动 READY、Esc / 筛选状态、弹窗浮层和审计流程仍有失败，结果为 47/58；失败集中在测试初始化和既有流程，服务端 `/api/stats` 及后续多项题库操作仍通过，未为本需求改动无关逻辑。

未执行：

- 未连接生产服务、未修改 systemd 或真实题库；未执行部署和远端浏览器验证。

## 合入

本轮为完整模式实现，提交按垂直切片包含后端投影 / API、AI 检索、前端 qview / 题库排序、测试、模块文档和本日志。生产重启、推送和合入远端仍需单独授权。
