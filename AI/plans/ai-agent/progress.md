# AI 助手：进度

> **状态**
> - 目标：给 OMRS 加内置 AI 助手（自写 Harness、服务端权限、正文入账、按运行撤销、聊天面板），总纲见同目录 `plan.md`
> - 阶段：**A–H 完成（v1.28.0，受限模式）**；I（部署）待用户授权。推迟项：B2（op_id 幂等）、F3 看图、MCP
> - 基线：导出包 `OMRS-source-sanitized-20260927T230601Z`（v1.27.0），受限模式本地基线提交 `fedd7f1`
> - 下一步：Codex · 完整：① 按任务日志 `AI/logs/2026-09-28_ai-agent.md`「合入」应用 `changes-2026-09-28-ai-agent.patch` 并提交；② 本机补做 `--write-log-index`、全量 E2E、`tests/visual/run.py --ref` 对比；③ 用真实模型（百炼或 DeepSeek）在设置页「测试连接」后走一遍五个典型对话；④ 等用户授权再部署
> - 更新：2026-09-28，Claude（对话内，受限模式）完成 A–H，门禁与测试见任务日志「验证」

## 1. 分期状态

| 期 | 内容 | 状态 | 落点 |
|---|---|---|---|
| A | Ledger 原子追加、进程写锁与 503、ThreadingMixIn、删 Skills | 完成 | `omrs/ledger.py`、`omrs/locking.py`、`omrs/cli.py`、`omrs/server.py` |
| B | 写入来源 `agent`（B1） | 完成；B2 幂等推迟 | `omrs/actor.py` |
| C | blobs、`question.content_update`、回填、写前对齐与 409、历史 / 取回 / 还原接口 | 完成（接口，无界面） | `omrs/content_history.py` |
| D | OpenAI 兼容客户端、厂商兼容数据、假模型、`agent_*` 配置 | 完成 | `omrs/llm/`、`omrs/agent/config.py` |
| E | 循环、`agent.db`、权限与预算、运行时与接口、系统提示词 | 完成 | `omrs/agent/` |
| F | 只读工具 7 个 | 完成；看图推迟 | `omrs/agent/tools/read.py` |
| G | 按运行撤销、可撤销工具 2 个、需确认工具 7 个 | 完成 | `omrs/agent/revert.py`、`omrs/agent/tools/write.py` |
| H | 助手页（按示例 UI 移植）、设置页分区 | 完成 | `assets/app/features/assistant/`、`assets/app/features/settings/agent*.js` |
| I | 文档、版本 v1.28.0；部署 | 文档完成；部署待授权 | `AI/agent.md`、`AI/frontend/assistant.md` |

## 2. 与总纲的偏差

- 示例 UI 里用行内 `style=` 画的条形、瀑布、火花线改为 SVG 属性（仓库 UI 门禁零容忍）；题目悬停预览浮层未移植，点引用直接打开仓库自带的题目弹窗。
- AI 打标记逐题记显式的 `question.metadata_update`（经 `write_question`，带前后正文哈希），不走工作区扫描的 `self_check`；用户在题目库打标记的路径不变。
- 聊天正文用页面自带的轻量 Markdown（引用芯片、表格、公式），不复用 `domain/question/markdown.js` 的整套渲染；公式仍走同一个 KaTeX 入口。
