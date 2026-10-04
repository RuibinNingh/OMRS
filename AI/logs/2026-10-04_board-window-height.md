# 2026-10-04 展示板浮窗高度修复与 v2.3.2 发布

## 背景

用户原话：「展示板在一定的窗口比例下会变成这样」「给出修复方案」，本轮进一步授权「执行修复」「版本号+0.0.1」「上线生产和GitHub推送」。执行者：Codex，完整模式。开工基线 `8624875`，工作区干净；生产为 `b466c58` / v2.3.1。本任务独立于已交付的展示板改版和动效计划。

调查实测：大于760px、至1160px时展示板已左右分栏，而公共外壳的整屏flex只在大于1160px生效。展示板自身取消最小高度后，纸面回到150px默认高度；1000×700窗口的工作区只到270px，下方空白。此前E2E只验桌面和手机，未覆盖中间区间。

## 行为变化

大于760px时，仅活动展示板补齐内容区到活动面板的整屏高度链；保持内部独立滚动、手机上下布局、宽屏布局和常驻预览iframe。补充跨断点、矮浮窗、切到其它页的浏览器回归。版本升级为v2.3.2，不改变数据格式、数据库结构、业务写入、打印和导出契约。

## 影响文件

- `assets/app/features/board/board.css`：作用于活动展示板的高度传递。
- `tests/e2e/board.py`：共享主应用入口、断点连续缩放、矮窗口滚动及其它页作用域回归。
- `tests/e2e/p8_test_modules.js`：测试适配器沿用主模块内容版本地址，避免导入另一套领域单例。
- `AI/frontend/board-ui.md`、`AI/frontend/shell.md`、`AI/frontend/architecture.md`：当前高度、外壳例外与浏览器验证契约。
- `omrs/version.py`、`omrs_dashboard.html`、根 `README.md`、`AI/README.md`、`AI/changelog.md`：版本与用户可见行为。
- 本日志及脚本生成的 `AI/logs/log.md`；发布完成后更新 `AI/environment.md`。

## 验证

已实际执行：

- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL node --test tests/app/*.test.mjs`：449/449，零失败、零跳过。
- 同样清除控制变量后运行 `python3 tests/app/run_browser.py`：34/34；`python3 tests/e2e/shell_router.py`：24/24；`python3 tests/e2e/board.py`：46/46；`python3 tests/e2e/board_picker.py`：31/31。展示板涵盖9组连续缩放、列表和详情真实滚动、其它页作用域及浅深中宽审计。
- `python3 tests/check_ui.py`：全仓五类计数0、0处问题；`python3 tests/check_contrast.py`：58/58；`git diff --check`退出0。
- 标准 `tests/visual/run.py` 通过仓库外临时驱动调用，增设1000×700的window档：`--ref 8624875 --pages board,questions --viewports desktop,mobile,window --out /tmp/omrs-v232-visual`。12组前后对比、0脚本错误、0小目标、0整页/局部横向溢出，尺寸一致。展示板桌面/手机四组差异0%；中宽浅色2.920%、深色38.249%为工作区从270px扩展至700px、纸面从150px扩展至580px。题库桌面/中宽四组0.001%为侧栏版本v2.3.1→v2.3.2；手机两组0%。已检查截图，变化符合预期。

首次展示板E2E出现3项失败：测试适配器沿原未版本化地址导入，得到独立预览单例。跟随主模块资源根路径后，主路径、响应式与选板全绿；同时把旧的根路径入口改为共享 `open_app`，兼容当前锁屏规则。仅调整测试基础设施，不改变生产授权行为。

所有测试服务使用合成临时Vault和随机端口，清除生产控制环境变量；生产只做已获授权的发布与只读验收，不写测试业务数据。未重复无关全量后端/E2E，未执行实物打印和平板实机浮窗验收。`python3 tests/check_docs.py --write-log-index` 与 `python3 tests/check_docs.py --diff 8624875` 已执行：102份文档0问题，2条既有大型计划篇幅提醒。精确release复用原venv（Python3.13.5、MCP SDK1.28.1、Pillow12.3.0），没有安装/升级依赖。清除生产控制变量后，在 `/root/workspace/apps/releases/omrs-de1e62d` 运行 `.venv/bin/python -m unittest tests.test_web_assets tests.test_asset_cache tests.test_http_boundaries tests.test_security tests.test_write_lock tests.test_mcp_http tests.test_backup_recovery -q`：78项通过，零跳过，63.576秒；同一精确release运行 `.venv/bin/python tests/e2e/board.py`：46/46。原日志及开发门禁输出已私有复制进保全目录。

生产PIN浏览器和平板实机浮窗未执行；没有取得实际PIN，不绕过入口认证。生产通过只读版本/资源/数据/权限核对，页面交互通过合成Vault的精确release真实浏览器验证。

## 生产与 GitHub

发布源码提交 `de1e62d7e5807407851db6c96dae47d9314e17e3`（v2.3.2），由精确Git归档生成 `/root/workspace/apps/releases/omrs-de1e62d`，1,140个源码文件逐字节校验通过；`.venv`相对链接复用旧依赖。发布前和停服后核对五个运行库未终结任务均0，没有整库恢复journal或正式题目写入意图。

保全目录 `/root/workspace/apps/releases/OMRS-v232-release-20261004T085918Z-mazifnus/` 为0700，完整 `错题/` 与 `.omrs-maintenance/` 原样tar、精确源码、旧unit/drop-in、发布脚本、私人逐表/文件对照、验证日志与SHA清单均0600；tar比较和刷盘通过。仅原子替换主服务drop-in的三处代码路径，2026-10-04 17:01:10 CST启动新版，停服保全至就绪2.20秒。主服务PID1287908，active/running、NRestarts=0；Tunnel、检测服务和Nginx状态/进程保持，模型指针、管理状态与控制配置SHA一致。

生产只读核对：48张原业务表全部原行/列与828个正文/图片/报告/配置/PIN/Key文件SHA保持，全部SQLite完整性通过，活动题262、待审0。版本v2.3.2，版本化展示板CSS返回字节与精确release一致并包含高度修复；主模块gzip、immutable缓存和ETag 304、主样式合并通过。公网入口/会话查询200，匿名状态/审批计数/MCP/工作台模块401；入口和公开场景脚本gzip验证通过。没有生产测试业务写、依赖升级、发布失败或数据回退。

已执行 `git push origin main`，正常快进 `8624875..de1e62d`；`git ls-remote --heads origin main`核对远端SHA与发布源码一致。发布文档收尾独立提交继续正常推送；不强推，不创建标签或GitHub Release，私人保全和数据库不进入Git。

收尾已实际执行 `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff de1e62d`：102份文档0问题，2条既有大型计划提醒，退出0；`git diff --check`退出0。实际变化复核仅剩 `AI/environment.md` 与本日志，作为发布记录提交，生产源码已验证，不再次部署或重启。主服务自17:01启动以来错误级journal无记录。

## 下一步

代码、v2.3.2发布与GitHub源码推送已完成；发布记录随本次收尾提交继续正常推送。用户刷新并按原PIN重新登录即可使用。平板实际浮窗的触摸与系统窗口缩放可在使用中验收。
