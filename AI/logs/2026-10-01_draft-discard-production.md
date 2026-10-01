# 2026-10-01 AI 草稿丢弃修复合入与生产部署

## 背景

用户原话：「合入main,部署生成」。结合上轮交付中的「尚未合入 main 或部署生产」，本轮按合入 main 并部署生产执行。执行者为 Codex · 完整模式；开工工作区干净，任务分支 `codex/draft-discard-navigation` 为 `477c5b2`，本地 main 为 `692728d`，原生产 release 为 `omrs-af9e400`。这是开发任务交付后的独立部署任务，原开发日志保留。

## 合入与行为变化

已执行 `git switch main`、`git merge --ff-only codex/draft-discard-navigation`，本地 main 快进至 `477c5b25c81f30e0b6813266e8205f6f37b80734`。相对原生产的业务源码仅修改草稿控制器与画布控制器，后端及依赖没有变化。

生产 AI 草稿丢弃成功后保持「待审核」并继续下一份，末项选择上一份；队列清空时清除会话选择，返回或刷新保持空状态。取消或失败保留编辑；空详情的画布刷新允许没有检测结果。版本保持 v2.1.0。

## 部署与回滚

- 从 Git 提交归档创建 `/root/workspace/apps/releases/omrs-477c5b2`，5 个关键源码文件与提交逐字节一致；`.venv` 相对链接复用 `../omrs-bbf3757/.venv`。
- 新 release 隔离验证通过后，复核生产无活动助手、草稿或收件箱任务，停服创建一致性快照。有效快照为 `/root/workspace/apps/releases/OMRS-draft-discard-rollback-20261001T154036Z/`，权限 0700，包含原 unit/drop-in、原发布源码归档、完整 `错题/` 归档及文件/数据库表内容哈希。
- GNU tar 归档比较与 `sha256sum -c MANIFEST.sha256` 全部通过。只替换 `/etc/systemd/system/omrs.service.d/10-release.conf` 的 release 路径，再执行 `systemctl daemon-reload`、`systemctl start omrs.service`。实际停服、备份与切换约 3 秒。
- 切换成功时间为北京时间 2026-10-01 23:40:39；真实 Vault、端口、PIN、Nginx、检测服务和模型指针保持原配置。
- 代码回滚时，将快照的 `10-release.conf.before` 恢复到原 drop-in，执行 `systemctl daemon-reload`、`systemctl restart omrs.service` 并检查 `/api/status`。原 release 保留；不要恢复旧 Vault 归档覆盖上线后的数据。

## 已实际执行的验证

新 release 的测试实例均使用临时 Vault、随机端口，并移除 `OMRS_SYSTEMD_SERVICE`：

| 命令 | 结果 |
| --- | --- |
| `python3 tests/e2e/drafts.py` | 75/75 通过，含丢弃队列、取消/失败保护、空队列返回和刷新 |
| `python3 tests/e2e/drafts_blocks.py` | 59/59 通过，含多块审核、丢弃后继续审核及四档布局 |
| `.venv/bin/python -m unittest tests.test_asset_cache -q` | 6/6 通过，使用复用的生产 Python 环境 |

生产切换后实际检查：

- `omrs.service` 为 active/running，WorkingDirectory 指向 `omrs-477c5b2`，PID 2677457，`NRestarts=0`；`/api/status` 返回 v2.1.0、262 题，启动时间已变化，新版启动后错误级 journal 为 0。
- 两个修改过的草稿 JS 文件经本机 Web 端口读取，SHA-256 与 release 完全一致，响应包含新 ETag。
- 公网 HTTPS 入口返回 200，未登录访问草稿静态资源与 MCP 均为 401。真实 Chromium 验证 PIN 输入与解锁按钮可见、免 PIN 入口隐藏、页面脚本错误为 0；截图为 `/tmp/omrs-draft-discard-production-entry.png`。
- 6 个 SQLite 库前后 `quick_check` 全为 ok；868 个非数据库文件（含 282 个 Markdown）SHA-256 无变化。所有业务表行数及内容哈希不变，仅 Ledger 的 `workspace_fingerprint` 与 `workspace_scan_status` 随启动更新扫描元数据。

部署状态保存在 `/tmp/omrs-draft-discard-deploy-state.json`；发布目录的隔离测试输出为 `/tmp/omrs-draft-discard-release-drafts.log`、`blocks.log`、`cache.log`（后两者同前缀）。快照内的 `before.json`、`after.json` 保留完整核对摘要，不包含业务行明文。

## 影响文件与文档收尾

`git diff --name-status` 已复核部署文档范围：`AI/environment.md` 更新当前生产 release 与回滚快照；`AI/mcp.md` 与 `AI/plans/mcp-integration/progress.md` 同步当前生产路径，保留原 MCP 发布事实。新增本任务日志，`AI/logs/log.md` 由脚本生成。没有新增业务代码或版本号修改。

已运行 `python3 tests/check_docs.py --write-log-index`，索引差异仅新增本任务条目；`python3 tests/check_docs.py --diff HEAD` 检查 77 份文档、0 问题、退出码 0，3 条提醒均为本次未修改大文档的体积提醒。`git diff --check` 通过。本批以独立部署文档切片提交到本地 main，线上源码仍对应 `477c5b2`。

## 未执行的验证与边界

本轮没有重复 Node 全量、全仓视觉、组件门禁或全量 Python：已验证提交快进合入，业务代码逐字节一致；开发阶段的 403/403 Node 与其它门禁保留在开发日志，本轮针对新 release 与上线差异验证。

生产没有创建或丢弃测试草稿，也未获取 PIN 会话进入主工作台；真实操作闭环由发布目录的隔离实例验证，线上核对服务、资源与入口。没有生成 MCP 验收 Key、重复带认证的 SDK 调用、启动 Tunnel 或推送远端。
