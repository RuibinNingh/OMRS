# 2026-10-04 公网加载优化 v2.3.1 生产发布

## 背景

用户原话：「版本升级0.0.1」「然后部署生产,提交GitHub」。执行者：Codex，完整模式。开发提交 `ec2ebca`，开工工作区干净，生产源码 `de10022` / v2.3.0，GitHub main 为 `21b4bb1`。本日志为独立发布任务，不改写已交付的开发日志。

## 行为变化

版本升级为 v2.3.1，发布 gzip、原生模块预加载、主样式合并和内容版本静态缓存。沿用既有 Vault、Web / MCP 端口、公网地址、PIN、MCP 权限、Nginx、Tunnel、模型服务和虚拟环境，不安装或升级依赖。本次不改变数据库 schema 或题库格式。

## 影响文件

`omrs/version.py`、`omrs_dashboard.html`、根 `README.md`、`AI/README.md` 同步版本；`AI/changelog.md` 添加版本摘要；`AI/frontend/shell.md` 更新可验证的加载约定与侧栏版本。发布后更新 `AI/environment.md` 当前环境事实。本日志与脚本生成的 `AI/logs/log.md` 记录发布、验证和推送结果。部署脚本、原始 Vault 保全及私人对照材料只存仓库外。

## 发布前核对

主服务 active/running、NRestarts=0，代码目录 `/root/workspace/apps/releases/omrs-de10022`，主 PID1977331；Tunnel PID875442、检测服务 PID1532134，均正常，活动题262。GitHub main 无新分歧，可正常快进；禁止强推。agent / inbox / drafts / runtime / ai_review 五个运行库未终结任务数均为0，无整库恢复 journal 或正式题目写入意图；切换前再次复核。

## 验证

开发轮实际已通过 809 项 Python、449 项 Node、资源专项 17 项及相关真实浏览器验证，56 组截图无视觉差异。本轮只针对版本与精确 release 运行适当检查，不无因重复全套业务门禁。

已实际运行 `python3 tests/check_ui.py`（五类全仓计数0）、`python3 tests/check_contrast.py`（58组全部通过）、生成日志索引和 `python3 tests/check_docs.py --diff HEAD`（102份文档0问题，2条既有篇幅提醒）。`python3 tests/visual/run.py --ref ec2ebca --pages dashboard --out /tmp/omrs-v231-version-visual` 比较桌面/手机与浅/深四档：桌面差异0.001%为侧栏 v2.3.0 → v2.3.1 文案，手机侧栏底部隐藏、差异0%，尺寸一致、无脚本错误。

精确 release 的现有 venv 已核对 Python3.13.5、MCP SDK1.28.1、Pillow12.3.0，含浏览器验证依赖；未安装或升级包。从精确 release 运行 `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL .venv/bin/python -m unittest tests.test_web_assets tests.test_asset_cache tests.test_http_boundaries tests.test_security tests.test_write_lock tests.test_mcp_http tests.test_backup_recovery -q`，78项通过、无跳过，63.514秒。`OMRS_TEST_CDP_URL=http://127.0.0.1:9222 .venv/bin/python tests/e2e/shell_router.py` 同样移除两个生产控制环境变量，24项通过，涵盖13页直接进入、真实PIN、刷新、导航守卫及手机路径。日志分别保存在 `/tmp/omrs-v231-release-tests.log`、`/tmp/omrs-v231-release-browser.log` 并私有复制到保全目录。

没有重复全量809项Python、449项Node和全套业务E2E；业务源码已在开发轮验证，本轮补跑精确release及既有venv的相关回归。没有在生产设置测试PIN、创建验收Key/题目/反馈/报告/展示板或调用付费模型。生产PIN浏览器与完整公网工作台速度测量未执行；实际公网已核对匿名入口和资源传输、授权边界。

## 生产与 GitHub

发布源码提交 `b466c58e1036a4f6714d2073259000ef5cac8bdc`，由 Git 归档生成 `/root/workspace/apps/releases/omrs-b466c58`，1,139个源码文件逐字节校验通过；相对链接复用现有venv。保全目录 `/root/workspace/apps/releases/OMRS-v231-release-20261004T072046Z-kfh3o6yo/` 为0700，原始归档、源码归档、旧unit/drop-in、部署脚本、私人对照、验证日志和SHA清单均为0600。停服原样归档完整 `错题/` 与 `.omrs-maintenance/`，tar比较和刷盘完成，不用会初始化或迁移的应用备份替代原始基线。

2026-10-04 15:22:38 CST启动新主服务，停服保全至新版就绪共2.66秒。仅原子替换 `/etc/systemd/system/omrs.service.d/10-release.conf` 的三处release路径，daemon-reload并启动主服务；PID1011719，active/running、NRestarts=0。Tunnel PID875442、检测服务PID1532134和Nginx状态保持，未重启；模型active链接、管理状态SHA和控制配置SHA核对一致。

实际生产只读核验保持48张原业务表全部原行与原列，828个Markdown/原图/报告/配置/PIN/Key文件SHA不变，题库仍262活动题，待审0；全部SQLite完整性通过。版本模块gzip解压后等于精确release原字节，私有一年immutable缓存和ETag 304通过；主样式gzip并合并import，保留@layer。公网入口、会话查询为200，入口与公开场景脚本gzip实际验证；匿名status、审核数量、MCP和版本化工作台模块均401。本次没有发布失败或回退，未用旧数据归档覆盖任何事实。

已实际执行 `git push origin main`，正常快进 `21b4bb1..b466c58`；`git ls-remote --heads origin main` 返回 `b466c58e1036a4f6714d2073259000ef5cac8bdc`，与发布源码一致。发布后的环境和本记录随独立文档收尾提交再次正常推送。无强推、新标签或GitHub Release，不提交真实Vault、备份、数据库或私人对照材料。

收尾 `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff b466c58` 检查102份文档、0问题、2条既有大型计划提醒，退出0；`git diff --check`退出0。复核收尾仅修改 `AI/environment.md` 与本日志，不再部署或重启已经验证的生产release。

## 下一步

v2.3.1发布、验证和GitHub正常快进推送已完成。没有新增业务遗留，用户刷新后按原PIN登录即可使用加载优化。后续真实公网工作台计时可在用户已登录的浏览器中测量，当前开发指标仍明确为隔离限速测量。
