# 2026-10-09 提取成功提示与生产发布

## 背景

执行者：Codex，完整模式。用户先要求「提取完成为什么还会显示这个」「之前不是优化过,让他不要乱弹窗吗?找找记录咋回事」，调查发现 9 月 30 日 `d51efb3` 只改了标记就绪提示，遗漏提取成功和重复提取的提示。随后明确授权「执行修改,完成后部署生产,提交GitHub」。本任务基线 `7b42945`，开工工作区干净；生产源码固定为 `ee366f1`（v2.3.8）。本轮不属于进行中的计划。

## 行为变化

- 一键提取和单区域重试成功后，只在「区域与转换」标题下显示局部成功状态，约 3.2 秒后隐藏。
- 重复点击一键提取时，「各区域已提取」同样在局部显示，避免成功通知遮住底部按钮。失败和警告保持全局通知。
- 成功回调绑定控制器生命周期、当前图片和重置代次；切图、离页或重置后，旧任务继续同步数据而不显示成功反馈。已显示的提取提示不会出现在其它图片上。
- 发布版本 v2.3.9；沿用现有前端资源内容指纹，刷新页面取得新模块。

## 影响文件

- `assets/app/features/create/inbox-ops.js`：成功通知改为由调用方提供的回调，失败仍调用全局通知。
- `assets/app/features/create/process.js`：复用现有状态块、隐藏计时和销毁清理；统一单区域／一键提取入口并核对图片 ID、代次与页面状态。
- `tests/e2e/create.py`：验证成功与重复点击不弹全局提示、部分失败警告、自动隐藏，以及重置／离页后的旧结果；沿用真实后台任务、解析器与 Chromium，只替换外部模型。
- `AI/frontend/create.md`、`AI/frontend/architecture.md`：同步局部反馈和生命周期约束。
- `omrs/version.py`、`omrs_dashboard.html`、根 `README.md`、`AI/README.md`、`AI/changelog.md`：同步发布版本和用户可见变化。
- 本任务日志及生成索引；部署完成后同步 `AI/environment.md`。实际范围以交付前差异和提交记录复核。

## 验证

已实际执行：

- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL node --test tests/app/*.test.mjs`：455/455 通过，无跳过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/app/run_browser.py`：34/34 通过。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组全部通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -u tests/e2e/create.py`：最终 124/124 通过；含延迟轮询响应后离页、返回重挂载的回归，以及桌面／手机、浅色／深色审计。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/visual/run.py --ref 7b42945 --pages create --create-stage process --out /tmp/omrs-extract-status-visual`：4 组比较、8 张截图；无脚本错误、横向溢出、小触摸目标或行内样式。浅色／深色桌面各 0.002% 差异，均只在版本脚注 `(55,871)–(61,880)`，是 8→9 的预期变化；两组手机无差异。已查看差异图及 E2E 成功状态截图，成功状态位于区域面板内，底部按钮无遮挡。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_asset_cache tests.test_web_assets tests.test_migration_compat -q`：21 项通过。
- `python3 tests/check_docs.py --write-log-index` 和 `python3 tests/check_docs.py --diff HEAD`：105 份文档、0 处问题；2 条既有大文件提醒。`git diff --check` 已通过。

所有业务测试使用临时 Vault、随机端口，清除生产控制变量；不读取真实题库。产物保存在 `/tmp/omrs-extract-status-*`，精确发布验证及生产保全结果在完成后追加。

未执行：真实付费模型请求、实体手机和 Windows 浏览器；本轮只改成功反馈的投递，不改模型、接口或持久化。全量后端及无关页面 E2E 不重复运行，发布另验资源缓存和迁移兼容。

## GitHub 与生产

源码提交 `9b29d495d726a5d7daa9c9948c915b36b917df54`（`fix(create): 提取成功改为局部提示并发布 v2.3.9`）已正常推送 `origin/main`，`git ls-remote` 核对为同一完整 SHA。提交前后复核本任务 12 条路径，未纳入私人题库、数据库或控制配置。

精确release `/root/workspace/apps/releases/omrs-9b29d49` 来自该提交归档，1,288个文件逐字节核对；复用原venv。`python3 /tmp/omrs-extract-status-release/validate-release.py` 实跑7/7组全部退出0：Node455、组件34、录入124、UI纪律、58组对比度、文档105份0问题、后端21项。无跳过；原始日志、前后截图与状态截图已复制到私有保全目录。

前两次切换因审核历史表增加记录而被严格数据核对自动回退至旧源码：首次为5条此前失败的 `propose_question_update`，第二次为并发草稿调用失败后留下的1条 `create_draft`。逐行核对确认均是现有 `ai_review.initialize → _import_mcp` 在启动时从冻结runtime记录补记的只读失败历史；身份、状态和时间戳与原运行证据对应。原审核记录未改；没有放宽数据门禁、删除补记或恢复旧Vault。调查期间还有外部MCP读取与草稿创建完成，正常新增内容全部保留。随后重新以当前数据保全，最终切换前后的完整表／文件核对通过。两份失败保全仍保留，不改写其失败状态。

最终保全 `/root/workspace/apps/releases/OMRS-v239-release-20261009T051105Z-ctmbt1bv`：目录0700、文件0600，包含新旧源码、有效服务配置、实际Nginx及模型控制、停止主服务后的一致Vault/maintenance归档和私人摘要。tar与原目录比较通过，独立解包978文件逐字节一致，SQLite完整性通过。冻结前后检查活动任务和维护journal均为零；只切换主服务源码。

2026-10-09 13:11:10 CST最终完成，切换与核验3.818秒。主服务active/running、PID1650618、NRestarts=0，实际cwd与命令行指向新release。最终冻结前后49张业务表和921个内容／关键配置文件摘要保持，290题、0冲突、待审0；85个控制文件/模型指针指纹保持。Tunnel、检测与Nginx没有重启。上述题数以最后一次冻结为准，包含切换前已经完成的并发业务。

`python3 /tmp/omrs-extract-status-release/read-live.py` 退出0：线上两项修改模块HTTP200、gzip字节与release一致、immutable、条件请求304，资源内容指纹已变化；公网匿名资源401。公网入口/授权摘要200，匿名status/MCP401，回环MCP无Key401。本机／公网真实浏览器390px PIN入口无横溢、无脚本错误；不输入PIN、不调用业务写接口。再次只读核对业务摘要、文件、控制配置和运行PID/cwd全部一致，切换后错误级journal为空。

部署事实同步 `AI/environment.md`；收尾文档单独提交并正常推送，生产继续固定在已验证的源码提交，不为纯文档重启。旧release、依赖及三份保全均保留。收尾复核仅环境文档和本任务日志两条路径；`python3 tests/check_docs.py --diff 7b42945`、日志索引生成和 `git diff --check` 均通过。三份保全各272个递归验证文件SHA256逐项一致，根清单及私密权限复核通过。

## 下一步

刷新页面即可使用局部提取成功提示；本任务功能和生产发布均已完成。真实PIN登录后的生产提取、付费模型、Windows与实体手机未执行，页面主路径以隔离真实浏览器验证。
