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

待候选门禁全绿后，正常提交并推送 `origin/main`；从精确提交归档发布并复用既有依赖。切换前核对未完成任务和维护 journal，停主服务后保全一致 Vault 和控制配置；只切换主服务源码。失败定向恢复旧源码，不能用旧 Vault 覆盖后续业务数据。部署及只读验收结果完成后追加本节。
