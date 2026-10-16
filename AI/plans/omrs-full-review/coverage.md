# OMRS 全面检查覆盖清单

执行者：Codex 主代理与 A／B／C 三个子代理，完整模式。P0–P3 已完成；此文件记录实际范围，总体合同见 `plan.md`，完成结论见 `report.md`。

## 基线

- 审计启动：2026-10-16；Git 参考 `98ca91f7f5011cab4e9e8b7e450cbfb7cc8072df`，包括启动时未提交与未跟踪业务实现。
- 工作区清单：1505 条路径，包含删除状态；清单 SHA256 `b43a44b44783eb0d32784a1806426d734a14fa37843445732bc844581bbb8372`。
- 原始清单、开工 diff 与状态存放于 `/tmp/omrs-full-review-20261016-_lotdof0/`。真实题库、私有运行数据、虚拟环境与缓存不进入源码快照。
- Python 3.13.5、Node v22.23.0、Git 2.47.3；Playwright、pytest、Pillow、MCP SDK 可用。Chromium 自启动探测成功，可信本机 CDP 可连接；未将模块存在视为功能通过。

## 功能与目录覆盖

| 功能域 | 源码／文档范围 | 静态责任 | 本轮状态 |
|---|---|---|---|
| 启动、登录、外壳与配置 | CLI、server／HTTP、web_assets；core／shell／settings | B、C；主代理 | HTTP/PIN与外壳静态、根边界门禁、配置E2E；真实反代未测 |
| 题库、目录、详情与标记 | question／catalog／labels／label_plan；questions／catalog／domain | B、C | 稳定身份/标记链路与题库/目录E2E；R02/R06/R07/R08 |
| 录入、收件箱、上传与草稿 | creation／inbox／uploads／drafts；create／草稿 UI | B、C | 上传/草稿/回执关键分支及E2E；R04；草稿补当前导航与选题后82/82、P4补验24/24 |
| 作业帮与独立网关 | omrs/zuoyebang、对应 HTTP／页面；services/zuoyebang | B、C | 主站78/78、服务页27/27、直连21/21、前缀23/23、网关单测63、独立浏览器6及包HTTP4；真实供应商未测 |
| 调度、算法、练习与反馈 | scheduling／sessions／feedback／practice；schedule／instant／feedback | B、C | 算法/Session/反馈门禁及E2E；R01/R05/R16/R17 |
| 展示板、导出与打印 | board／exporting／export_fonts／模板；board domain／页面 | B、C | 关键后端补查/展示板浏览器/两打印/离线HTML；真实出纸未测 |
| AI 助手、模型、审核中心 | agent／llm／ai_assist／ai_review／question_update；assistant／ai-review | B、C | 审核/权限/晚到响应与历史链路；R02/R06；助手展开列表后两专项及审核48项补验通过 |
| MCP、Key 与协议调用 | mcp 及独立回执存储／权限 | B；主代理 | Key生命周期与协议实际执行；CLI与MCP/HTTP回执门禁 |
| 统计、历史、复盘与报告 | analytics／stats／reports／runtime；dashboard／records 系列 | B、C | 统计/历史/复盘/报告静态及真实页面E2E |
| Ledger、正文与生命周期 | actor／ledger／projection／data_repository／locking／backup／lifecycle | B；主代理 | Ledger/正文/恢复/并发关键分支与根门禁；R03/R04 |
| 标注、训练面板与检测服务 | annotate／trainpanel／traincontrol／system_resources；tools/boxdetect、services/boxdetect | B、C | 标注/训练页面与合成控制、服务10单测；R09；默认目录隔离遗漏及安全重跑见报告§6，真实模型未测 |
| CLI、仓库工具与交付 | 全部 CLI、源码导出、pack_for_ai、依赖／vendor／忽略规则 | A；主代理 | 显式53CLI/110检查，109通过1缺陷；打包实测/规则审查 |
| 文档完整性与事实同步 | 根 README／AGENTS、AI 全部分册与计划、两个服务文档 | A；其余代理按域复核 | 128份清点/重点事实深读，18组＋2API勘误、六计划索引已修 |

## 测试入口清单

已盘点根 E2E 45 个 Python 文件：纸面模块为辅助模块，不单独计通过；boxdetect 真实模型验证依赖未提供的冻结材料；网关联调要求 `--out`，独立显式运行；其余实际入口逐一核查。部分脚本的 SKIP 仍返回 0，最终结果须读取日志。

固定临时截图路径存在既有产物，不能覆盖。可配置项按脚本独立设置；写死路径的少数入口仅在仓库外执行输出路径常量重定向，保留原源码哈希、转换差异和实际结果，不修改断言、等待或业务逻辑。两个作业帮入口分别使用独立目录，避免覆盖 `checks.json`。

根 unit／UI／升级、两服务单测、两种联调、网关浏览器／独立包、CLI 和重要发现独立复核均已执行。42 个原始独立 E2E 为35退出0／7非零／0显式SKIP，补导航或环境前提后的重跑单列，不覆盖首次失败。视觉有效当前112状态、参考48状态，另24个空库／窄屏状态；4个默认训练目录来源不明状态作废、删除图像后受控替代。执行记录逐项存于仓库外 `records/`，汇总见 `validation.json`，失败归因与未验证限制见报告。

## 子代理实际交付

A：128 份 AI 文档清点及重点契约深读，仓库 tracked／untracked／ignored、237 vendor 哈希、打包规则、53 条真实 CLI。B：148 份 Python AST／符号盘点，79 份重要区域阅读，四项合成复现及 C 浏览器证据交叉核对。C：18 个页面／入口，两个真实模块 Node 复现、三项真实浏览器问题复核、24 组空库状态／窄屏截图。三代理均未修改共享仓库。

盘点不是逐行审计。逐文件范围、源码哈希、仅盘点项、测试对应和验证限制均在仓库外 agent-a／agent-b／agent-c 的 coverage.json；validation.json 保留其证据位置与哈希。主代理独立重跑 B 四项、C 两项 Node，另做 HTTP、源码实际归档、CLI Session 与常规规模性能测量。
