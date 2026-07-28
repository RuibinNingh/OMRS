# OMRS 仓库协作准则

## 开始任务前

- 先读 `AI/README.md`，再按任务范围读取对应的 `AI/*.md`。
- 先运行 `git status --short`，识别并保留用户已有的未提交改动；不得把不属于本任务的改动覆盖、还原或顺手整理。
- 判断现状时以当前工作区代码、测试和配置为准，以 Git 历史解释设计意图；若它们与 AI 文档冲突，必须在本任务内把文档同步到可验证的当前行为。

## 每次任务的强制文档收尾

凡任务在仓库中产生持久化改动，交付前都必须完成以下事项：

1. 用 `git diff --name-status`（必要时结合相关提交历史）复核本任务的实际变化。
2. 更新受影响的模块文档；不得只改代码而留下已知过时的 AI 文档。
3. 在 `AI/logs/` 新建本次任务的 `YYYY-MM-DD_<topic>.md` 记录，并在 `AI/logs/log.md` 增加索引。日志至少写清行为变化、影响文件和验证结果。
4. 同一逻辑任务跨多轮继续工作时更新同一份任务日志；任务已经交付后出现的新任务，必须使用新主题名或 `-2`、`-3` 后缀，不得混写回旧任务。
5. 历史日志只允许在纠正该日志自身的事实错误时追加明确标注的勘误；不得删除、重写历史事实，或把后续任务伪装成旧日期的原始内容。
6. 运行与改动风险相称的检查，并确保日志中的验证描述与实际执行结果一致。

只读调查、答疑或没有产生仓库改动的任务不应为了留痕而制造空提交或空日志；交付时明确说明“未修改仓库”即可。

## 代码到文档的对应关系

| 改动范围 | 必查/必更新文档 |
|---|---|
| `omrs/scheduling.py`、记忆与推荐规则 | `AI/algorithm.md` |
| `omrs/server.py`、HTTP 请求/响应；`omrs/ai_assist.py` | `AI/api.md`，AI 配置或存储变化同时更新 `AI/data.md` |
| `omrs/analytics.py`、`omrs/stats.py`、报告指标 | `AI/api.md`、`AI/frontend.md`；持久化或导出格式变化同时更新 `AI/data.md` |
| `omrs/reports.py`、报告托管 | `AI/api.md`、`AI/data.md`、`AI/frontend.md` |
| CSV、Ledger、Markdown、配置或持久化格式 | `AI/data.md`、必要时 `AI/ledger.md` |
| `omrs/exporting.py`、`omrs/export_templates/`、导出入口 | `AI/export.md`，接口变化同时更新 `AI/api.md` |
| `assets/`、`omrs_dashboard.html`、前端交互 | `AI/frontend.md` |
| 报告、优化、跨模块架构 | 对应 `AI/*.md`，并复核 `AI/README.md` 的索引与项目摘要 |
| 用户可见行为、启动/安装命令、目录、依赖或版本 | 同步根 `README.md` |
| `pack_for_ai.bat` | 确保根 `AGENTS.md`、全部 `AI/*.md` 和 `AI/logs/` 被打包，并同步根 `README.md` 的打包说明 |
| 测试、工具或协作规则 | 相关模块文档；任何持久化改动仍须写本次任务日志 |

详细维护流程、命名和日志模板以 `AI/README.md` 为准。
