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

生产环境事实（2026-10-12 23:09 CST发布并核验）：当前v2.6.0，运行源码为Git提交 `6b5cdbb2fca41b541c64291bb6e3bf7bb0f625f0` 的精确归档 `/root/workspace/apps/releases/omrs-6b5cdbb`，1441个源码文件与已验收工作区及Git归档逐字节一致。作业帮网关在同一仓库的services/zuoyebang，独立进程持有设备／账号／Key／审计；面板提供状态概览和管理弹窗，OMRS支持拍照／上传／粘贴取图、候选自动预览及原人工核对入库。

主服务omrs.service沿用原unit/drop-in，Type=simple、Restart=on-failure、RestartSec=3s；持久别名 `/root/workspace/apps/releases/omrs-9b29d49` 原子指向omrs-6b5cdbb。网关omrs-zuoyebang.service共用该别名和Python依赖，cwd为release/services/zuoyebang，运行数据在 `/var/lib/omrs-zuoyebang`（0700、文件0600），独立管理员初始密码在该目录的admin-secret.txt，不提交或输出。两进程真实cwd已核验，自动重启计数均为0。旧release、依赖和发布保全保留；回退恢复源码指针并保留最新Vault。

Python依赖仍为 `/root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv`，Python3.13.5、MCP SDK1.28.1、Pillow12.3.0、Playwright1.62.0、Segno1.6.6；当前浏览器缓存/root/.cache/ms-playwright包含对应1234版Chromium。共享CDP9222仅供可信本机隔离context，不关闭共享浏览器；完整摄像头流程使用独立Chromium的模拟媒体参数。发布验证TMPDIR须使用浏览器可访问目录，不能把候选1228缓存用于生产Playwright1.62。

Web8471、回环MCP18472、HTTPS8472和公开URL `https://home.ruibin-ningh.top:8472` 保持。Nginx同一server块的 `/zuoyebang/` 转发至回环8745，不新增公网端口；覆盖XFF，网关明确信任127.0.0.1/32，公开Origin固定为上述HTTPS源，管理Cookie为Secure/HttpOnly/Strict并限制到/zuoyebang/。OMRS已以外部HTTPS模式配置同机公开前缀及独立调用Key；本地／外部模式都需要Key。PIN、原MCP密钥与权限保持，匿名Web数据、MCP、网关调用和管理会话接口仍401。

生产切换前有效后台任务、审批及恢复意图均为0。当前停服保全在 `/root/workspace/apps/releases/OMRS-v260-release-retry-4zau6dy0/`（0700、文件0600），包含精确新旧源码、控制配置、Vault/maintenance、网关私有数据及一致性摘要。两份数据归档实际比较、解包1024个文件及8个SQLite库完整性通过。切换保留49张业务表、945个正文／图片／关键配置文件、301题、0冲突、待审0；网关设备、账号、密钥及设置保持。unit、Nginx、Tunnel、检测服务和模型配置保持。

已验收工作区在同一生产依赖下14/14组通过：后端68、Node496、网关52／4真实面板、前缀双进程18、设置75、原录入124、服务27、作业帮63、外壳24、组件34、UI0问题、58组对比度及8档前后视觉全部通过，无跳过。文档115份0问题（2条既有大计划提醒）；全部使用临时Vault及合成上游。发布归档与已验收源码逐文件核验，不把工作区运行冒称为归档目录重跑。

真实生产43项通过：源码及运行资源字节、公网未登录保护、HTTPS连接、匿名鉴权、私有文件及XFF拒绝、面板登录／概览／弹窗／Key元数据／来源IP／登出、Cookie属性、浅深色桌面与390px布局、OMRS PIN入口及未解锁直达保护，两服务稳定且无错误级journal。既有设备及账号配置保持，不自动联系官方；真实官方搜题、签名期限、付费模型及实体手机摄像头须另验。生产PIN后的录入操作未自动验证；配置PIN时须实际解锁并携带当前进程handoff，不能以直接访问unlocked参数代替。Windows打包未在本机运行。

启动会按稳定源身份将既有MCP运行记录导入为只读审核历史，并收束旧进程的审批，不再次执行业务；契约见 `ai-review.md` §5。发布预检按有效状态区分过期审批与有效未终结任务。原表摘要变化时须逐行核验来源、过期时间、正文、修订和结果；启动收束仅改变状态／时间／错误码的记录单独登记，不能忽略整表差异。原题目或审批业务事实变化、有效未终结任务或恢复意图仍阻止切换；历史追加和技术收束均不允许用旧Vault覆盖当前数据。

正式题目、标记整理journal与统一审批恢复保持最新数据；存在未完成恢复或整批写入意图时停止发布，不能靠切换旧源码跳过恢复。跨旧存储版本不能只恢复旧drop-in或旧Vault。原正文恢复保全及私人清单仍保留，当前正文可用性与历史缺口的规范见 `ledger.md` §10；禁止提交正文、私人路径清单和数据库。

A4固定字体与打印门禁为 `python3 -m unittest tests.test_export_fonts tests.smoke_a4_print -q`；统一门禁包含 `print-a4`，下载路径另由 `tests/e2e/schedule.py` 验证。刷新不闪动的隔离门禁为 `python3 tests/e2e/ai_review_refresh.py`。所有测试实例须清除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`，Windows Edge与实体手机须另验。

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

对话内审批门禁为 `python3 tests/e2e/assistant_review.py`，使用三个合成目标验证两道真实修改和一道无需变更，覆盖原位详情、焦点 / 输入保留、保存失败、关闭保护与单份入库。截图保存到 `/tmp/omrs-chat-review-shots`，可用 OMRS_REVIEW_SHOTS 指定临时目录；与全部浏览器门禁一样不连接生产数据或真实模型。

P4 分类和草稿修订路径使用独立的 `tests/fixtures/agent_p4_faux.json` 与 `tests/e2e/p4_tools.py`；脚本自己创建临时 Vault、随机端口并清除 `OMRS_SYSTEMD_SERVICE`，在 Chromium 中确认分类、审核修订卡和零题候选。

聊天练习卡场景写在 `tests/fixtures/agent_faux.json`，`tests/e2e/practice.py` 使用临时 Vault、随机端口与真实 Chromium，覆盖从聊天卡进入即时练习、刷新续练、反馈丢响应后重试、部分成功及重练请求恢复；该脚本不接真实模型或生产数据。

## 作业帮隔离验收

作业帮验收使用 `tests/test_zuoyebang.py`、`tests/test_zuoyebang_render.py` 和 `tests/e2e/zuoyebang.py`；可选依赖见 `requirements-zuoyebang.txt`，渲染须另安装 Playwright Chromium。正文夹具来自附件三道化学题的题干/答案，独立回归覆盖pid、域/IP限制、旧公式及MathJax3。专项E2E自建临时Vault和随机端口，去掉生产控制环境，仅替换作业帮及AI网络边界；真实执行HTTP上传、账号协议、本地二维码、后端Chromium、文件创建与Ledger，并覆盖账号菜单与440px预览/左侧弹性布局。摄像头使用浏览器fake-device的真实MediaStream，不能替代实体手机权限和设备验收。视觉比较可用 `python3 tests/visual/run.py --ref HEAD --pages create --create-stage zuoyebang`；有生成题图的八档截图由专项E2E保存。

专项产物包含真实1080长答案及末尾、八档页面截图、创建的合成 Markdown 和 checks.json；`OMRS_ZYB_SHOTS` 可指定产物目录。既有录入页用 `tests/visual/run.py --ref <基线> --pages create` 做前后比较，新工作区用专项八档审计。多块草稿 E2E 从审核中心入口进入，保留菜单、编辑、图文创建和窄屏回归。

## 5. 已知坑

- **缺模块。** 旧版导出只含 Git 已跟踪文件，未提交的模块会缺失，导致包无法 import。现行导出按目录收集并包含未提交源码；若再遇到缺失，先报告，不要在交付物里补替身。
- **Playwright 独立 Chromium 在本机可能崩溃。** `chromium.launch()` 打开 OMRS 页面可能返回 `TargetClosedError: Page crashed`，而 Hermes Browser Use 的 Chrome/CDP 可正常访问；不要仅凭此判为 OMRS 服务故障。若环境变量 `OMRS_TEST_CDP_URL=http://127.0.0.1:9222` 指向受信任的本机 CDP，测试可复用共享 Chrome，但每项测试必须只关闭自己创建的 BrowserContext，不能调用 `Browser.close()` 关闭共享实例。CDP 只绑定本机可信端点，不要暴露公网；独立 Chromium 崩溃原因未确认。
- **测试实例会重启生产服务。** `/api/restart` 只要在进程环境里看到 `OMRS_SYSTEMD_SERVICE`，就执行 `systemctl restart <该服务>`（见 `omrs/server.py`）。完整模式下启动任何测试实例之前，都先 `unset OMRS_SYSTEMD_SERVICE`；设置页相关的 E2E 用 `page.route` 拦截 `/api/restart`。
- **Playwright 的 `text=` 是子串匹配。** 它会点中含同样字样的说明文字。按钮一律用 `get_by_role("button", name=..., exact=True)`。
- **刷新后立即操作会失败。** 普通应用页可用 `tests/browser_runtime.py::open_app` 明确设置入口参数并等待 `window.__omrs`、当前路由与活动面板就绪；入口与 PIN 专项直接访问 `/`，否则点击发生在脚本加载之前。
- **草稿详情容器不表示数据载入完成。** `.drf-detail` 也用于加载占位；运行记录跳转草稿的 E2E 等待详情内入库按钮出现后，再断言科目、来源和正文，不依赖页面入场动画留出的时间。
- **截图时机。** 主面板不播放入场动画，仍须等目标数据与字体就绪再截图；开关、菜单和弹窗的局部过渡按组件契约等待，不能用固定延迟代替页面就绪判断。
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

当前仓库的独立检测服务位于 `services/boxdetect/`，从该目录执行 `python -m boxdetect_service serve` 或 probe；支持安装后从仓库外运行。三项推理依赖与安装包验收见 `services/boxdetect/README.md`，旧工具入口仍可用。源码迁移不修改下文所记生产 unit 与模型入口。

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

## 标记整理批次

启动和扫描前检查标记整理 journal；只读盘点拒绝待恢复状态。隔离回归使用临时 Vault，不连接真实题库。

## 整批标记归类

新增 `tests/e2e/label_plans.py`：三百合成题、假模型与真实 MCP SDK 走分片准备、同页修订、跨科目选择、一次批准、结果和整批撤销。浅深主题与桌面/390px 布局截图在临时目录；真实进程故障覆盖见 `tests/test_label_plan_recovery.py`。

标记整理回归包含真实进程故障、三百题双入口与真实 SDK、原位审批和撤销；由 `tests/e2e/label_plans.py` 自动加入全门禁。E2E 直接导入应用模块时，从主模块脚本地址解析相对路径，沿用页面内容版本；禁止导入未版本化路径形成另一份未连接的领域单例。界面集成的 CSS 层断言读取 `CSSLayerBlockRule.name`；历史首屏按六十条分页校验，MCP 权限回归含默认关闭的两个标记权限。
