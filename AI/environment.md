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

生产环境事实（2026-10-18 发布）：当前 v2.8.3，源码为 Git 提交 `baae15f0e6bfb90139aedb0b19e8d2e208102a20` 的精确归档 `/root/workspace/apps/releases/omrs-baae15f`，1567个源码文件逐字节一致，发布提交已推送GitHub main。当前工作区是开发源码，不是在线运行目录；生产 Vault 仍为 `/root/workspace/apps/OMRS`，隔离测试不能读取其真实错题数据。

三个服务沿用原 unit/drop-in。持久别名 `/root/workspace/apps/releases/omrs-9b29d49` 指向 omrs-baae15f；主服务、网关、检测的真实 cwd 分别为同一归档根、services/zuoyebang、services/boxdetect。检测使用原训练解释器执行模块 CLI。三个服务均 active/running、NRestarts为0；网关私有数据在 `/var/lib/omrs-zuoyebang`，目录0700、文件0600，管理员秘密不输出或提交。

Python依赖沿用 `/root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv`，Python3.13.5、MCP SDK1.28.1、Pillow12.3.0、Playwright1.62.0、Segno1.6.6；浏览器缓存包含对应1234版Chromium。检测使用 `/root/omrs-train/.venv/bin/python`，推理依赖未升级。共享 CDP9222 仅供可信本机隔离 context，验证不关闭共享浏览器；发布 TMPDIR 使用浏览器可访问目录。

Web8471、回环MCP18472、HTTPS8472及公开URL `https://home.ruibin-ningh.top:8472` 保持。Nginx的 `/zuoyebang/` 反代至回环8745，不新增公网端口；管理Cookie为Secure/HttpOnly/Strict并限制服务路径。原网关连接、账号／设备、PIN、MCP及调用Key保持，匿名数据、MCP、网关调用与详情仍需鉴权；锁屏入口内联既有SVG图标。

当前停服保全为 `/root/workspace/apps/releases/OMRS-v283-backup-hcou3lvi`，目录0700、文件0600，含新旧源码、unit、Vault/maintenance与网关私有数据。切换前八类活动任务均为0、恢复与写入意图检查通过，持训练锁停服；备份解包校验1250个文件及8个SQLite库后原子切换，切换与主要验收共5.080秒。49张原业务表的全部原列／原行及1081个原正文、图片和关键配置文件保持；长期待审不依据旧期限作废。

作业帮工作台在超过1500 CSS px时并排显示题目与答案，小屏保留切换；确认按钮打开识别工作窗，期间显示居中提示，暂存、刷新和重开保留草稿。候选按360 CSS px宽、17px正文、3倍输出，静态SVG附图经校验生成PNG，旧预览可主动重生成；正文切换预览／源码，已入库源码只读。设置支持筛选、勾选运行／AI日志并下载ZIP。题图无目录FD分支使用独立lstat核对文件身份，兼容Windows目录扫描中的零身份字段；run.bat和依赖保持。生产不执行真实搜题、模型调用或测试入库。

当前发布从精确归档执行10组门禁：Node550项、后端定向60项、浏览器组件35项、入口分档30项、背景5项、外壳路由24项、设置75项均通过；UI零违规，对比度58组通过，146份文档零问题。版本数字的4组前后截图无脚本错误或横溢，桌面浅深差异各0.002%、手机均0。入口支持自动／轻量／完整／静态，按设备信号和运行帧率调整，系统减少动态效果优先。

生产只读验收核对9份版本化资源原字节、immutable与回环304，以及6份公开入口资源原字节、no-cache与回环304；现有公网代理对这6份资源的条件请求均返回完整200，正文仍与归档一致。业务API、main/settings脚本、MCP与网关匿名访问均401。独立Chromium完成1440／390px自动、静态及390px减少动态共5场景：自动选轻量，静态不请求场景，PIN可输入，无脚本错误或横溢；零写请求。验收后原业务表、文件、网关凭据与控制配置保持，三服务无错误级日志；实体设备功耗与登录后真实业务未验收。

上线后的正常入库继续追加业务事实，核验时以保全中的原记录为比较前缀，不将题目总数固定为发布时的值。模型指针、revision与控制文件保持；源码回退保留最新数据，不用旧归档覆盖后续业务事实。

生产部署使用 Git 精确归档，沿用当前依赖，不打包未提交的开发改动。功能验证使用临时 Vault 和随机端口；发布前按改动范围从归档执行相关检查。实际切换前检查运行任务与恢复意图，持训练锁停服保全并校验归档，再原子切换源码别名。上线后至少核对三服务真实目录、版本、资源及就绪；完整验收另核对鉴权、原数据库全部业务列及原正文／配置哈希，快速发布按用户指定范围执行。回退保留最新数据。

启动按稳定身份导入只读审核历史并收束旧进程，不能重放业务。发布预检核对有效未终结任务、恢复意图、训练锁及受管操作；已结束的运行记录须结合关联审批的真实状态判断，MCP 与已送审助手提案、待审草稿长期保留，不能因旧期限或调用线程结束而废止。数据库迁移后仍投影全部原列逐表比较；新增列和生命周期变化单独核对，不忽略审批库差异。存在未完成题目／整批标记写入或恢复意图时停止；回退只恢复源码别名和必要的 unit，保留最新 Vault、受管历史、revision及锁。

A4固定字体与打印门禁为 `python3 -m unittest tests.test_export_fonts tests.smoke_a4_print -q`；统一门禁包含 `print-a4`，下载路径另由 `tests/e2e/schedule.py` 验证。刷新不闪动的隔离门禁为 `python3 tests/e2e/ai_review_refresh.py`。并排录入用 `python3 tests/e2e/ai_review_entry.py`，覆盖缩略图切换、实时框选、暂存／刷新与真实入库；其后台作业回归应逐个运行浏览器脚本，避免其它上下文抢占前台使 document.hidden 暂停轮询。所有测试实例须清除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`，Windows Edge与实体手机须另验。

审核中心长期待审用 `python3 tests/e2e/ai_review.py` 验证：临时 Vault 在实际服务启动前预置一个月前带旧期限的 MCP 提案，浏览器核对队列、详情无有效期、人工修订与批准；服务启动不能按旧期限结束该请求。时钟前移一年的领域回归使用进程内替换时间，不等待真实期限，也不读取生产题库。

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

**模拟网络下的工作台加载实测。** `python3 tests/bench_web_load.py --out /tmp/omrs-web-load.json` 自建演示 Vault、随机端口和浏览器上下文，默认模拟 100ms 延迟、5Mbps 下载，每次分别测冷启动和真实刷新。可用 `--tree <基线源码目录>` 比较同一命令下的版本，`--runs` 调整次数；`OMRS_TEST_CDP_URL` 沿用受信任本机 CDP 配方。结果包含仪表盘数据就绪时间、CSS / JS 请求数、传输字节、缓存与脚本错误，不接生产端口或真实数据，不把偶发时间波动作为功能门禁。

**入口分档实测。** `python3 tests/bench_entry_load.py --ref HEAD --runs 3 --seconds 10 --out /tmp/omrs-entry-bench.json` 从Git归档基线和当前树分别启动临时PIN Vault、随机端口，直接访问真实锁屏。默认100ms延迟、5Mbps，桌面1440×900／DPR1、手机390×844／DPR3、大屏2560×1440／DPR2；可用 `--scenarios desktop,mobile`、`--profiles auto,light,static,full`、`--cpu-rate 4` 调整。复用浏览器进程、每次新建冷HTTP缓存上下文，不清空进程级着色器与系统缓存。结果含首屏绘制、PIN可用、背景就绪、输入往返／事件排队、绘制FPS、浏览器进程CPU时间、渲染像素、贴图像素、JS堆和传输字节；CPU100%表示一个逻辑核，不是整机百分比，JS堆不含GPU显存。软件WebGL与CPU节流不能当实体设备功耗验证。

`python3 tests/e2e/entry_quality.py` 是入口强度功能门禁：真实WebGL、PIN登录、设置回读、异步取消与资源释放；低核／省流量、持续低帧率、标签页隐藏和闲置时钟分别模拟。视频使用内嵌合成VP9样本，不依赖ffmpeg；静态视频／GIF必须无媒体请求。`OMRS_ENTRY_SHOTS` 指定截图目录。普通图片／背景配置仍由 `tests/e2e/entry_background.py` 验证，组件和工作台的门禁不代替入口测量。

CPU节流结果需要空白页对照：当前Linux Chromium在4倍CDP节流下，空白页也产生约77%的单核CPU计量，而不节流约0.8%；节流档CPU不能直接当页面自身开销。节流不等同低端GPU，正式CPU对比优先使用未节流的重复样本，并同时保留渲染器名称和单次原始数据。

**前后截图对比。** `tests/visual/run.py` 用 `git worktree` 检出基线，与当前工作区各起一个实例、各喂同一份 fixture 副本，按 12 页 × 浅/深 × 桌面 1440 / 手机 390 截图并做像素差分。产物是 `report.html`、`audit.json`（每页字号种数、最小字号、小于 28px 的可点目标、行内样式数、横向溢出），仓库里不存金标图。审计只计非空 `style` 属性，字号和行内样式均排除 KaTeX 内部。页面内冻结 `Date`、注入样式关闭动效；`--pages ai-review --review-kind draft` 对比真实草稿并排工作区，默认审核类型仍为 operation；服务端实时内容在脚本的 `MASKS` 里登记后截图时遮住。约 1–2 分钟，放后台轮询：

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

作业帮隔离门禁包括 `tests/test_zuoyebang.py`、`tests/test_zuoyebang_render.py`、`tests/test_zuoyebang_geometry.py` 与服务测试。使用安装了requirements-zuoyebang.txt的解释器，另安装Playwright Chromium；本机通用python可能缺少Segno，需选现有完整依赖环境。网关测试在services/zuoyebang运行 `python -m unittest discover -s tests -t . -q`，不能省略包根-t。

`tests/e2e/zuoyebang.py`自建临时Vault、随机端口，清除生产控制环境，只替换作业帮／AI网络边界；真实执行HTTP、上传、Chromium、图片及合成题目创建。`zuoyebang_paper.py`是其题框专项：原图字节、分组、选框、移动／缩放、刷新、缓存离页、裁图入库及重复回执。摄像头使用fake-device的真实MediaStream，不能替代实体手机验收；专项应使用独立Chromium，不沿用缺少模拟媒体参数的共享CDP。

`OMRS_ZYB_SHOTS`指定截图与checks.json目录，包含1080长答案、八档320/390/1024/1440px浅深主题、裁图入库页及合成Markdown。视觉比较用 `python3 tests/visual/run.py --ref <基线> --pages create --create-stage zuoyebang`，脚本对旧源码进入原工作区，对新源码进入独立路由；普通录入页另用 `--pages create` 比较。页面缺少有效题框时保留候选，不用生成的框代替真实接口证据。

作业帮E2E内的zuoyebang_mobile.py只在该次临时Vault移除合成记录的layout字段以模拟旧预览，核对主动升级、在途刷新与编辑保留，并比较旧record.json和PNG原字节；产物含legacy-mobile-entry-320/390及mobile-preview截图。手机题图仍输出1080物理像素，CSS排版宽度为360、DPR为3。

两进程验收用 `tests/e2e/zuoyebang_gateway_integration.py --with-prefix --out <临时目录>`，验证实际网关签名／坐标解码、反代前缀和原图传输；`tests/e2e/zuoyebang_service.py`验证服务切换与失败后的观察归属。均使用临时私有数据，无真实官方搜题和付费模型调用。

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

当前仓库的独立检测服务位于 `services/boxdetect/`，从该目录执行 `python -m boxdetect_service serve` 或 probe；支持安装后从仓库外运行。三项推理依赖与安装包验收见 `services/boxdetect/README.md`，旧工具入口仍可用。生产从同仓服务目录启动，模型入口仍为原 managed/active。

控制器的候选预检使用登记解释器、服务目录 WorkingDirectory 与新 probe CLI；内存保护由 `omrs/system_resources.py` 提供，训练脚本复用同一函数。部署模板为 `deploy/boxdetect.service`，示例路径须替换为实际同仓发布归档／登记解释器／训练根，生产迁移只调整源码入口和 cwd，保留 managed/active 与资源限额。

CPU 训练使用仓库外 `~/omrs-train/.venv/`，精确依赖在 `tools/boxdetect/requirements-train.txt`，服务依赖另列 `requirements-serve.txt`。数据只读原 Vault，产物写外部目录。训练以 nice 19 限制优先级，线程数最多 6，并监控可用内存；可用内存不足 2 GiB 时停止训练。数据构建与系统 Python 单测不加载 torch／onnxruntime。

训练面板文件与 HTTP 门禁：`python3 -m unittest tests.test_trainpanel -q`，使用临时 Vault、假训练目录与随机本机高端口；路由提取已登记 `_trainpanel_get` / `_trainpanel_post`。

## 草稿工作树验证

AI 草稿的开发与浏览器测试使用独立 Git 工作树，服务仍从临时 Vault 与随机高端口启动。`tests/check_docs.py` 的路由发现清单包含 `_drafts_get` 与 `_drafts_post`，新增草稿路由后由 `--write-routes` 更新总表。文档索引必须在完整模式按实际日志文件生成。


训练面板浏览器验证：`python3 tests/e2e/trainpanel.py` 用临时 Vault、假实验与假检测服务，覆盖进度／曲线刷新、人工复核、训练与服务分工及四档状态审计。真实模型链路：`python3 tests/e2e/boxdetect.py --dataset /path/to/frozen-dataset --train-dir /path/to/frozen-training-copy --shots /tmp/omrs-box-detect-real`，从外部数据快照取测试图，临时启动回环检测服务与隔离 OMRS，不写真实 Vault。截图不进 Git。

视觉比较可加 `--create-stage train` 切到录入页 AI 训练工作区，例如 `python3 tests/visual/run.py --ref e40e6b8 --pages create --create-stage train --out /tmp/omrs-box-detect-visual`；不传该选项时保持默认工作区。运行测试前仍须去掉 OMRS_SYSTEMD_SERVICE。

设置页视觉比较可用 `--pages settings --settings-section ai` 定位 AI 识别分区，基线与当前工作区都会先切换到该分区再截图；不传时仍按上次保存的设置分区显示。

内容评测门禁 `python3 -m unittest tests.test_trainaudit -q` 使用假响应与临时目录，覆盖请求预算、429重试、缓存恢复、原判不可变和HTTP复核冲突，不消耗付费额度。训练看护同时读取宿主机和cgroup v2当前层/祖先内存剩余额度；读取失败拒绝启动，workers固定0。测试产物与真实评测均在仓库外。

视觉工具支持 `--pages trainpanel`，基线与当前都直接打开独立 `/train`，与主站路由区分。评测详情由面板E2E另行以假记录覆盖桌面/手机与浅深主题。

## 本机检测生产服务

`omrs-boxdetect.service` 与主服务分开，开机自启、失败 3 秒后重启，使用训练 venv 的 onnxruntime，在同仓发布别名的 services/boxdetect 执行 `-m boxdetect_service serve`；只监听 127.0.0.1:18766。受管模型入口为 `/root/omrs-train/managed/active`；当前实际在线 `v2-20260929-b`，SHA-256 为 `f62581b7c28353d5d7799973018a6986e706cd7dcf4fb43ccd10972be4a4c7c3`，输入 640、置信度 0.1，独立内容验收状态为 missing。服务启动加载一次，不热加载训练目录的 current；主服务本次发布没有切换此模型。

资源限制：ORT内部3线程、systemd CPUQuota=200%、MemoryHigh=512M、MemoryMax=1G、Nice=10，启动内存约60MiB。`systemctl status omrs-boxdetect.service`查状态，`journalctl -u omrs-boxdetect.service`查错误；`systemctl start/stop/restart omrs-boxdetect.service`会影响线上框选，仅在获得授权后操作。主应用配置local_http及http://127.0.0.1:18766/detect，浏览器不直接访问检测端口，不需Nginx增加路由。

三服务代码回退恢复本次源码别名及检测 unit，执行 daemon-reload 后按原服务状态启动；受管模型指针独立保持，不随代码回退切换。当前提供方与 URL 未改变，无需回写配置。真实 Vault 备份只供专项恢复，不用旧归档覆盖上线后新增题目；候选的内容验收状态仍须在服务操作历史中核对。

## 受管检测服务安装与验证

安装登记、初始化映射及unit调整步骤见tools/boxdetect/README.md；未登记实例不提供控制能力。候选预检使用systemd-run独立临时单元，MemoryMax=768M、RuntimeMaxSec=30、CPUQuota=200%；结束后清理临时单元，主程序不导入训练框架。要求有效可用内存至少2GiB，并与training.lock互斥。

隔离门禁：`env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_traincontrol -q`；`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/traincontrol.py`。浏览器脚本只注入测试后端，不操作生产unit。正式服务仍限1GiB，登记精确绑定真实Vault，避免隔离实例继承环境误操作。

部署登记使用 `OMRS_BOXDETECT_CONTROL=/etc/omrs-boxdetect-control.json`精确绑定固定unit、Vault与端口；源码中的当前`/train`只提供实验和内容复核，设置保留固定进程启停，新版独立面板拥有模型状态。新版连接启用后旧控制停用；实际生产切换须另行授权，不能把工作区源码行为视为已部署状态。

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

## 公式定界符隔离验证

公式定界符回归使用 `tests/fixtures/math_delimiters.json` 的合成答案与边界案例，前后端共用。`env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/e2e/math_delimiters.py` 自建临时 Vault 与随机 Web/MCP 端口，实际走官方 SDK、审核入库、题库旧正文兼容及三种离线导出；浅深色桌面 / 手机截图与 HTML、checks.json 保存在唯一临时目录，不接生产或真实模型。

## 门禁入口与隔离

tests/run_gates.py显式包含services组（两服务单测和网关浏览器），E2E跳过纸面辅助模块，网关联调分别传独立--out并执行直连／前缀。退出0但打印SKIP或有跳过用例时状态为skipped，整组不能计通过；空筛选直接退出2，不生成成功报告。摄像头专项单独启动Chromium，不继承共享CDP地址，其余子进程保留浏览器配置。安装包真实推理和冻结检测材料仍需显式提供；--dataset必须同时传--train-dir，检测入口也拒绝默认训练目录。

合成Vault夹具及视觉每一侧显式设置空train_dir并清空既有检测地址；录入策略测试只指向自身随机端口，不能探测8600等固定服务。草稿／录入／审核截图使用独立目录或OMRS_E2E_SHOTS；统一门禁为每项设置独立产物目录。门禁递归扫描AI分册及服务／工具文档，file::symbol引用先检查真实文件。

## AI 框选服务面板隔离验证

同端口接入、迁移和门禁见 `AI/boxdetect.md`；测试用临时数据，去掉生产控制环境变量。
