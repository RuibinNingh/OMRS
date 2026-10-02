# 2026-10-02 MCP 题图按需读取

## 背景

用户要求执行「MCP 题图按需读取计划」，终点为「本地 SDK 验收即可」。执行者 Codex，完整模式；规划与开工 HEAD 为 968fdfb，工作区已有另一任务的历史记录改造。开工保存相关文件与状态快照，保护全部已有改动。历史任务随后独立提交为 73e34fd，本批实际提交与累计 diff 基线采用该提交，未纳入历史任务增量。本任务不发布、推送或升级版本。

执行说明见 AI/plans/mcp-integration/exec-2026-10-02-question-image-read.md。

## 行为变化

I1 新增按共享题目图片下标、安全读取附件原件的领域函数；上传完整解码校验抽为共享纯函数，延迟导入 Pillow。读取只接受服务端从 images[] 选出的 basename，拒绝不安全目录、链接、非普通文件、重名、超限和损坏图片。

I2 新增 get_question_image，仅 omrs:read 可用；UID 与严格整数下标必填，成功只返回单个原生 ImageContent。实时 Key 在读取前和返回前复查；工具发现为 10/1/11 项，内置助手注册表与草稿写权限不变。运行记录登记“读取题图”及 image_index，不保存图像或 Base64。

## 影响文件

新增 omrs/question_images.py、tests/test_question_images.py；omrs/mcp/server.py 只抽取上传校验，不覆盖历史记录包装层。I1 更新 AI/mcp.md 的领域校验说明、本计划总纲与进度，新增执行说明与本日志。I2 修改 omrs/runtime_records.py 与 MCP 适配，补 MCP 策略、真实协议和运行记录测试；同步 AI/mcp.md、AI/api.md、AI/security.md、AI/agent.md、AI/runtime.md 与 README.md。

## 验证

规划阶段已实际执行 MCP 专项 60/60、共享读题与运行记录 21/21，通过。I1 首次专项运行 77 项，其中截断 PNG 校验抛 SyntaxError 未归一化；已将此类解码异常转为安全 ValueError。单独题图测试重跑 17/17，随后题图/共享查询/MCP/运行记录专项 98/98 通过，无 SKIP。

I1 日志索引已生成，累计 docs 基线 73e34fd 检查 81 个文档、0 问题、3 条既有大文件提醒；git diff --check 通过。

I2 题图/共享查询/MCP/运行记录专项 107/107 通过，无 SKIP。新真实 SDK 用例验证 PNG、JPEG 尾数据、GIF、多帧 GIF、正文截断后引用、严格参数、三类 scope、8 MiB 原字节输出及吊销后拒绝；运行记录无图像落库。首跑仅新吊销用例未覆盖 SDK TaskGroup 退出的 401 异常，已按既有会话断言模式修正并重跑。

I2 当前切片和累计基线 73e34fd 的 docs 均检查 81 个文档、0 问题、3 条既有大文件提醒；git diff --check 通过。专项运行出现 SQLite ResourceWarning，测试仍全通过，本批不扩展连接管理重构。

未执行：浏览器回归及 Python 全量，留待 I3。生产、推送和目标 ChatGPT 账户联调不在授权范围，未执行。

## 实现调整

定位使用 POSIX 目录文件描述符固定读取层级；无此能力的平台采用逐级目录/文件身份核对，拒绝重解析点。完整校验保留原字节，不复用只检查图片头且无界读取的导出函数。

为拒绝 JSON Schema 允许的 1.0，下标启用 SDK 严格整数模型；通用协议边界在 schema 后校验既有参数模型，失败归一化为 invalid_arguments，不回显参数。既有查询、创建和重试回归全部通过。
