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

生产环境事实（2026-09-29 实测）：服务 `omrs.service`，监听 TCP 8471，`Type=simple`、`Restart=on-failure`、`RestartSec=3s`；systemd drop-in 从 `/root/workspace/releases/omrs-25f3c3f` 运行 v1.33.1，真实 Vault 仍是 `/root/workspace/apps/OMRS`。备份目录 `/root/workspace/backups/recycle/`；当前发布的一致性备份为 `assistant-jpeg-25f3c3f-20260929T070258Z`，旧发布目录 `omrs-f803f2d` 保留用于代码回退。远端经 Nginx 反向代理。默认分工和规划模式见 `AGENTS.md`「维护者、分工与运行模式」。

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

```bash
python3 tests/fixtures/make_vault.py --out /tmp/fx/full
python3 tests/fixtures/make_vault.py --out /tmp/fx/empty --profile empty
```

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

AI 助手没有网络也能完整测试：启动服务前设环境变量 `OMRS_AGENT_FAUX_SCRIPT=tests/fixtures/agent_faux.json`，运行时改用脚本化假模型（按最近一条用户消息选场景，模板可引用之前的工具结果），再在 `config.json` 里设 `agent_enabled: true`。`tests/e2e/assistant.py` 就是这样起隔离实例的。

## 5. 已知坑

- **缺模块。** 旧版导出只含 Git 已跟踪文件，未提交的模块会缺失，导致包无法 import。现行导出按目录收集并包含未提交源码；若再遇到缺失，先报告，不要在交付物里补替身。
- **Playwright 独立 Chromium 在本机可能崩溃。** `chromium.launch()` 打开 OMRS 页面可能返回 `TargetClosedError: Page crashed`，而 Hermes Browser Use 的 Chrome/CDP 可正常访问；不要仅凭此判为 OMRS 服务故障。若环境变量 `OMRS_TEST_CDP_URL=http://127.0.0.1:9222` 指向受信任的本机 CDP，测试可复用共享 Chrome，但每项测试必须只关闭自己创建的 BrowserContext，不能调用 `Browser.close()` 关闭共享实例。CDP 只绑定本机可信端点，不要暴露公网；独立 Chromium 崩溃原因未确认。
- **测试实例会重启生产服务。** `/api/restart` 只要在进程环境里看到 `OMRS_SYSTEMD_SERVICE`，就执行 `systemctl restart <该服务>`（见 `omrs/server.py`）。完整模式下启动任何测试实例之前，都先 `unset OMRS_SYSTEMD_SERVICE`；设置页相关的 E2E 用 `page.route` 拦截 `/api/restart`。
- **Playwright 的 `text=` 是子串匹配。** 它会点中含同样字样的说明文字。按钮一律用 `get_by_role("button", name=..., exact=True)`。
- **刷新后立即操作会失败。** 页面刷新后要等 `typeof switchTab === 'function' && document.readyState === 'complete'` 成立才能操作，否则点击发生在脚本加载之前。
- **截图时机。** 面板淡入 0.3s、开关过渡 0.15s，切换后至少等 0.9s 再截图，否则画面发灰或开关状态看起来不对。
- **HTTP 风险提示。** 远端 HTTP 登录会弹一次 `alert`，需要注册 `page.on("dialog", ...)` 自动确认。
- **中文输出。** `cut -c` 按字节截断会切坏中文，导致整条输出被拒收。要截断时用 Python 按字符处理。
- **`pkill -f` 会杀掉自己。** 模式串出现在本条命令里时，`pkill -f` 会连同执行它的 shell 一起结束，工具调用返回 -1。按端口查进程时写成 `pgrep -f "[s]erve -p 18471"`，或在启动时记下 PID。
- **不要运行 `--write-log-index`。** `AI/logs/` 在包内只有本次新建的日志，生成出来的索引不完整；交给完整模式运行。

## 6. 完整模式接手配方

**合入 CCW 交付。**

1. `git status --short` 记录现状。
2. 按任务日志「合入」一节运行 `git apply --3way <补丁>`（2026-09-26 之前的交付，按它自带的 UPGRADE 文档）。
3. 跑门禁：`unittest`、`node --test tests/app/*.test.mjs tests/app/*.test.mjs`、`python3 tests/check_docs.py --diff HEAD`、`python3 tests/check_ui.py`、`python3 tests/check_contrast.py`。
4. 运行 `python3 tests/check_docs.py --write-log-index`，审阅 `AI/logs/log.md` 的 diff 后提交。
5. 「合入」一节列出的生产验收，须用户授权后再做，结果补进对应的任务日志。

**按执行说明开发。** 执行说明在 `AI/plans/<计划>/exec-*.md`，规则见 `AGENTS.md`「按执行说明执行」。

- 生产服务如果运行在本机工作区里，开发一律放到 `git worktree` 里做，生产目录只在授权部署时才改动。
- 浏览器测试在本机崩溃时，按第 5 节设置 `OMRS_TEST_CDP_URL`。

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

`omrs-boxdetect.service`与主服务分开，开机自启、失败3秒后重启，使用训练venv的onnxruntime执行固定发布目录的serve.py；只监听127.0.0.1:18766。受管模型入口为/root/omrs-train/managed/active；当前指向旧640副本，SHA前缀894cb458，640输入、置信度.55。服务启动加载一次，不热加载训练current。完整SHA见模型元数据及训练记录。

资源限制：ORT内部3线程、systemd CPUQuota=200%、MemoryHigh=512M、MemoryMax=1G、Nice=10，启动内存约60MiB。`systemctl status omrs-boxdetect.service`查状态，`journalctl -u omrs-boxdetect.service`查错误；`systemctl start/stop/restart omrs-boxdetect.service`会影响线上框选，仅在获得授权后操作。主应用配置local_http及http://127.0.0.1:18766/detect，浏览器不直接访问检测端口，不需Nginx增加路由。

代码回退使用备份的主服务drop-in与检测unit，daemon-reload后重启，恢复原固定模型入口；当前提供方/URL未改变，无需回写配置。备份只供专项恢复，不用旧Vault覆盖上线后新增题目。该检测模型由用户明确选用，内容回归9/15的未达标事实保留，人工校正仍可用。

## 受管检测服务安装与验证

安装登记、初始化映射及unit调整步骤见tools/boxdetect/README.md；未登记实例不提供控制能力。候选预检使用systemd-run独立临时单元，MemoryMax=768M、RuntimeMaxSec=30、CPUQuota=200%；结束后清理临时单元，主程序不导入训练框架。要求有效可用内存至少2GiB，并与training.lock互斥。

隔离门禁：`env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_traincontrol -q`；`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/traincontrol.py`。浏览器脚本只注入测试后端，不操作生产unit。正式服务仍限1GiB，登记精确绑定真实Vault，避免隔离实例继承环境误操作。

主服务已通过OMRS_BOXDETECT_CONTROL=/etc/omrs-boxdetect-control.json登记固定unit、Vault与端口；/train可以管理服务、显式应用完整导出候选并回退。2026-09-29初始化revision为0，旧640在线；主服务与检测服务均开机自启。

框选流程视觉对比使用 `python3 tests/visual/run.py --ref <基线> --pages create --create-stage process`，会在临时 fixture 中放入一张合成题图与题目／答案两个待提取框，基线和当前使用完全相同的数据；提取结果态由录入 E2E 的四档截图及审计覆盖。
