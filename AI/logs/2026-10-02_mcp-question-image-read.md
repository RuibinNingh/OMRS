# 2026-10-02 MCP 题图按需读取

## 背景

用户要求执行「MCP 题图按需读取计划」，终点为「本地 SDK 验收即可」。执行者 Codex，完整模式；规划与开工 HEAD 为 968fdfb，工作区已有另一任务的历史记录改造。开工保存相关文件与状态快照，保护全部已有改动。历史任务随后独立提交为 73e34fd，本批实际提交与累计 diff 基线采用该提交，未纳入历史任务增量。本任务不发布、推送或升级版本。

执行说明见 AI/plans/mcp-integration/exec-2026-10-02-question-image-read.md。

## 行为变化

I1 新增按共享题目图片下标、安全读取附件原件的领域函数；上传完整解码校验抽为共享纯函数，延迟导入 Pillow。读取只接受服务端从 images[] 选出的 basename，拒绝不安全目录、链接、非普通文件、重名、超限和损坏图片。

I2 新增 get_question_image，仅 omrs:read 可用；UID 与严格整数下标必填，成功只返回单个原生 ImageContent。实时 Key 在读取前和返回前复查；工具发现为 10/1/11 项，内置助手注册表与草稿写权限不变。运行记录登记“读取题图”及 image_index，不保存图像或 Base64。

I3 将题图读取闭环纳入真实 SDK / 浏览器隔离验收：先读取正式合成题目的题目与答案图片，检查 MIME、原字节及学习 Ledger 提交不变，再执行既有草稿和 Key 管理浏览器路径。

## 影响文件

新增 omrs/question_images.py、tests/test_question_images.py；omrs/mcp/server.py 只抽取上传校验，不覆盖历史记录包装层。I1 更新 AI/mcp.md 的领域校验说明、本计划总纲与进度，新增执行说明与本日志。I2 修改 omrs/runtime_records.py 与 MCP 适配，补 MCP 策略、真实协议和运行记录测试；同步 AI/mcp.md、AI/api.md、AI/security.md、AI/agent.md、AI/runtime.md 与 README.md。

I3 修改 tests/e2e/mcp.py，同步 AI/environment.md 和 AI/frontend/architecture.md 的验收路径、同一任务日志、MCP 进度与 AI/plans/README.md 计划索引；AI/logs/log.md 由门禁脚本生成。实际累计文件清单以 git diff 73e34fd --name-status 复核，全部增量属于本批。

## 验证

规划阶段已实际执行 MCP 专项 60/60、共享读题与运行记录 21/21，通过。I1 首次专项运行 77 项，其中截断 PNG 校验抛 SyntaxError 未归一化；已将此类解码异常转为安全 ValueError。单独题图测试重跑 17/17，随后题图/共享查询/MCP/运行记录专项 98/98 通过，无 SKIP。

I1 日志索引已生成，累计 docs 基线 73e34fd 检查 81 个文档、0 问题、3 条既有大文件提醒；git diff --check 通过。

I2 题图/共享查询/MCP/运行记录专项 107/107 通过，无 SKIP。新真实 SDK 用例验证 PNG、JPEG 尾数据、GIF、多帧 GIF、正文截断后引用、严格参数、三类 scope、8 MiB 原字节输出及吊销后拒绝；运行记录无图像落库。首跑仅新吊销用例未覆盖 SDK TaskGroup 退出的 401 异常，已按既有会话断言模式修正并重跑。

I2 当前切片和累计基线 73e34fd 的 docs 均检查 81 个文档、0 问题、3 条既有大文件提醒；git diff --check 通过。专项运行出现 SQLite ResourceWarning，测试仍全通过，本批不扩展连接管理重构。

本批已实际执行下列命令，均清除生产控制环境变量并只使用临时 Vault 和随机高端口：

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_question_images tests.test_agent_tools tests.test_mcp tests.test_mcp_keys tests.test_mcp_http tests.test_mcp_protocol tests.test_mcp_draft_atomic tests.test_runtime_records -q
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/mcp.py
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest discover -s tests -p 'test_*.py' -q
```

上述专项在 I2 收尾执行，107/107；I3 真实 SDK / 浏览器 39/39（SDK 6 项、既有浏览器 33 项）；Python 全量 527/527，耗时 90.639 秒。均为退出码 0，无 SKIP。SDK 测试使用官方 mcp 1.28.1，PNG/JPEG 尾数据与 GIF 经 Base64 解码和原件逐字节相同，不产生结构化图片 JSON。

全量输出含 SQLite/文件句柄 ResourceWarning，以及后台 HTTP 授权响应的 BrokenPipeError；最终 unittest 为 OK。本批未修改该 Web 授权路径，未断定诊断的具体成因，未扩展连接管理或 HTTP 异常处理重构。

I3 已实际执行文档收尾：

```bash
python3 tests/check_docs.py --write-log-index
python3 tests/check_docs.py --diff HEAD
python3 tests/check_docs.py --diff 73e34fd
git diff --check
```

日志索引生成成功；两次文档检查均为 81 文档、0 问题、3 条既有大文件提醒，退出码 0。提醒为 AI/api.md、AI/plans/frontend-rearch/exec-2026-09-26-codex.md 与 AI/plans/v2.0.0/plan.md，本批不扩展文档拆分。git diff --check 通过。

未执行：Windows 实机联调（便携路径分支已在 Linux 测试）；Node、UI、对比度及视觉全仓门禁（本批没有前端源码/样式改动，已执行相关真实浏览器回归）。生产发布、GitHub 推送、Tunnel、目标 ChatGPT 账户联调与版本升级不在本批范围，未执行。

## 提交与终点

I1 提交 86d3937：安全题图读取及共享原件校验；I2 提交 1af2263：按题目下标返回 MCP 原生图片；I3 由本次提交交付真实 SDK / 浏览器闭环、全量与文档验收。I1–I3 全部完成，本批无剩余实施步骤，版本保持 v2.1.0。外部发布及账户联调单列后续。

## 实现调整

定位使用 POSIX 目录文件描述符固定读取层级；无此能力的平台采用逐级目录/文件身份核对，拒绝重解析点。完整校验保留原字节，不复用只检查图片头且无界读取的导出函数。

为拒绝 JSON Schema 允许的 1.0，下标启用 SDK 严格整数模型；通用协议边界在 schema 后校验既有参数模型，失败归一化为 invalid_arguments，不回显参数。既有查询、创建和重试回归全部通过。

I3 收尾复核发现纯空白 UID 原先返回 invalid_request，未满足参数错误使用 invalid_arguments 的契约；为新工具的 UID schema 补非空白约束，并同时修正协议断言、增加普通及 Unicode 空白的校验覆盖。专项重新运行 107/107；只合入尚未推送的 I2 提交，未改目标与权限边界。

修正后再次执行同一 SDK / 浏览器命令，39/39；再次执行 Python 全量命令，527/527，耗时 90.300 秒。两次退出码均为 0，无 SKIP；因此最终验收对应修正后的代码。
