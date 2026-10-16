# 计划文件夹

跨多轮、多个维护者接力的任务，都在这里放一个文件夹。文件夹本身就是这份计划：总纲、执行说明和进度都在里面，随源码包导出。下一个执行者打开包就能看到，不依赖任何包外的交接文档。

写计划的方法（规划模式的流程、执行说明的模板）只写在根目录 `AGENTS.md` 的「规划模式」一节，本文件只管目录约定。

## 目录约定

```
AI/plans/<计划名>/
├── plan.md                       总纲：目标、架构、分期、验收、决策点。只在计划本身变更时修改
├── exec-<YYYY-MM-DD>[-主题].md    执行说明：规划模式写给执行者的一批工作（可以有多份）
└── progress.md                   进度：当前阶段、基线、门禁计数、各期状态、写法与坑、下一步
```

- **计划名**：用英文小写加连字符，与任务日志主题的前缀一致。例如 `frontend-rearch` 对应 `AI/logs/2026-09-25_frontend-rearch-p4.md`。
- **`plan.md` 的两种写法**：
  - 一次会话就能执行完的小计划，`plan.md` 直接按执行说明的模板写，不必另写 `exec-*.md`；
  - 需要分多批执行的，`plan.md` 写总纲，每批一份 `exec-*.md`。
- **执行说明的维护**：执行说明由规划者维护，执行者不改它（笔误除外）。执行中的偏差写进任务日志和 `progress.md`；需要改目标或范围时，由规划者另写一份新的执行说明，或改 `plan.md` 并登记。
- **`progress.md` 的状态块**：前 15 行必须有 `> **状态**` 块，写目标、阶段、基线、下一步、更新五项，每项一行。「下一步」写明执行者、运行模式，以及要读的执行说明。
- **`tests/check_docs.py` 的检查**：它检查 `plan.md` 和 `progress.md` 都存在、状态块完整。计划文件夹里的所有文档都描述未来，其中引用的路径不做存在性检查；但 `progress.md` 的「已完成」部分只写已经存在的东西。
- **进度只记在 `progress.md`**：各期任务日志写本期做了什么、怎么验证的；`progress.md` 写整件事走到哪、下一步做什么。两边不重复抄写细节，互相指路即可。

## 执行者怎么用

1. **开工前：** 读 `progress.md` 的状态块和「下一步」。「下一步」指向执行说明时，通读它；再按需读 `plan.md` 的对应章节。执行规则见 `AGENTS.md`「按执行说明执行」。
2. **每次提交或每轮收尾：** 更新 `progress.md`，包括状态块、分期表、门禁计数、遗留和下一步。没做完也要写清停在哪里。
3. **计划本身要改时**（范围、顺序、流程）：先改 `plan.md` 的对应章节，再在 `progress.md`「计划变更」表记一行：日期、改了什么、依据（用户原话或实测）。
4. **全部完成后：** 把状态块的阶段写成「已完成」，文件夹留在原处作为记录。不再有人读的旧计划，可以整体移到 `AI/plans/archive/`。

不写 `UPGRADE-*.md`、`HANDOFF-*.md` 这类包外交接文档。

## 现有计划

| 计划 | 状态 | 说明 |
|---|---|---|
| `ai-agent/` | A–H 已合入并部署 v1.28.1；外部验收待核实 | 真实模型五类对话及生产 Ledger 前后校验未见完成记录；B2、F3 后续；见 `ai-agent/progress.md` |
| `ai-label-organizing/` | 阶段 0–5 已完成并随 v2.3.8 发布 | 整批标记归类、审核与撤销；见 `ai-label-organizing/progress.md` |
| `board-motion/` | 实现与门禁已完成；提交／汇报按 progress 核实 | 展示板翻页和切板过渡；题库选择器基线问题另记；见 `board-motion/progress.md` |
| `board-redesign/` | UI 打磨已部署并验收 | 展示板布局、保存与预览；实体出纸按使用验收；见 `board-redesign/progress.md` |
| `entry-background/` | 已完成 | 入口图片／视频背景配置及隔离验证；见 `entry-background/progress.md` |
| `omrs-stabilization/` | v1.35.0 实现、部署、正文回填与推送已完成 | 数据完整性与并发巩固；历史不可取回缺口不伪造恢复；见 `omrs-stabilization/progress.md` |
| `frontend-rearch/` | P0–P8、终检及部署已完成 | 前端架构、设计系统与 UI；后续清理已在 v1.28.1 完成，详见 `frontend-rearch/progress.md` |
| `ai-draft/` | P1–P4 已完成并部署 v1.30.0 | 主 AI 聊天录题、草稿审核入库、框选与独立训练任务；执行结果与发布状态见 `ai-draft/progress.md` |
| `box-detect/` | 已完成并部署v1.32.0 | 训练、内容评测、复核面板及服务启停／模型显式应用与回退已交付，见progress.md |
| `boxdetect-service/` | 已完成并部署 v2.7.0 | 源码 00b44d8、4cef0fe，发布 6f38c87 已推main；三服务同仓、原模型保持，18组隔离和49项生产检查通过 |
| `v2.0.0/` | P0–P7 本地实现与隔离门禁完成，已部署 | 审核、录入、助手、练习与用量；真机、真实供应商及人工计时仍待验收，见 `v2.0.0/progress.md` |
| `mcp-integration/` | 扩展及后续维护已部署至 v2.3.6 | 工具说明与录题规范、网页确认及安全导出；当前状态与外部验收限制见 `mcp-integration/progress.md` |
| `history-redesign/` | 已部署 v2.1.0，随 ba6501b 发布 | 学习与变更 / 系统运行分区时间线、真实 MCP 调用与草稿入库双向关联，见 `history-redesign/progress.md` |
| `omrs-audit-repair/` | 全部完成，已部署v2.2.0并推GitHub | 十九项修复与治理、万题十万反馈容量、真实副本迁移/恢复及生产验收；执行者Codex完整模式，见progress.md |
| `mcp-review-sessions/` | 已部署v2.2.1并推送GitHub | 正式调度创建、查询增强及v2.2.1；执行者Codex完整模式，见progress.md |
| `ai-review-center/` | 已部署v2.3.0并推送GitHub | 统一 MCP/助手业务写审核、草稿迁入和安全正式改题；执行者Codex完整模式，见progress.md |
| `zuoyebang/` | 已完成v2.4.1并部署 | 作业帮账号、实时摄像头、图片搜题、1080完整后端渲染与核对入库；执行者Codex完整模式，见progress.md |
| `zuoyebang-service/` | 已同仓部署v2.5.0并推GitHub | 同仓网关、Key与来源IP审计及OMRS本地／外部连接；执行者Codex完整模式，见progress.md |
| `zuoyebang-search-ui/` | 已合入main、部署v2.6.0并推GitHub | 取图搜题／候选自动预览与状态服务面板合并；14组隔离及43项生产检查通过，执行者Codex完整模式，见progress.md |
| `omrs-full-review/` | 检查完成，17项发现已登记 | 文档、仓库卫生、适度安全与全功能链路；原始失败及补验均保留，见 `omrs-full-review/progress.md` |
| `omrs-maintenance/` | 本地维护完成，来源限制保留 | 承接全面检查R01–R17；Codex主代理及三个子代理，完整模式；见 `omrs-maintenance/progress.md` |
