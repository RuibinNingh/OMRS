# 维护者运行环境与协作配方

> **速查**
> - 职责：三类维护者的运行环境、可用工具、做不到的事，以及隔离实例、远端模拟、交付补丁的做法
> - 入口：`AGENTS.md`「维护者与运行模式」（规则）；本文件只记事实与配方
> - 不变量：能力以实测为准，每条都注明探测日期；过期或不确定的写「待确认」，不臆测
> - 必跑测试：—（环境文档；改动后运行 `python3 tests/check_docs.py`）
> - 相关：`AGENTS.md`、`AI/README.md`

## 1. 三类维护者

| 维护者 | 模式 | 源码来源 | 能做 | 不能做 |
|---|---|---|---|---|
| Hermes Agent | 完整 | 本机 Git 工作区 `/root/workspace/apps/OMRS` | 任意命令、联网、Git 提交、systemd、生产验收（须用户授权） | — |
| Codex | 完整 | 同上 | 同上 | — |
| Claude Code Web | 受限（含规划模式） | 用户上传的 `OMRS-source-sanitized-*.zip` | 本地跑全部单测、隔离实例、无头浏览器端到端、截图；写执行说明 | 联网、Git 远端、systemd、生产服务、读取 `错题/` 真实数据和 `AI/logs/` |

生产环境事实（2026-10-04 实测）：服务 `omrs.service`，`Type=simple`、`Restart=on-failure`、`RestartSec=3s`；有效 systemd drop-in 从 `/root/workspace/apps/releases/omrs-b466c58` 运行 v2.3.1，来自精确 b466c58 的 Git 归档，1,139个源码文件逐字节校验通过。`.venv`相对链接复用 `/root/workspace/apps/releases/omrs-bbf3757/.venv`，未安装或升级依赖；Python3.13.5、MCP SDK1.28.1、Pillow12.3.0 已核对。真实Vault仍是 `/root/workspace/apps/OMRS`。

Web监听8471，同进程MCP只监听127.0.0.1:18472；Nginx共用HTTPS8472按路径分流。启动参数公网MCP为 `https://home.ruibin-ningh.top:8472/mcp`，公网Web为 `https://home.ruibin-ningh.top:8472`。PIN已配置；本机API免PIN不能绕过主工作台入口。当前源码提供40个MCP工具，按Key现有权限发现；只读22工具。正式计划创建需omrs:read与session:create，先返回待审操作；改题提案需omrs:read与默认关闭的question:propose。既有Key不自动扩权。

当前v2.3.1发布保全位于 `/root/workspace/apps/releases/OMRS-v231-release-20261004T072046Z-kfh3o6yo/`（目录0700、文件0600），含停服原样归档的完整 `错题/` 与 `.omrs-maintenance/`、旧unit/drop-in、精确源码归档、部署脚本、私人业务表/文件对照和SHA清单；tar比较通过。代码切换只替换主服务drop-in的三处release路径，端口、公网URL及控制配置保持。旧de10022 / b41a65a release、既有保全与共享依赖仍保留。

v2.3.0保全仍位于 `/root/workspace/apps/releases/OMRS-v230-release-20261003T092803Z-6u51wcwh/`。当前v2.3.1沿用其数据库契约，不新增schema迁移；恢复仍须保全当前数据，不以旧Vault归档覆盖上线新增事实。

v2.3.0的新权限scope、JSON/YAML编码、统一审批与正式题目journal使直接旧码写入存在契约风险。发布后恢复须保留最新数据，使用兼容当前数据的修复版本前向恢复；禁止把旧Vault归档覆盖上线后新增事实，不能仅恢复旧drop-in便当作安全降级。

最新历史正文补回保全位于 `/root/workspace/apps/releases/OMRS-content-recovery-20261003T010842Z-uvv8l1w4/`（目录0700、文件0600），含一致ZIP、两次停写原库、私有正文清单、来源和逐字段核验。原升级保全OMRS-v220-upgrade-20261003T003307Z及旧release仍保留。当前1个归档身份、262活动题、零冲突；269个原正文blob与15个核验补回版本均可取回，六个实库的原业务行及1,203助手事件保留。48个首次正文快照前的历史版本仍缺原文，当前题目正文完整。

v2.2.0存储迁移后不能仅回退v2.1.0代码，也不能用旧归档覆盖上线新增事实；保留最新数据并使用兼容当前契约的修复版本前向恢复。具体升级/失败边界及实际生产验收见 `plans/omrs-audit-repair/release.md`。旧release及依赖目录保留。

本机可靠副本中的历史正文可用 `content-recover --manifest <私人清单路径>` 预览，明确加 `--apply` 才补入；不通过它还原当前题目或覆盖原始流水。先取得一致备份，在隔离副本验证所有业务字段和原始事实保持，再按生产授权执行。清单格式、只补缺失、幂等与事务失败边界见 `ledger.md` §10；禁止将正文、私人路径清单或数据库提交到源码仓库。

主服务、`tunnel-client-omrs.service` 和 `omrs-boxdetect.service` 均active/running、NRestarts=0；主服务PID1011719、Tunnel PID875442、检测PID1532134。主服务于2026-10-04 15:22:38 CST启动，最终切换2.66秒；另外两个服务与Nginx未重启，模型active指针及管理状态SHA、Nginx配置、端口、PIN和Key权限保持。

当前精确release与既有venv的7个资源/HTTP/安全/MCP/备份模块78项通过、无跳过，均使用临时Vault与随机端口；真实浏览器路由/PIN/手机/刷新验收24项通过。当前发布无数据库迁移，停服前后只读核验保持48张原业务表全部原行/列和828个原文件SHA，活动题仍为262，待审0。版本四档截图只出现桌面侧栏版本文字变化，无脚本错误。

实际生产只读核验确认版本化模块返回私有immutable缓存、gzip字节解压后与release一致，主样式合并且条件请求304保持。公网入口与公开场景脚本实际gzip返回200，未登录的status、审核API、MCP和版本化工作台模块均返回401。未在生产创建验收Key或执行测试业务写，未使用真实付费模型；完整公网工作台计时、生产PIN浏览器、ChatGPT账户联调及Windows实机仍待验证。

## 2. Claude Code Web 实测能力（2026-09-24）

- **系统**：Ubuntu 24.04.4，1 核 CPU、4GB 内存；Python 3.12.3，Node 22.22.2 / npm 10.9.7，git 2.43.0。
- **Python 包**：Pillow、playwright（自带 Chromium 141，可无头运行）、numpy、pandas、openpyxl、python-docx、python-pptx、bs4、lxml、requests。没有 pytest，一律用 `unittest`。
- **命令行**：有 zip/unzip、curl/wget、pandoc、pdftotext、ImageMagick `convert`、`file`；没有 rg、jq、sqlite3、xxd、systemd。
- **网络**：出站被代理拒绝（访问 pypi 返回 403），不能 `pip install` 或 `npm install`。
- **路径**：上传文件只读，在 `/mnt/user-data/uploads/`；工作目录 `/home/claude/`；交付文件放 `/mnt/user-data/outputs/` 供用户下载。
- **网卡**：容器有一个非回环地址（实测 `192.0.2.2`，以 `hostname -I` 为准），可用来模拟「远端设备」。
- **限制**：单次工具调用超过约 2–3 分钟会被中断；每轮工具调用次数有限；命令输出含不完整的 UTF-8 字节时整条输出会被拒收。

## 3. 探测命令（开工第一步）

```bash
python3 --version; node --version; git --version
for c in zip rg jq sqlite3 curl systemctl; do printf "%s:%s " $c $(command -v $c >/dev/null && echo y || echo n); done; echo
python3 -c "from playwright.sync_api import sync_playwright as p; b=p().start().chromium.launch(); print('chromium', b.version)"
timeout 5 curl -sS -o /dev/null -w "net:%{http_code}\n" https://pypi.org; hostname -I
```

## 4. 受限模式配方

**建基线。** 先解压，再把导出包原样提交为基线：

```bash
unzip -q /mnt/user-data/uploads/OMRS-source-sanitized-*.zip -d /home/claude && cd /home/claude/OMRS
git init -q && git add -A && git -c user.email=ccw@local -c user.name=ccw commit -qm "baseline <导出时间>"
```

**门禁。** 预期计数以最新任务日志为准：

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -q
node --test tests/app/*.test.mjs tests/app/*.test.mjs
python3 tests/check_docs.py --diff <基线提交>
python3 tests/check_ui.py          # 前端纪律与旧代码棘轮，见 AI/frontend/design-system.md
python3 tests/check_contrast.py    # 设计 token 对比度
python3 tests/app/run_browser.py   # ui 组件浏览器单测（需 playwright）；--shots DIR 另存 gallery 截图
python3 tests/e2e/ui_bridge.py     # 过渡桥主路径 E2E：自建 fixture Vault 与隔离实例
python3 tests/e2e/shell_router.py  # 路由、刷新停留、前进后退、外壳与 304 的 E2E（同上）
python3 tests/e2e/instant.py       # 即时练习主路径与审计（同上）
python3 tests/e2e/feedback.py      # 反馈录入主路径、导入与审计（同上）
python3 tests/e2e/questions.py     # 题目库主路径（筛选 / 视图 / 键盘 / 批量 / 视图预设 / 旧入口）、题目弹窗（焦点、叠加浮层、Markdown 编辑器）、D4 与审计（同上）
python3 tests/e2e/board_picker.py  # 选板浮层：键盘、过滤、折叠、连加 / 撤回、新建、叠在弹窗上、居中与审计（同上）
python3 tests/e2e/annotate.py      # 独立框选标注页：上传、画框、快捷键、导出、训练页入口与四档审计（同上）
```

**隔离实例。** 用临时 Vault 和高端口启动，`</dev/null` 防止依赖检查等待输入：

```bash
mkdir -p /tmp/v/错题 && python3 omrs_engine.py --vault /tmp/v create --subject 数学 --category 函数 </dev/null
(setsid python3 omrs_engine.py --vault /tmp/v serve -p 18471 </dev/null >/tmp/omrs.log 2>&1 &); sleep 3
curl -s http://127.0.0.1:18471/api/auth/session
```

**演示数据。** `tests/fixtures/make_vault.py` 生成不含真实数据的 Vault：`full` 档约 40 题，含 LaTeX、长题面、3 张示意图、标记、3 轮反馈、1 道停用题和 1 块展示板；`empty` 档是空库，专看空状态。标记、反馈等经临时实例的 HTTP API 写入，全程约数秒：

路由与 PIN 的 `tests/e2e/shell_router.py` 使用合成静态入口背景；默认黑洞 WebGL、自定义背景及窄屏显示由独立 `tests/e2e/entry_background.py` 验证。普通页面验收使用 `tests/browser_runtime.py` 的 `open_app`，入口专项仍走真实锁屏与登录请求。

```bash
python3 tests/fixtures/make_vault.py --out /tmp/fx/full
python3 tests/fixtures/make_vault.py --out /tmp/fx/empty --profile empty
```

**公网加载实测。** `python3 tests/bench_web_load.py --out /tmp/omrs-web-load.json` 自建演示 Vault、随机端口和浏览器上下文，默认模拟 100ms 延迟、5Mbps 下载，每次分别测冷启动和真实刷新。可用 `--tree <基线源码目录>` 比较同一命令下的版本，`--runs` 调整次数；`OMRS_TEST_CDP_URL` 沿用受信任本机 CDP 配方。结果包含仪表盘数据就绪时间、CSS / JS 请求数、传输字节、缓存与脚本错误，不接生产端口或真实数据，不把偶发时间波动作为功能门禁。

**前后截图对比。** `tests/visual/run.py` 用 `git worktree` 检出基线，与当前工作区各起一个实例、各喂同一份 fixture 副本，按 12 页 × 浅/深 × 桌面 1440 / 手机 390 截图并做像素差分。产物是 `report.html`、`audit.json`（每页字号种数、最小字号、小于 28px 的可点目标、行内样式数、横向溢出），仓库里不存金标图。审计只计非空 `style` 属性，字号和行内样式均排除 KaTeX 内部。页面内冻结 `Date`、注入样式关闭动效；服务端实时内容在脚本的 `MASKS` 里登记后截图时遮住。约 1–2 分钟，放后台轮询：

```bash
(timeout 600 python3 -u tests/visual/run.py --ref <基线提交> --out /tmp/vis > /tmp/vis.log 2>&1 &); sleep 100; cat /tmp/vis.log
python3 tests/visual/run.py --audit-only --fixture empty --out /tmp/aud   # 只审计当前工作区
```

**模拟远端设备。** 本机 CLI 请求不带 `Origin`，可以直接改配置。依次设置 PIN、开启外部访问、重启，然后轮询 `instance_id`，变化后用 `http://<hostname -I 的地址>:18471` 访问，服务端会把它当作远端：

```bash
curl -s -H 'Content-Type: application/json' -d '{"pin":"2468","idle_minutes":30}' http://127.0.0.1:18471/api/auth/pin
curl -s -H 'Content-Type: application/json' -d '{"allow_external":true}' http://127.0.0.1:18471/api/config
curl -s -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:18471/api/restart
```

**长任务放后台。** 服务、端到端脚本都放后台，分次轮询日志，每次调用控制在 2 分钟内：

```bash
(timeout 600 python3 -u e2e.py > /tmp/e2e.log 2>&1 &); sleep 100; tail -20 /tmp/e2e.log
```

**交付补丁。** 生成补丁后，必须在干净的导出包上验证能应用：

```bash
git add -A && git diff --cached <基线> > /mnt/user-data/outputs/changes-<日期>.patch
mkdir /tmp/chk && cd /tmp/chk && unzip -q /mnt/user-data/uploads/<原始导出包>.zip && cd OMRS && git apply --check /mnt/user-data/outputs/changes-<日期>.patch
```

视觉脚本传入 `--pages assistant` 时会给隔离 fixture 开启 `agent_enabled` 并注入 `tests/fixtures/agent_faux.json`，可对助手欢迎页、输入区和处理过程做浅 / 深色桌面与手机截图；不会连接真实模型。

新审核中心使用 `python3 tests/visual/run.py --audit-only --pages ai-review --out /tmp/omrs-review-audit` 独立审计；脚本在临时 Vault 创建合成草稿、正式题目、有限修改提案与自动写记录，打开真实待审详情截图，不写生产数据。中心新增前的基线没有该路由，既有录入、助手、历史与设置页仍用 `--ref <基线> --pages create,assistant,history,settings` 前后比较。320 / 390 / 1024 / 1440px 和双标签未保存保护由 `tests/e2e/ai_review.py` 实跑；样式审计按既有规则排除 KaTeX 内部的生成属性。

AI 助手没有网络也能完整测试：启动服务前设环境变量 `OMRS_AGENT_FAUX_SCRIPT=tests/fixtures/agent_faux.json`，运行时改用脚本化假模型（按最近一条用户消息选场景，模板可引用之前的工具结果），再在 `config.json` 里设 `agent_enabled: true`。`tests/e2e/assistant.py` 就是这样起隔离实例的。

P4 分类和草稿修订路径使用独立的 `tests/fixtures/agent_p4_faux.json` 与 `tests/e2e/p4_tools.py`；脚本自己创建临时 Vault、随机端口并清除 `OMRS_SYSTEMD_SERVICE`，在 Chromium 中确认分类、审核修订卡和零题候选。

聊天练习卡场景写在 `tests/fixtures/agent_faux.json`，`tests/e2e/practice.py` 使用临时 Vault、随机端口与真实 Chromium，覆盖从聊天卡进入即时练习、刷新续练、反馈丢响应后重试、部分成功及重练请求恢复；该脚本不接真实模型或生产数据。

## 5. 已知坑

- **缺模块。** 旧版导出只含 Git 已跟踪文件，未提交的模块会缺失，导致包无法 import。现行导出按目录收集并包含未提交源码；若再遇到缺失，先报告，不要在交付物里补替身。
- **Playwright 独立 Chromium 在本机可能崩溃。** `chromium.launch()` 打开 OMRS 页面可能返回 `TargetClosedError: Page crashed`，而 Hermes Browser Use 的 Chrome/CDP 可正常访问；不要仅凭此判为 OMRS 服务故障。若环境变量 `OMRS_TEST_CDP_URL=http://127.0.0.1:9222` 指向受信任的本机 CDP，测试可复用共享 Chrome，但每项测试必须只关闭自己创建的 BrowserContext，不能调用 `Browser.close()` 关闭共享实例。CDP 只绑定本机可信端点，不要暴露公网；独立 Chromium 崩溃原因未确认。
- **测试实例会重启生产服务。** `/api/restart` 只要在进程环境里看到 `OMRS_SYSTEMD_SERVICE`，就执行 `systemctl restart <该服务>`（见 `omrs/server.py`）。完整模式下启动任何测试实例之前，都先 `unset OMRS_SYSTEMD_SERVICE`；设置页相关的 E2E 用 `page.route` 拦截 `/api/restart`。
- **Playwright 的 `text=` 是子串匹配。** 它会点中含同样字样的说明文字。按钮一律用 `get_by_role("button", name=..., exact=True)`。
- **刷新后立即操作会失败。** 普通应用页可用 `tests/browser_runtime.py::open_app` 明确设置入口参数并等待 `window.__omrs`、当前路由与活动面板就绪；入口与 PIN 专项直接访问 `/`，否则点击发生在脚本加载之前。
- **截图时机。** 面板淡入 0.3s、开关过渡 0.15s，切换后至少等 0.9s 再截图，否则画面发灰或开关状态看起来不对。
- **HTTP 风险提示。** 远端 HTTP 登录会弹一次 `alert`，需要注册 `page.on("dialog", ...)` 自动确认。
- **中文输出。** `cut -c` 按字节截断会切坏中文，导致整条输出被拒收。要截断时用 Python 按字符处理。
- **`pkill -f` 会杀掉自己。** 模式串出现在本条命令里时，`pkill -f` 会连同执行它的 shell 一起结束，工具调用返回 -1。按端口查进程时写成 `pgrep -f "[s]erve -p 18471"`，或在启动时记下 PID。
- **不要运行 `--write-log-index`。** `AI/logs/` 在包内只有本次新建的日志，生成出来的索引不完整；交给完整模式运行。

## 6. 完整模式接手配方

**合入 CCW 交付。**

1. `git status --short` 记录现状。
2. 按任务日志「合入」一节运行 `git apply --3way <补丁>`（2026-09-26 之前的交付，按它自带的 UPGRADE 文档）。
3. 跑门禁：`unittest`、`node --test tests/app/*.test.mjs`、`python3 tests/check_docs.py --diff HEAD`、`python3 tests/check_ui.py`、`python3 tests/check_contrast.py`。
4. 运行 `python3 tests/check_docs.py --write-log-index`，审阅 `AI/logs/log.md` 的 diff 后提交；生成器会跳过 Git 明确忽略的本机私人日志。
5. 「合入」一节列出的生产验收，须用户授权后再做，结果补进对应的任务日志。

**按执行说明开发。** 执行说明在 `AI/plans/<计划>/exec-*.md`，规则见 `AGENTS.md`「按执行说明执行」。

- 生产服务如果运行在本机工作区里，开发一律放到 `git worktree` 里做，生产目录只在授权部署时才改动。
- 浏览器测试在本机崩溃时，按第 5 节设置 `OMRS_TEST_CDP_URL`。
- 正文覆盖率可用 `python3 omrs_engine.py --vault /path/to/vault content-audit --json` 只读盘点。命令不初始化或迁移 Ledger，不输出正文；JSON 分列当前缺 blob、文件与投影冲突和历史缺口。未授权时只做只读审计，真实 Vault 的增量回填须单独授权；隔离验证仍使用临时 Vault 与随机高端口，并在启动前去掉 `OMRS_SYSTEMD_SERVICE`。

## 7. 本地框选训练环境

CPU 训练使用仓库外 `~/omrs-train/.venv/`，精确依赖在 `tools/boxdetect/requirements-train.txt`，服务依赖另列 `requirements-serve.txt`。数据只读原 Vault，产物写外部目录。训练以 nice 19 限制优先级，线程数最多 6，并监控可用内存；可用内存不足 2 GiB 时停止训练。数据构建与系统 Python 单测不加载 torch／onnxruntime。

训练面板文件与 HTTP 门禁：`python3 -m unittest tests.test_trainpanel -q`，使用临时 Vault、假训练目录与随机本机高端口；路由提取已登记 `_trainpanel_get` / `_trainpanel_post`。

## 草稿工作树验证

AI 草稿的开发与浏览器测试使用独立 Git 工作树，服务仍从临时 Vault 与随机高端口启动。`tests/check_docs.py` 的路由发现清单包含 `_drafts_get` 与 `_drafts_post`，新增草稿路由后由 `--write-routes` 更新总表。文档索引必须在完整模式按实际日志文件生成。


训练面板浏览器验证：`python3 tests/e2e/trainpanel.py` 用临时 Vault、假实验与假检测服务，覆盖进度／曲线刷新、积累及四档状态审计。真实模型链路：`python3 tests/e2e/boxdetect.py --dataset ~/omrs-train/datasets/20260929-1 --shots /tmp/omrs-box-detect-real`，从外部数据快照取测试图，临时启动回环检测服务与隔离 OMRS，不写真实 Vault。截图不进 Git。

视觉比较可加 `--create-stage train` 切到录入页 AI 训练工作区，例如 `python3 tests/visual/run.py --ref e40e6b8 --pages create --create-stage train --out /tmp/omrs-box-detect-visual`；不传该选项时保持默认工作区。运行测试前仍须去掉 OMRS_SYSTEMD_SERVICE。

设置页视觉比较可用 `--pages settings --settings-section ai` 定位 AI 识别分区，基线与当前工作区都会先切换到该分区再截图；不传时仍按上次保存的设置分区显示。

内容评测门禁 `python3 -m unittest tests.test_trainaudit -q` 使用假响应与临时目录，覆盖请求预算、429重试、缓存恢复、原判不可变和HTTP复核冲突，不消耗付费额度。训练看护同时读取宿主机和cgroup v2当前层/祖先内存剩余额度；读取失败拒绝启动，workers固定0。测试产物与真实评测均在仓库外。

视觉工具支持 `--pages trainpanel`，基线与当前都直接打开独立 `/train`，与主站路由区分。评测详情由面板E2E另行以假记录覆盖桌面/手机与浅深主题。

## 本机检测生产服务

`omrs-boxdetect.service` 与主服务分开，开机自启、失败 3 秒后重启，使用训练 venv 的 onnxruntime 执行固定发布目录的 serve.py；只监听 127.0.0.1:18766。受管模型入口为 `/root/omrs-train/managed/active`；当前实际在线 `v2-20260929-b`，SHA-256 为 `f62581b7c28353d5d7799973018a6986e706cd7dcf4fb43ccd10972be4a4c7c3`，输入 640、置信度 0.1，独立内容验收状态为 missing。服务启动加载一次，不热加载训练目录的 current；主服务本次发布没有切换此模型。

资源限制：ORT内部3线程、systemd CPUQuota=200%、MemoryHigh=512M、MemoryMax=1G、Nice=10，启动内存约60MiB。`systemctl status omrs-boxdetect.service`查状态，`journalctl -u omrs-boxdetect.service`查错误；`systemctl start/stop/restart omrs-boxdetect.service`会影响线上框选，仅在获得授权后操作。主应用配置local_http及http://127.0.0.1:18766/detect，浏览器不直接访问检测端口，不需Nginx增加路由。

主服务代码回退只恢复本次备份的主服务 drop-in，执行 daemon-reload 后重启；检测服务和受管模型独立运行，不随主服务代码回退自动切换。当前提供方与 URL 未改变，无需回写配置。真实 Vault 备份只供专项恢复，不用旧归档覆盖上线后新增题目；候选的内容验收状态仍须在服务操作历史中核对。

## 受管检测服务安装与验证

安装登记、初始化映射及unit调整步骤见tools/boxdetect/README.md；未登记实例不提供控制能力。候选预检使用systemd-run独立临时单元，MemoryMax=768M、RuntimeMaxSec=30、CPUQuota=200%；结束后清理临时单元，主程序不导入训练框架。要求有效可用内存至少2GiB，并与training.lock互斥。

隔离门禁：`env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_traincontrol -q`；`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/traincontrol.py`。浏览器脚本只注入测试后端，不操作生产unit。正式服务仍限1GiB，登记精确绑定真实Vault，避免隔离实例继承环境误操作。

主服务已通过 `OMRS_BOXDETECT_CONTROL=/etc/omrs-boxdetect-control.json` 登记固定 unit、Vault 与端口；`/train` 可以管理服务、显式应用完整导出候选并回退。受管 revision 当前为 1，实际在线 `v2-20260929-b` 且与配置指针一致；主服务与检测服务均开机自启。

框选流程视觉对比使用 `python3 tests/visual/run.py --ref <基线> --pages create --create-stage process`，会在临时 fixture 中放入一张合成题图与题目／答案两个待提取框，基线和当前使用完全相同的数据；提取结果态由录入 E2E 的四档截图及审计覆盖。

## MCP 隔离验收

`tests/test_mcp_protocol.py` 用官方可选 SDK 启动随机高端口的同进程 Web/MCP，真实读取临时 Vault 并校验原件字节、权限和正式数据不变。`tests/e2e/mcp.py` 先走 `get_question → images[] → get_question_image → ImageContent`，核对 PNG/JPEG/GIF 的 MIME、原始尾数据及学习 Ledger 提交不变，再在同实例打开草稿与 Key 管理页面。SDK 验收不能以 SKIP 代替通过；`tests/test_mcp_http.py` 和 `tests/test_mcp_keys.py` 可在无 SDK 环境验证标准库边界。所有实例移除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`。

视觉脚本的 `--create-stage drafts` 自动注入三份多文字块、公式和合成来源图草稿，基线与当前工作区共用同一份夹具；测试直接访问已授权的本地 `/?unlocked=1` 外壳，避免停在锁屏。

草稿 P4 鼠标验收在获取缩放柄坐标前等待来源图片加载，并通过 hover 等平滑滚动稳定与命中检查，随后执行真实拖动；避免布局移动让拖动落到画布外，保存和人工调整断言保持完整。

展示板夹具写入先读取 /api/boards 的目录和板版本，按当前 CAS 契约建板；并发验证独立保留旧版本以实测 409，不使用夹具 helper 自动刷新来掩盖冲突。视觉比较可用 --pages board 限定四组主题/屏幕组合。

MCP 扩展闭环由 tests/e2e/mcp_expansion.py 启动真实临时 Web/MCP 服务并用 SDK 与浏览器验证；tests/test_mcp_board.py 覆盖确认幂等/崩溃/纸面边界。所有实例清除生产控制环境变量。路由生成器同时枚举 _mcp_get/_mcp_post。

## 8. 审计修复回归入口

`tests/browser_runtime.py` 的 `app_url`／`open_app` 为普通页面提供明确主应用地址和就绪等待；不会替代 PIN 认证。`tests/e2e/shell_router.py` 保留入口点击与 PIN 路径，普通刷新／跳页使用该入口；`tests/e2e/instant.py` 展开仪表盘建议后验证跨页预设，不依赖被折叠按钮可见。

前端审计行为测试为 `tests/app/audit-controllers.test.mjs` 和 `tests/app/audit-identity-uploads.test.mjs`，直接导入当前模块与控制器，覆盖并发裁图、反馈部分失败、旧响应、稳定身份、分块原始字节、业务午夜和历史分页。全部数据合成，浏览器服务只用临时 Vault 和随机高端口，清除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`。


统一入口为 `python3 tests/run_gates.py --ref <本次改动基线>`，显式包含 unittest、pytest 风格报告导出、Node、组件浏览器、打印冒烟、全部不依赖外部模型材料的原始 E2E、升级/回退演练、视觉及文档门禁。`--ref` 只用于文档差异与视觉比较；升级演练使用独立的 `--upgrade-ref`，默认 `17d6d84`，必须保留历史旧唯一索引与 UID-only Session 语义，不能以已完成迁移的任务基线替代。结果 JSON 同时记录两种基线。`--only` 按门禁 ID 重跑失败项，结果与每条日志保存在临时目录。真实 ONNX `boxdetect` 需要外部冻结数据与模型，只有传 `--dataset` 才加入，并明确记录缺失原因。

助手浏览器实例经 `tests/fixtures/serve_diagnostics.py` 启动同一 CLI，只在临时服务日志记录审核计数异常的 SQLite 类型和消息，不记录请求、正文或凭据，不改变 HTTP 错误响应。`tests/e2e/assistant.py` 的服务日志保留在临时目录 `omrs-ast-server-*.log`，失败时输出对应路径，便于定位首次建库并发错误。

容量验证使用 `tests/bench_data_runtime.py` 生成合法合成 Ledger、真实 Markdown 和 blob；`tests/bench_backup_runtime.py` 实测磁盘 ZIP、目录交换和真实 HTTP 启动。所有实例清除生产控制环境变量，固定种子、随机高端口和临时 Vault。RSS 在 Linux 取独立进程 `VmHWM`，不用继承的父进程峰值假定内存；计时、样本数、P50/P95与冻结时间随结果交付。HTTP 就绪用快速认证状态端点，统计接口另给完整请求期限，避免容量报告把一秒探测超时误认为启动失败。

发布兼容演练为 `python3 tests/check_upgrade_compat.py --ref 17d6d84`，此处 `--ref` 专指历史夹具的旧提交；脚本将旧代码归档到仓库外空目录，新旧进程仅访问合成 Vault，逐项校验事实不变、归档身份、旧缓存失效和当前备份恢复。统一门禁通过 `--upgrade-ref` 向它传参。退出 0 不表示可直接降级：工具主动记录旧代码的 UID-only Session 错归属风险，发布采用保留当前事实的前向修复策略。

核心业务日期转换不强制依赖外部 `tzdata`：系统没有 IANA 数据库时，上海 1992 年起的时间使用 UTC+08 固定偏移；更早历史与其它缺失时区不猜夏令时。`tests/test_data_runtime.py` 模拟 `ZoneInfoNotFoundError`，通过真实反馈、上海午夜历史与完整重放验证该路径；这项模拟不代替 Windows 文件锁或目录恢复的平台实测。

配置发布回归为 `python3 -m unittest tests.test_config_publication -q`，以真实独立 Python 进程与持久 SQLite 事务覆盖镜像写入、旧发布者、响应窗口、WAL 读取快照和投影策略读取；另验证审计失败时回滚配置／投影／重算回执、空库迁移以及待同步镜像第三方冲突。屏障只控制时机，配置、文件与提交均实际执行，不访问真实题库。

`tests/e2e/audit_identity.py` 在真实临时服务验证旧计划人工绑定、归档与新题同 UID 的板内身份隔离、超过 16MiB 原图字节保持，以及 66 对话／45 运行／411 事件的全部历史可读；翻早页核对长消息展开态和 DOM 保留，同 UID 不同身份的迟到题面响应不覆盖新挂载。

容量工具默认`--samples 5`，每条路径每个样本复制同一合成基线；参数重算不因前一次参数相同被跳过，十万修正不叠加为五十万。普通反馈内部50次计分单独统计。P95使用最近秩，5样本P95为最大值，不能理解为长期流量分布。直接`--action`只接受本工具带合成标记的`/tmp/omrs-data-capacity-*`、无符号链接库，入口先清生产控制变量。升级工具`python3 tests/check_upgrade_compat.py --ref 17d6d84`使用Git归档和合成Vault，结果明确旧码直接回退不安全，按发布材料前向修复而不覆盖新增。

## 正式题目审核恢复验证

`env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_question_update tests.test_backup_recovery` 全部使用临时 Vault。题目专项以真实独立 Python 进程在文件替换与 Ledger 提交窗口调用 `os._exit`，验证链头、稳定身份、精确 inode 所有权和同事务回执；没有生产服务或真实数据替身。无法证明无后续事实时正常启动拒绝继续，保留 `.omrs-maintenance/question-updates/`；只读 `content-audit` / `content-recover` 也不抢先执行恢复。

正常 CLI 顺序为目录交换恢复、正式题目写入恢复、配置和逐卡回执、扫描与正文回填、统一审核初始化、助手中断恢复，最后启动工作区扫描及 HTTP 监听。全库备份在捕获前复用同一题目 journal 收束；整库恢复使当前库和备份中的未终结审核许可失效。具体文件、事实和旧世代规则见 `AI/ledger.md` 与 `AI/backup.md`。
