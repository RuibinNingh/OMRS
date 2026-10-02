# 执行说明：MCP 题图按需读取

**日期：**2026-10-02。**执行者：**Codex，完整模式。
**基线：**规划和开工 HEAD 为 968fdfb；开工时已有历史记录改造，提交前复核独立基线，保护其全部改动。
**终点：**连续完成 I1–I3，以本地官方 MCP SDK 验收通过交付。生产、推送、Tunnel、目标账户联调与版本升级不在本批范围。

## 1. 任务目标与原话

新增只读工具 get_question_image(uid, image_index)，按需返回题目所引用图片的 MCP 原生 ImageContent。

用户原话：「制定计划」，随后要求执行所列完整计划；验收终点选择「本地 SDK 验收即可」。
附件中的明确约束：

> **不要给 `get_question` 加 `include_images`，也不要新增一个裸 HTTP 图片接口。**
>
> **新增一个 MCP 只读工具 `get_question_image(uid, image_index)`，按需返回 MCP 原生 `ImageContent`。**

历史诉求完整原话沿用 exec-2026-10-01-mcp-v1.md §1 与 progress.md「用户诉求」。API Key、查询同口径、唯一业务写入 create_draft、完整原图仍有效。附件中的 8 MiB 建议采用为本批默认约束。

## 2. 当前背景与约束

先读根 AGENTS.md、AI/README.md、AI/mcp.md、AI/security.md、AI/runtime.md、AI/environment.md 的 MCP 隔离验收，以及本计划 progress.md。

实测：SDK 1.28.1 能封装原字节为 ImageContent。现有 get_question.images 来自未截断的题目与答案分节，排序和去重沿用共享解析器。规划阶段 MCP 专项 60/60，共享查询和运行记录 21/21 通过。

实测：导出 _read_image_info 接受只有文件头和尺寸的损坏 PNG，不能承担完整校验；_find_image 允许绝对路径及 Vault 路径，不能作为 MCP 文件定位器。开工历史改造新增运行记录包装层，须保留且只补新工具登记。

## 3. 最终预期行为

get_question_image 必填 UID 与从 0 开始的图片下标；UID 去首尾空白、最多 200 字符且非空，下标拒绝布尔值、非整数和负数，拒绝额外参数。

每次复用共享 get_question，按 images[] 选择图片，不重新解析截断正文。成功仅返回一个 ImageContent，格式根据实际原件确认为 PNG/JPEG/GIF，Base64 解码与磁盘原字节一致。get_question、Web 图片入口、草稿写权限、内置助手注册表保持。

## 4. 实施计划与提交

开工记录 HEAD、已有差异，保存重叠文件快照。历史任务未提交时继续独立实现与测试，提交前必须可安全隔离本批增量，不能混入历史改造。

- I1：新增安全题图读取领域模块；抽出上传和输出共享的纯字节完整校验，Pillow 延迟加载。领域层输入 Vault、UID、下标，返回原字节及格式；补定位、大小、解码及字节测试。
- I2：注册 MCPImage 返回工具、omrs:read 和标准只读注解，显式非结构化图片输出；补 schema、实时权限、10/1/11 项工具发现及运行记录兼容测试。
- I3：官方 SDK 与隔离浏览器回归，全量 Python、文档门禁、日志索引及进度收尾。

各阶段一个提交，包含对应代码、测试、文档、同一任务日志和 progress 更新。阶段是检查点，连续执行到 I3。

## 5. 关键技术决策

客户端永远不传文件名或路径；仅使用该题 images[] 的服务端安全 basename。在 Vault 的错题/附件及普通子目录内查找，不解码 URL、不下载外链、不回退到绝对路径或 Vault 根；多个同名候选拒绝。

拒绝根、目录、图片符号链接、Windows 目录联接及非普通文件。通过受控文件句柄检查类型、大小并读取；支持目录 FD 的平台固定目录与文件句柄，其它平台检查目录和文件身份，防止路径替换绕过。

单张原字节 ≤8 MiB，最多读取上限加 1 字节；累计解码像素 ≤4000 万、帧数 ≤100。校验只解码，不裁剪、压缩、补尾、转码或重新保存原件。格式为 png/jpeg/gif，不根据扩展名推断。

读取和解码在线程中执行，不长时间持全局写锁；读取前和返回前复查实时 omrs:read，不缓存图像或授权结果。注册 readOnlyHint=true、destructiveHint=false、idempotentHint=true、openWorldHint=false；唯一业务写工具仍为 create_draft。

schema 错误使用 invalid_arguments；不存在、无图、越界、缺失、歧义、损坏和超限使用 invalid_request 配合可区分中文说明，OS 异常不泄漏路径。运行记录只保存脱敏 UID、下标、状态、耗时，不保存图片或 Base64。

## 6. 边界情况

题目或答案多图；重复引用；混合 Markdown 语法；引用在正文截断之后；无图；不存在 UID；非法下标；缺图；同名文件；恶意或编码路径；根/目录/文件链接；FIFO；读取期间替换或变化；误导扩展名；损坏像素流；8 MiB 边界；过多像素或帧；处理中吊销、到期或降权。

## 7. 修改范围

- 预计涉及：题图领域模块、MCP 适配与运行记录登记、对应 Python/SDK/E2E 测试和模块文档。
- 明确不要修改：get_question 返回及输入、Web /api/image、助手工具注册表、生产与草稿写权限。
- 本次必须完成：原生图片内容、题目绑定与受限文件读取、字节保真、实时权限、真实协议及回归、三个独立提交。
- 可以顺手处理：仅共享校验抽取所必要的异常归一化和中文事实文档。
- 本次不要处理：无关重构、图片转换、客户端联调、部署、推送或版本升级。

## 8. 验收标准

SDK 调用获得且仅获得一个正确 MIME 的 ImageContent，解码字节等于原件。每个下标与共享 images[] 对应，旧读题结果相同。非法输入与不安全/损坏/超限文件明确拒绝，错误不含服务器路径。

读取权限发现 10 项、草稿权限 1 项、双权限 11 项；隐藏工具直接调用拒绝，处理中权限失效不返回图像。运行记录识别新工具且没有图片数据；读图不改变题目、学习 Ledger 提交或草稿业务数据。

旧上传、幂等、查询与浏览器审核回归通过，SDK 不得以 SKIP 代替成功。

## 9. 验证步骤

测试仅使用临时 Vault、随机高端口，清除生产服务与检测控制环境变量：

~~~bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_question_images tests.test_agent_tools tests.test_mcp tests.test_mcp_keys tests.test_mcp_http tests.test_mcp_protocol tests.test_mcp_draft_atomic tests.test_runtime_records -q
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/mcp.py
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest discover -s tests -p 'test_*.py' -q
python3 tests/check_docs.py --write-log-index
python3 tests/check_docs.py --diff <任务基线>
git diff --check
~~~

真实 SDK 路径为 get_question → images[] → get_question_image → ImageContent → 原字节比对。真实浏览器复跑既有 MCP 草稿与 Key 管理，不访问真实题库。

## 10. 执行原则

先读后改、以代码为准、复用抽象；实现细节可调整但目标、契约及验收不改，偏差写日志。

停止条件只有无法安全隔离已有改动，或复核事实要求改变目标、权限或附件边界；其它情况继续执行。中断时保存工作区，在 progress 写明阶段和未跑验证；恢复先查 git status、最近提交和状态块。

最终中文汇报五项：本批提交及版本、实际验证、未执行验证及原因、遗留不确定性、下一步。事实验证计数写入本批记录，历史记录不改写。
