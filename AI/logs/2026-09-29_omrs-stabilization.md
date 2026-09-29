# 2026-09-29 OMRS v1.35.0 数据完整性与并发巩固

## 背景

用户提出《OMRS v1.35.0 数据完整性与并发巩固计划》，本任务由 Codex · 完整模式在分支 `codex/omrs-stabilization` 执行。基线 `c2dee40`（v1.34.0），此前项目现状审查点 `80ff164`。生产部署与真实 Vault 正文回填需另行授权。计划总纲、执行说明与实时进度见 `AI/plans/omrs-stabilization/`。

## 行为变化

本地 v1.35.0 已实现只读正文覆盖率盘点、正文随对应 Ledger 提交入账、启动前增量回填、删除前可取回校验、跨题还原拒绝与助手撤销续做。收件箱用持久 revision 和 reset_epoch 检查更新、重置、丢弃及录入；前端字段补丁与后台作业防止过期结果覆盖人工编辑，flush 失败不继续录入。受管模型在主站监听前恢复中断操作，管理查询只读，检测请求核对实际在线身份；未过独立内容验收的应用需明确确认并记录服务端认证来源。助手、标注和展示板的迟到响应或冲突保留当前状态。本地代码与受影响浏览器主路径已完成复验。

质量补丁进一步保护唯一正文：创建题目的 Ledger 提交失败时保留已写出的 Markdown 与附件；助手撤销先验证所有涉及正文的当前 blob，损坏时不先撤其他题。旧投影 blob 缺失且文件已改、或 blob 内容/身份损坏时，API 编辑、标签、移动、删除与工作区扫描拒绝该题写入；扫描会报告并跳过冲突题，其他题仍继续。

## 影响文件

- `omrs/content_history.py`、`creation.py`、`question_ops.py`、`workspace_sync.py`、`agent/revert.py`、`ledger.py`、`cli.py`：正文审计、入账、删除与撤销边界。
- `omrs/inbox.py`、`server.py`、`annotate.py`、`traincontrol.py`、`trainpanel.py`、`ai_assist.py`：CAS 接口、模型恢复、在线身份与操作审计。
- `assets/app/features/create/`、`annotate/`、`assistant/`、`board/`、`trainpanel/`：保存队列、冲突提示和迟到响应处理；`omrs/version.py`、`omrs_dashboard.html` 标明 v1.35.0。
- `tests/` 下的后端、Node 与隔离浏览器回归验证上述路径；`AI/` 模块文档、计划、任务日志和根 `README.md` 同步契约。已用 `git diff --name-status c2dee40` 结合未跟踪文件状态核对实际变化。

## 本地提交

- `15301b8`：正文审计、入账、回填、删除保险与按运行撤销；附隔离回归及计划、模块文档。
- `0130415`：收件箱 revision、字段补丁、后台代次校验及浏览器交错回归。
- 本提交：模型服务恢复与审计、标注和异步页面状态、版本与文档收尾；哈希以本分支最新提交为准。

## 已执行验证

- 建立基础版前执行 `git status --short`，确认当前分支有多份并行在制的后端、前端和测试文件；未覆盖或清理这些改动。
- 阅读 `AI/README.md`、`AI/plans/README.md` 和相关模块文档速查头，确认计划目录、文档映射与门禁要求。
- 质量代理用 `git archive c2dee40` 取旧版源码，并在临时 Vault/假服务中运行三组红灯脚本，脚本退出码 **0**，断言均观察到旧错误：①创建后 Markdown 存在而 blob 不存在，随后撤销使两者都不存在；②旧版只改 layout 的保存跨 `load()`/提取后仍提交整份 regions，把服务端 done 结果写回 running 且 text 变空；③构造模型操作为 running、在线身份为 new、配置指针为 old，基线 `cli.main serve` 到开始监听时仍为 running，假后端调用为 0。此复现只在旧版临时源码与临时 Vault 中执行，未触碰生产服务或真实数据。
- 主控首轮全仓门禁：`python3 -m unittest discover -s tests -p 'test_*.py' -q` **375/375**；`node --test tests/app/*.test.mjs` **377/377**；`python3 tests/app/run_browser.py` **32/32**。
- 质量补丁定向验证：`python3 -m unittest tests.test_content_integrity tests.test_labels -q` **23/23**；`git diff --check` 通过。此结果不替代质量补丁后的全仓复测。
- 质量补丁后全仓 Python 复验：`env -u OMRS_SYSTEMD_SERVICE python3 -W ignore::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -q` **379/379** 通过。
- 质量补丁后隔离浏览器复验：`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/create.py` **104/104**、`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant.py` **58/58**，均使用临时 Vault 与随机高端口。质量补丁未修改前端；其余 Node、组件浏览器和页面主路径的首轮通过结果仍适用。
- 切片隔离回归：将 `15301b8` 与 `0130415` 分别用 `git archive` 导出到临时源码运行全仓门禁；前者 Python **368/368**、Node **369/369**、助手浏览器 **58/58**，后者 Python **373/373**、Node **375/375**、组件浏览器 **32/32**、录入浏览器 **104/104**，均通过。
- 隔离浏览器主路径：`tests/e2e/create.py` **104/104**、`assistant.py` **58/58**、`assistant_race.py` **2/2**、`annotate.py` **34/34**、`traincontrol.py` **32/32**、`trainpanel.py` **32/32**、`board.py` **25/25**，均通过。
- 静态门禁：`python3 tests/check_ui.py` **0 个问题**；`python3 tests/check_contrast.py` **58/58**；`python3 tests/check_docs.py --diff c2dee40` 检查 **57 份文档、0 个问题**。文档检查另提醒 `AI/api.md` 与旧执行说明超过建议文件大小上限，不计为失败。
- `python3 tests/visual/run.py --ref c2dee40` 比较 **48 张**：24 张有差异、24 张无差异，脚本错误 0。历史页因启动时不再生成一次性正文快照而少一条时间线项，差异 **1.889–3.981%**；仪表盘最近动态同因变化 **0.352–0.714%**；其余页面桌面端 **0.001–0.002%** 的差异来自侧栏版本号。未发现本轮功能区域的其他视觉回归。

## 未执行验证与下一步

本地代码与页面主路径验收已完成。未执行生产部署、真实 Vault 增量回填、真实 Vault 写入后的 Ledger/Markdown/模型身份验收，均需用户单独授权；不能把本地通过或只读盘点当作生产已发布或缺口已补齐。

## 只读数据盘点与 16:59 调查

主控在本轮以新 `content-audit --json` 对真实 Vault 做只读盘点：236 道活动题、23 道当前缺 blob、0 个文件/投影冲突、63 个历史缺口，后者均早于首次 snapshot。用户原先给出的 232/19/63 是较早时点输入；当前题目与当前缺口各增 4，不能据此解释为已发生正文丢失。未运行真实 Vault 回填；发布前须再只读盘点，并在独立授权、备份与部署后核对当时全部安全可回填的当前缺口降为 0。

主控只读核对 `managed/operations/bd5a…json`：2026-09-29 16:59:28（UTC+8）记录 activate `v2-20260929-b`，16:59:29 完成；旧记录的 actor 仅为硬编码“已认证用户”。同秒 `omrs-boxdetect.service` journal 有旧服务停止、新服务启动；`omrs.service` journal 该窗口有 manager GET 轮询，未找到 control POST；Nginx 目录无可用 access log，全局 system journal 也未找到该 POST。现有证据**无法归因**到具体请求者或个人，不猜测操作者。

本轮只读核对的 `managed/state.json` current 与 active 指针一致，`/health` 在线模型仍为 `v2-20260929-b`，SHA 与该 operation 的 resulting_sha256 一致。本轮未切换在线模型。
