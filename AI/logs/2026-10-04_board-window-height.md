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

首次展示板E2E出现3项失败：旧入口停在锁屏，测试适配器又沿原未版本化地址导入，得到独立预览单例。使用共享 `open_app` 并跟随主模块资源根路径后，主路径、响应式与选板全绿；仅调整测试基础设施，不改变生产授权行为。

所有测试服务使用合成临时Vault和随机端口，清除生产控制环境变量；生产只做已获授权的发布与只读验收，不写测试业务数据。未重复无关全量后端/E2E，未执行实物打印和平板实机浮窗验收。`python3 tests/check_docs.py --write-log-index` 与 `python3 tests/check_docs.py --diff 8624875` 已执行：102份文档0问题，2条既有大型计划篇幅提醒。精确release与生产结果在发布后继续记录。

## 生产与 GitHub

待本地门禁与精确release验证完成后，停服原样保全、原子切换主服务代码目录，正常快进推送main并核对远端SHA；不强推，不创建标签或GitHub Release。私人保全和数据库不进入Git。
