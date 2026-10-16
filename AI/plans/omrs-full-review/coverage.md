# OMRS 全面检查覆盖清单

执行者：Codex 主代理与 A／B／C 三个子代理，完整模式。此文件记录本次检查的实际范围；总体合同见 `plan.md`，完成结论见后续 `report.md`。

## 基线

- 审计启动：2026-10-16；Git 参考 `98ca91f7f5011cab4e9e8b7e450cbfb7cc8072df`，包括启动时未提交与未跟踪业务实现。
- 工作区清单：1505 条路径，包含删除状态；清单 SHA256 `b43a44b44783eb0d32784a1806426d734a14fa37843445732bc844581bbb8372`。
- 原始清单、开工 diff 与状态存放于 `/tmp/omrs-full-review-20261016-_lotdof0/`。真实题库、私有运行数据、虚拟环境与缓存不进入源码快照。
- Python 3.13.5、Node v22.23.0、Git 2.47.3；Playwright、pytest、Pillow、MCP SDK 可用。Chromium 自启动探测成功，可信本机 CDP 可连接；未将模块存在视为功能通过。

## 功能与目录覆盖

| 功能域 | 源码／文档范围 | 静态责任 | 本轮状态 |
|---|---|---|---|
| 启动、登录、外壳与配置 | CLI、server／HTTP、web_assets；core／shell／settings | B、C；主代理 | 核查中 |
| 题库、目录、详情与标记 | question／catalog／labels／label_plan；questions／catalog／domain | B、C | 核查中 |
| 录入、收件箱、上传与草稿 | creation／inbox／uploads／drafts；create／草稿 UI | B、C | 核查中 |
| 作业帮与独立网关 | omrs/zuoyebang、对应 HTTP／页面；services/zuoyebang | B、C | 核查中 |
| 调度、算法、练习与反馈 | scheduling／sessions／feedback／practice；schedule／instant／feedback | B、C | 核查中 |
| 展示板、导出与打印 | board／exporting／export_fonts／模板；board domain／页面 | B、C | 核查中 |
| AI 助手、模型、审核中心 | agent／llm／ai_assist／ai_review／question_update；assistant／ai-review | B、C | 核查中 |
| MCP、Key 与协议调用 | mcp 及独立回执存储／权限 | B；主代理 | 核查中 |
| 统计、历史、复盘与报告 | analytics／stats／reports／runtime；dashboard／records 系列 | B、C | 核查中 |
| Ledger、正文与生命周期 | actor／ledger／projection／data_repository／locking／backup／lifecycle | B；主代理 | 核查中 |
| 标注、训练面板与检测服务 | annotate／trainpanel／traincontrol／system_resources；tools/boxdetect、services/boxdetect | B、C | 核查中 |
| CLI、仓库工具与交付 | 全部 CLI、源码导出、pack_for_ai、依赖／vendor／忽略规则 | A；主代理 | 核查中 |
| 文档完整性与事实同步 | 根 README／AGENTS、AI 全部分册与计划、两个服务文档 | A；其余代理按域复核 | 核查中 |

## 测试入口清单

已盘点根 E2E 45 个 Python 文件：纸面模块为辅助模块，不单独计通过；boxdetect 真实模型验证依赖未提供的冻结材料；网关联调要求 `--out`，独立显式运行；其余实际入口逐一核查。部分脚本的 SKIP 仍返回 0，最终结果须读取日志。

固定临时截图路径存在既有产物，不能覆盖。可配置项按脚本独立设置；写死路径的少数入口仅在仓库外执行输出路径常量重定向，保留原源码哈希、转换差异和实际结果，不修改断言、等待或业务逻辑。两个作业帮入口分别使用独立目录，避免覆盖 `checks.json`。

根 unit／UI／升级门禁、两个独立服务单测已安排；后续继续 E2E、两种双服务联调、独立网关浏览器、完整与补充视觉、CLI 和重要发现独立复核。执行记录逐项存于仓库外 `records/`，最终汇总到本计划 `validation.json`。
