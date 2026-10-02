# 2026-10-02 MCP 题图与运行记录推送及生产发布

## 背景

用户原话：「推送GitHub」「部署生产」。执行者 Codex，完整模式；本地工作区干净，main 为 ba6501b，生产为 omrs-477c5b2 / v2.1.0。Git fetch 后远端未领先，本地领先六个提交，已正常快进推送 origin/main（692728d → ba6501b），未强推。

当前 main 包含已独立验收的历史记录页及运行记录提交 73e34fd，连同 I1–I3 的 86d3937、1af2263、ba6501b 一起发布。这是实现交付之后的独立部署任务，原开发日志、验收计数与未发布事实保留；版本保持 v2.1.0。

## 行为变化

生产开放 get_question_image，按 get_question.images 下标返回原生图片并保持原字节、附件边界、资源上限和实时权限。历史页上线「学习与变更」「系统运行」分区时间线；MCP 工具执行边界写入脱敏终态，不记录图片。正式题目和草稿写权限保持。

## 发布与回滚

从 ba6501b90fdc5293121876ac82709f4d00c727df 的 Git 归档创建 /root/workspace/apps/releases/omrs-ba6501b，16 个后端、历史页与验收文件和提交逐字节一致。.venv 相对链接复用 ../omrs-bbf3757/.venv；实际环境为 Python 3.13.5、mcp 1.28.1、Pillow 12.3.0、jsonschema 4.26.0、pydantic 2.13.5，未安装或升级依赖。

隔离门禁通过后，重新确认无活动助手、收件箱或草稿任务，停服创建一致性回滚快照 /root/workspace/apps/releases/OMRS-question-image-rollback-20261002T090103Z/（0700）。包含原 unit/drop-in、旧源码归档、完整错题归档和只含计数/哈希的数据库、内容文件摘要；GNU tar 对比及 sha256sum 清单校验通过。

仅替换 /etc/systemd/system/omrs.service.d/10-release.conf 的三个 release 路径，再执行 systemctl daemon-reload、systemctl start omrs.service。停服、备份、切换和启动核验共 3.102 秒；切换完成为北京时间 2026-10-02 17:01:06。真实 Vault、端口、PIN、Nginx、检测配置与模型指针未修改。

代码回滚只需恢复该快照的 10-release.conf.before 到原 drop-in，再执行 systemctl daemon-reload、systemctl restart omrs.service，并确认状态接口正常。旧 omrs-477c5b2 和共享依赖目录保留；不要用旧 Vault 归档覆盖上线后数据。自动失败恢复路径同样只恢复代码配置，本次部署一次通过，未触发回滚。

## 已实际执行的验证

下列命令在新发布目录执行，全部使用生产 Python 环境、临时 Vault 与随机高端口；清除生产重启及检测控制环境变量：

```bash
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python -m unittest tests.test_question_images tests.test_agent_tools tests.test_mcp tests.test_mcp_keys tests.test_mcp_http tests.test_mcp_protocol tests.test_mcp_draft_atomic tests.test_runtime_records -q
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python tests/e2e/mcp.py
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python tests/e2e/history.py
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python tests/e2e/runtime_history.py
```

| 验证 | 结果 |
| --- | --- |
| 题图 / 共享查询 / MCP / 运行记录专项 | 107/107，5.542 秒 |
| 真实 SDK / 草稿与 Key 浏览器路径 | 39/39 |
| 学习历史修正与四档审计 | 29/29 |
| MCP 运行记录、关联、手机与重启 | 34/34 |

全部退出码 0，无 SKIP。专项输出有 SQLite ResourceWarning，未做无关连接管理重构。日志与部署脚本在 /tmp/omrs-question-image-deploy-yeu7yoea/，状态摘要为 state.json；公网 PIN 入口截图为 public-entry.png。

生产只读核验共 26/26：官方 SDK 经公网 HTTPS 初始化并发现十个只读工具；get_question 与共享读取完全一致，按 images[] 下标取得原生 image/png，Base64 解码的 351546 字节与磁盘原件完全一致，没有结构化图片 JSON。题图的标准只读注解与输出 schema 正确。

临时 omrs:read Key 直接点名 create_draft 返回 forbidden，Web API 返回 403；验收后密钥 mcp_c5b22b8aca944f06 已吊销，公网返回 401。明文只在内存，不写脚本、日志或文件。生产没有创建、提交或丢弃测试题目、草稿；临时密钥的三次真实调用（读题、读图、被拒绝的草稿调用）留下终态，题图参数仅 UID/下标，结果摘要为空，无图片/Base64/密钥明文。

八个历史页静态资源哈希与 release 一致；公网首页 200、未登录历史资源 401，真实 Chromium 的 PIN 输入可见，页面脚本错误为 0。服务 active/running，WorkingDirectory 指向新 release，PID 1688458、NRestarts=0；/api/status 为 v2.1.0、262 题、0 冲突，切换后的错误级 journal 为 0。

上线前后 868 个内容文件（含 282 个 Markdown）哈希不变，原六个 SQLite 数据库业务表行数、内容与 schema 哈希不变；仅 Ledger 的 workspace_fingerprint、workspace_scan_status 更新扫描元数据且行数保持。公网验收新增独立 runtime.db，最终七库 quick_check 都为 ok；预期变化只有临时密钥 / 最近使用元数据和三次运行记录。runtime.db、mcp_keys.json 均为 0600，既有密钥公开元数据保持（允许最近使用时间更新）。

## 影响文件与文档收尾

更新 AI/environment.md 的真实 release 和回滚位置、AI/mcp.md 的当前线上能力；两个计划的总纲、进度和 AI/plans/README.md 记录新增发布授权及完成状态。新建本任务日志，AI/logs/log.md 按脚本生成。没有改业务代码、版本号或原执行说明；旧任务日志不重写。

已运行 python3 tests/check_docs.py --write-log-index，索引仅新增本任务；python3 tests/check_docs.py --diff HEAD 检查 81 个文档、0 问题，退出码 0，三条既有大文件提醒保持。git diff --check 通过；git diff --name-status 连同未跟踪日志复核，本轮仅涉及上述文档。收尾文档采用独立提交并同步 origin/main，生产 release 保持已验收的 ba6501b。

## 未执行与下一步

本轮未重复 Python/Node 全量、组件、UI/对比度与视觉全仓门禁：已验收源码的开发门禁保留，本轮针对发布环境、生产差异和历史页主路径验证。未获取 PIN 会话进入生产主工作台，完整页面交互以新 release 的隔离浏览器结果为准。

ChatGPT 目标账户、Windows 实机与 Tunnel 尚未联调，本次没有启动 Tunnel、调整 OAuth/鉴权或升级版本。推送及生产发布已完成，无剩余实施项；上述联调为独立后续工作。
