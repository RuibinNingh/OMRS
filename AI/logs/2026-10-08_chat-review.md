# 2026-10-08 对话内审核与 v2.3.7

## 背景

用户原话：「不合理啊,AI助手对话中的为什么要跳转到审核中心,太麻烦了吧,而且UI做的不太好 给我一个方案」；接受对话内轻量确认、复杂详情抽屉与回执收起方案后，明确授权：「可以,执行并且提交GitHub部署生产」。执行者 Codex，完整模式；开工 main / 36b97cc，工作区干净。截图仅作界面参考，不视作操作指令。已有审核中心计划已完成，本任务不改其历史范围和执行说明。

## 行为变化

- 轻量操作在聊天中展示影响并直接确认 / 拒绝。标记卡解释涉及、将变更、无需变更数量；完成后只用真实 changed / skipped / failed 回执计算。
- 完整预览、人工修订、草稿编辑复用中心控制器，桌面侧抽屉、手机全屏，聊天地址、输入、位置与焦点保留。关闭按钮、Esc、遮罩和离页保护未保存修改，保存失败不丢输入。
- 当前服务端状态替代重复的历史标签；批准待执行不等于成功。成功默认收起，失败 / 冲突 / 部分完成默认展开。历史只读，批准绑定已展示 revision，后台换版必须重新核对。
- 聊天草稿一次处理当前目标，入库后保留该回执；集中审核的队列推进仍保留。审核中心继续承担集中待办与记录。
- 发布版本 v2.3.7；后端接口、存储格式和权限不变。

## 影响文件

按 git diff --name-status 复核；未跟踪的新模块另用 git status --short 核对。

- assistant/review-cards.js、review-model.js、review-preview.js、view.js、index.js、assistant-run.css：当前状态、回执、内联决定、原位详情与单层卡片。
- ai-review/detail-panel.js、index.js、view.js、operation-view.js、drafts.js、drafts-review.js：共享详情控制器、局部事件、未保存守卫、读取失败重试与单份草稿。
- domain/ai-review.js、main.js：领域面板端口与装配；不允许 feature 跨功能直接导入。
- ui/drawer.js：关闭按钮同样检查 dismissible，允许恢复指定焦点。
- tests/app/ai-review.test.mjs、tests/e2e/assistant_review.py、assistant.py、ai_review.py、p4_tools.py：版本确认、当前回执、抽屉与原路径回归。
- AI/frontend 的 assistant、ai-review、architecture、components、design-system 分册，AI/environment.md、README.md：同步实际行为及验证配方。订正草稿样式目录。
- omrs/version.py、omrs_dashboard.html、README.md、AI/README.md、AI/changelog.md：版本与行为摘要；本日志与自动索引。

## 已执行验证

全部写入类测试使用临时 Vault、随机端口和脚本假模型；清除 OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL。

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：820 项，127.379 秒，OK，无跳过。
- 相关后端单测 test_ai_review、test_agent_review、test_agent_loop、test_agent_tools、test_ui_gates：64 项，OK。
- `node --test tests/app/*.test.mjs`：451/451，无跳过。
- `python3 tests/app/run_browser.py`：34/34；`python3 tests/check_ui.py`：0 问题；`python3 tests/check_contrast.py`：58 组，0 不达标。
- `python3 tests/e2e/assistant_review.py`：28/28；真实逐题回执、聊天焦点 / 输入保留、关闭按钮 / Esc / 遮罩 / 离页保护、失败保存保留、单份入库、320/390/1024/1440px 双主题草稿详情无横溢。截图位于 /tmp/omrs-chat-review-shots，已目视检查手机卡片和桌面草稿抽屉。
- `python3 tests/e2e/assistant.py`：59/59；`python3 tests/e2e/ai_review.py`：47/47；`python3 tests/e2e/ai_review_refresh.py`：56/56；`python3 tests/e2e/p4_tools.py`：11/11；`python3 tests/e2e/drafts_blocks.py`：59/59。
- `python3 tests/visual/run.py --ref 36b97cc --pages assistant,ai-review,create,settings --out /tmp/omrs-chat-review-visual-final`：16 组，无脚本错误。助手浅 / 深桌面差异0.033% / 0.030%、手机0.122% / 0.109%，均为欢迎页「审核中心批准后执行」改为「对话中确认后执行」，桌面另含版本文字。录入、设置、中心的6组桌面差异0.002–0.003%为版本文字，6组手机无差异；差异图已目视核对。实际操作状态另由新 E2E 截图覆盖。
- `python3 tests/check_docs.py --diff HEAD` 与 `git diff --check`：通过；日志索引用 --write-log-index 生成。

## 验证中发现与修正

初版直接跨 feature 导入被 UI 门禁拒绝，改为 main 连接 domain 面板端口。旧 E2E 仍等待 ast-gate，与新卡片不符；更新为真实待审卡与操作身份定位，保持业务断言。拒绝 / 冲突的人类错误曾被折叠隐藏，已保留。

中心动态 import 未版本化 drafts 模块会得到另一个未连接服务的实例；测试改用页面实际加载的版本化 resource URL。新测试先后修正合成配置值、等待 rAF 渲染、明确选择「留在当前」按钮，均不削弱回执与未保存断言。跨断点截图曾在共享抽屉入场动画途中判断横溢；改为等待动画完成后检查最终宽度，两端正文与控件保持。详情失败重试视图对不含 error 的历史测试状态作空值处理后，全量 Node 通过。

## 未执行验证与边界

没有运行全部历史 E2E、实体手机、Windows 浏览器或付费真实模型。生产不执行题库写入、入库或批准作验收；业务路径以隔离真实服务与 Chromium 验证。生产入口和实际新静态资源读回将在部署后记录。

## 发布

用户已授权 GitHub 提交与生产部署。先提交已验收源码，再从精确提交归档；复用既有生产依赖，停主服务保全当前 Vault 与控制配置。严格比较业务表 / 内容 / PIN / Key / 模型及相邻服务；失败只回退代码，不覆盖旧业务数据。生产实际结果另追加于本任务日志，文档提交不再次重启。

## 实际发布与最终读回

源码提交 `f61277f` 已推送 GitHub main，并远端读回一致。生产于2026-10-08 22:11:40 CST切到 `/root/workspace/apps/releases/omrs-f61277f`；精确提交 `f61277fddb2fb7fa3e6998d783f47b5f0a508cf9` 归档的1,264个文件逐字节一致，复用既有venv，无依赖安装。release下另实跑后端64/64、聊天审核28/28、刷新56/56。

保全目录 `/root/workspace/apps/releases/OMRS-v237-release-20261008T140957Z-3c9le11w/`：目录0700、文件0600，精确新旧源码、主服务unit/drop-in、实际Nginx/模型控制、一致Vault/maintenance与私人摘要保留；停服tar compare通过，独立解包933个文件逐字节相同且SQLite完整性通过。验证原始输出及哈希清单包含失败诊断证据，不提交真实数据或凭据。

- 主服务PID3456500，active/running、NRestarts=0，argv/cwd指向发布目录；停服冻结至健康核验3.762秒。只变主服务drop-in三处源码路径，Tunnel、检测服务和Nginx状态/PID保持。
- 严格业务摘要49张表不变；877个内容/关键配置文件、85个控制文件/模型指针不变。切换前后277题、扫描冲突0、待审0；基线在本轮切换前重新读取，不沿用旧日志278题。
- 本机16项新模块/样式及合并CSS实际200，gzip解压与release字节相同，immutable与ETag304均通过。公网匿名工作台资源16项401，入口与授权摘要200、status/MCP401，回环MCP无Key401，均符合既有鉴权。
- 本机与实际公网390px浏览器看到PIN入口，无横溢、无脚本错误；未登录或尝试业务写入。Tunnel三个健康接口均200；主服务错误级journal为空。

读回脚本最初错误要求匿名公网工作台资源200，被既有PIN保护返回401；纠正验证预期后通过。本机字节、缓存和版本断言保持严格，没有绕过鉴权或修改生产配置。后续 recheck 再次确认业务表、内容、控制和运行状态保持。

回滚时先保全当时最新数据、检查无活动写任务，再只恢复本轮保全的旧drop-in和v2.3.6兼容源码，daemon-reload并重启主服务；不得将旧Vault覆盖上线新增事实。旧release和保全保留。部署事实单独文档提交，生产仍固定运行源码提交，不为文档再次重启。
