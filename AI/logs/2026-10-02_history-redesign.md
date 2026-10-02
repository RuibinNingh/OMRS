# 2026-10-02 历史页重设计与 MCP 运行记录

## 背景

用户要求历史页重设计并增加系统运行记录，首批聚焦 MCP，认可分区时间线草稿后要求「执行修改」。Codex 完整模式，基线 `968fdfb`，开工工作区干净。所属计划：`AI/plans/history-redesign/`。

## 行为变化

历史页使用用户认可的分区时间线：「学习与变更」「系统运行」分别按天分组，默认最新在前并保留原排序偏好。桌面选择记录看右侧详情，手机在列表与详情间切换并还焦点；两区有搜索和时间筛选，系统区增加密钥与状态。真实数量、空态、读取失败和重试均接入后端，不展示草稿的示例数据。

MCP 在真实工具执行边界记录进行中、成功、失败与中断；独立 SQLite `runtime.db` 保存白名单摘要和密钥公开快照，重启恢复遗留进行中状态。握手、工具发现和未认证 HTTP 不冒充调用。原权限、幂等、原图及领域写锁保持；记录故障不改变工具结果，原始正文、密钥、原图、签名 URL 和客户端自由文字不进入记录。

运行详情复用草稿编号和原 Ledger `_draft.draft_id` 读取当前草稿、后续人工入库节点；学习详情能返回来源调用，包括首屏之外的记录。关联读取故障不会拖累学习详情。系统记录只读；原反馈修正、Session 撤销 / 恢复和结构化状态还原仍追加 Ledger 节点。搜索改变立即作废旧请求，进行中轮询保持已加载旧页，参数 / 结果 / 技术详情分别保留展开状态。

## 影响文件

交付前实际执行 `git diff --name-status` 与未跟踪文件清单复核，本次提交的改动均属于本任务：

- `omrs/runtime_records.py`（新增）：独立存储、脱敏、生命周期、筛选分页、汇总及只读关联；`omrs/mcp/server.py` 包装原工具执行边界；`omrs/cli.py` 在监听前恢复中断。
- `omrs/server.py`：运行记录两条读取路由与禁止缓存，历史筛选和详情关联；`omrs/projections.py`：筛选先于分页、草稿来源摘要及独立节点详情字段。
- `assets/app/domain/history.js`：两类记录读取；`features/history/` 的 `index.js/state.js/view.js/history.css`：分区布局与交互；新增 `learning-view.js/runtime-view.js/runtime-controller.js` 拆分职责，保留现有修正表单。
- `tests/test_runtime_records.py`（新增）、`tests/app/runtime-history.test.mjs`（新增）、`tests/app/history.test.mjs`、`tests/e2e/runtime_history.py`（新增）、`tests/e2e/history.py`：领域、权限、存储故障、脱敏、并发、时区与请求竞争回归，定位器适配选择式详情。
- `AI/frontend/records.md`、`AI/frontend/architecture.md`、`AI/frontend.md`、`AI/api.md`、`AI/data.md`、`AI/ledger.md`、`AI/mcp.md`、`AI/security.md`、新增 `AI/runtime.md`：同步当前可验证行为。`AI/README.md`、根 `README.md` 与计划索引更新入口；`AI/routes.md` 和 `AI/logs/log.md` 按脚本生成。
- `AI/plans/history-redesign/plan.md` 与 `progress.md`（新增）、本日志：用户原话、确认范围、决策与实测收尾。版本保持 v2.1.0，按计划单一完整切片提交。

## 验证

已实际执行，最终结果均通过：

| 命令 | 结果 |
| --- | --- |
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 501 / 501，88.630 秒，无跳过，含真实同进程 MCP SDK 协议测试 |
| `node --test tests/app/*.test.mjs` | 410 / 410，无跳过 |
| `python3 tests/app/run_browser.py` | 34 / 34 |
| `python3 tests/e2e/history.py` | 29 / 29，原修正与四档审计通过 |
| `python3 tests/e2e/mcp.py` | 33 / 33，真实原图草稿和密钥管理通过 |
| `python3 tests/e2e/runtime_history.py` | 34 / 34，70 次真实 SDK 调用（69 成功、1 越权失败）、浏览器人工入库与双向回溯、分页保留、迟到请求、手机返回、终态轮询、真实服务重启通过 |
| `python3 tests/check_ui.py` | 全仓五项计数均 0，规则零问题 |
| `python3 tests/check_contrast.py` | 58 / 58 |
| `python3 tests/visual/run.py --ref 968fdfb --pages history --out /tmp/omrs-history-visual-20261002-05` | 4 对截图完成，无页面脚本错误或横向溢出 |
| `python3 tests/check_docs.py --write-routes`、`python3 tests/check_docs.py --write-log-index` | 分别执行并生成路由 / 日志索引 |
| `python3 tests/check_docs.py --diff 968fdfb`、`git diff --check` | 零问题、退出 0 |

全部服务使用脚本持有的临时 Vault 与随机高端口，启动环境去掉 `OMRS_SYSTEMD_SERVICE`；没有访问生产端口或真实题库。长调用轮询采用真实数据库生命周期夹具，短调用、权限失败、草稿新建与复用使用官方 SDK；不把长调用夹具称为真实 SDK 慢请求。数据脱敏直接读取 SQLite 验证，损坏运行库时学习详情仍可读也有回归。Python 全量输出存在仓库既有 ResourceWarning 和测试主动制造的错误日志，最终退出 0；未做无关清理。

调试期间修复了布尔属性经模板被省略导致的手机切换 / 选中态、搜索防抖期间旧请求仍有效、关联列表读取故障、刷新丢失旧页以及同名详情折叠状态混用。浏览器测试的操作定位器改到所选详情；分页锚点先使加载按钮进入视口，避免 Playwright 的点击滚屏污染断言。SDK 测试在独立线程运行，避免同步浏览器自己的事件循环冲突。以上最终复跑全部通过。

### 视觉差异解释

已实际查看学习页与系统页截图。学习页对基线的差异：浅色桌面 12.600%、深色桌面 16.212%、浅色手机 51.562%、深色手机 51.547%。四对分别确认：桌面两主题从逐节点卡片 / 折叠详情改成日分组轻量时间线与右侧选中详情，增加分区标签、搜索与日期控件，默认顺序改为最新在前；手机两主题使用同样控件换行，详情由独立画面显示，列表竖线 / 卡片替换为行式时间线。这些都是本次已确认重设计的预期差异。

四档当前学习页最小字号 12px，可点目标低于规定高度、行内样式及横向溢出均为 0。运行页另拍浅深 × 桌面手机四张关联草稿详情，实际审核已入库状态、关联按钮和参数摘要；同档审计全部通过，手机验证返回焦点。视觉报告在 `/tmp/omrs-history-visual-20261002-05/report.html`，最终系统页截图在 `/tmp/omrs-runtime-history-shots-6pkonoiq/`，产物不入库。

### 未执行与下一步

未推送、未部署、未操作 systemd / Nginx，未做生产或目标 ChatGPT 账户联调；用户本轮授权是本地实现，外部状态变更须单独授权。无未完成的实现项，旧调用不补造。生产仍运行原 release；下一步由 Hermes 完整模式在取得发布授权后部署并验收，不把本地通过说成已上线。

文档门禁有三条现存篇幅提醒（API 与两份既有计划），退出仍为 0；API 拆分已登记在 `AI/optimization.md`，本任务不扩展到无关重构。新增存储说明单独放 `AI/runtime.md`，`AI/data.md` 保持小于 40KB。

### 提交范围复核

收尾时同一工作区新增了其他工作的题图模块与测试，并在 `omrs/mcp/server.py` 提取图片校验。按 hunk 分离：本次仅提交运行记录导入、密钥公开快照读取和调用包装；图片校验提取及新模块保留在工作区，不覆盖、不纳入本次提交。使用独立 Git 索引固定已复核范围，再由暂存树导出隔离验证副本。

该副本实际复跑 Python 全量 501 / 501（88.974 秒）、Node 410 / 410、组件浏览器 34 / 34、学习历史 E2E 29 / 29、运行记录 E2E 34 / 34、MCP E2E 33 / 33，以及 UI 零问题和对比度 58 / 58，全部退出 0。因此提交不依赖工作区另一项尚未提交的改动。
