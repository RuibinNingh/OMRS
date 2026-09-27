# 2026-09-27 前端重构：P6 在制（Codex）与 P7（CCW）合并，v1.26.5

## 背景

- 用户原话：「合并两个分支 我让Codex做的P6,没做完,但是CCW P7做完了 所以请你帮我合并这两个代码」；随后「执行」「继续」。记为 progress §1 的 U18。
- 所属计划：`AI/plans/frontend-rearch/`。按 U18，合并改在对话里完成，取代 P7 日志「合入」一节由 Codex 自行 `git apply --3way`、按轮拆提交的做法；Codex 只把合并补丁作为一个提交落地，并补做需要本机环境的步骤（见文末「落地」）。
- 执行者与环境：Claude（claude.ai 对话沙箱）。Python 3.12.3、Node 22.22.2、git 2.43.0、Playwright Chromium 141（独立启动，无 CDP）；无网络；没有本机 worktree，也没有 `AI/logs/` 里的其它日志与 `AI/logs/log.md`（导出包不带日志）。
- 输入：
  - P6 一侧：导出包 `OMRS-source-sanitized-v1_25_13-p6wip-20260927T125544Z`，是 Codex worktree 在 12:55:44Z 的快照：已提交到 v1.25.13，另有未提交的框选工作区在制代码（`features/create/process*.js`、`legacy-inbox.js`、`tests/app/create-process.test.mjs` 及 `inbox.js`、`create.py`、`styles.css`、`omrs_dashboard.html` 的相应改动）。
  - P7 一侧：`OMRS-2026-09-27-p7r6.zip`（v1.26.5 完整包）、累计补丁 `changes-2026-09-27-p7-r1-r6.patch`（相对导出包 `20260927T013727Z`，v1.25.4）、第 6 轮增量 `changes-2026-09-27-p7r6.patch`。
- 共同祖先：在 P7 完整包上反向应用累计补丁（`git apply -R --check` 通过），得到 470 个文件，与导出包 `20260927T013727Z` 自带清单逐项一致。以它为 base、P6 导出包与 P7 完整包为两侧，用 `git merge` 做三方合并（开启改名检测）。

## 行为变化

两条线的用户可见变化都保留，合并本身不引入新行为：P6 的历史、目录、报告、设置、录入页（外壳、上传、快速录入、收件箱网格、在制的框选工作区）与手机上传页，P7 的展示板整页原生与选板浮层，同时生效。侧栏版本号为 v1.26.5。

## 盘点

- 相对祖先，P6 新增 56、删除 7、修改 45 个文件；P7 新增 30、删除 4、修改 33、改名 4 个（即累计补丁的 71 个）。两边都改的 21 个文件里，git 自动合并 7 个（`AGENTS.md`、`AI/environment.md`、`AI/frontend/components.md`、`AI/frontend/library.md`、`AI/frontend/records.md`、`AI/optimization.md`、`assets/styles.css`），14 个文本冲突。
- 语义冲突（git 查不出）1 处：P6 新写的 `assets/app/features/create/quick.js` 仍 `import { boardQuickAdd } from '../../domain/board.js'`，这个文件 P7 第 1 轮已改为 `domain/board/index.js`。ES 模块只要一个 import 失败，整个 `main.js` 模块图都不执行，整站只剩旧脚本。
- 交叉引用核对：P6 从 `history.js`、`catalog.js`、`reports.js`、`app.js`（设置段）、`inbox.js`、`labels.js`、`schedule.js`、`core.js` 删掉的 159 个顶层名字，P7 改过的文件一个都没有引用（登记表 `legacy-pages.js` 除外，见下）。反过来，P6 仍在用的旧展示板全局只有 `boardInit` / `boardReloadData`（`app.js`、`labels.js`）与 `boardQuickAdd`（`inbox.js`），都由 P7 的 `installBoardBridge` 挂回。

## 处理

- 版本号四处与 `AI/changelog.md`：按 progress §9（U16 一行）的规则，工作区 v1.25.13 低于补丁版本，取 v1.26.5，不另加 0.0.1；此后各页从 v1.26.6 起。`README.md` 末尾「版本」一节 P7 一侧还停在 v1.24.2，一并改为 v1.26.5。changelog 按版本倒序排两条线（v1.26.5–v1.26.0 在前，v1.25.13–v1.25.5 在后），v1.26.5 段首加一条合并说明。
- `assets/app/main.js`：两边的页面契约都登记（P6 的 history、catalog、reports、settings、create，P7 的 board）。
- `assets/app/legacy-pages.js`：P6 删完五页后只剩 board，P7 删掉 board，登记表为空；文件留到 P8 连同 `main.js` 的 `...LEGACY_PAGES` 一起删。
- `assets/app/styles/index.css`：两边的 `@import` 都保留（domain 层加 `domain/board/picker.css`；features 层在 `schedule.css` 之后依次是 `board.css` 与 P6 的六个样式表）。
- `omrs_dashboard.html`：`<script>` 同时去掉 `board.js`、`board_picker.js`、`board_preview.js`（P7 已删）与 `history.js`、`catalog.js`、`reports.js`（P6 已删）；`inbox.js`、`app.js` 用 P6 一侧的缓存参数；`main.js` 与 `index.css` 内容与两侧都不同，缓存参数改为 `20260927-p6p7-merge`。
- `assets/app/legacy-bridge.js`：唯一冲突是 `uiDialog` 调用方注释，写成现存的 `labels.js`、`questions.js`。
- `assets/app/features/create/quick.js`：import 改为 `../../domain/board/index.js`，与 P7 改 `features/data/index.js`、`features/questions/index.js` 的写法相同，函数签名一致。
- `assets/styles.css`（自动合并）：逐行核对，合并结果相对 P6 的增删与 P7 相对祖先的增删完全相同，反之亦然；P7 删的展示板规则与 P6 删的旧规则没有重叠或遗漏。
- `tests/ui_baseline.json`：先按两侧逐项取小写入，`check_ui.py` 0 处问题后用 `--update-baseline` 重算为实测值（只降不升）。与 P6 一侧的基线相比，`inbox.js`、`styles.css`、`omrs_dashboard.html` 的下降来自框选在制代码与 P7 删的展示板规则。
- 文档：`AI/README.md`、`AI/frontend/architecture.md`、`design-system.md`、`shell.md` 的冲突处写成合并后的实际状态（页面清单、`<script>` 顺序、domain 层、过渡桥表）；`architecture.md` §8 待办同步两条线的完成情况。`progress.md` 状态块写两条线的位置，§3、§4 换成合并后的实测，§1 加 U18，§2 加本次合并一行，§5b 登记框选在制，§8 更新剩余 document 级 keydown（只剩 `app.js`），§9 记本次变更。

## 影响文件

相对 P6 导出包：P7 的全部改动（新增 `assets/app/features/board/`、`assets/app/domain/board/`、`tests/app/board*.test.mjs`、`tests/e2e/board*.py` 等，删除 `assets/board.js`、`board_picker.js`、`board_preview.js`、`assets/app/domain/board.js` 与 4 份旧展示板 node 测试），P7 任务日志 `AI/logs/2026-09-27_frontend-rearch-p7.md`，本日志，以及上面「处理」列出的合并修改。完整包里的 `SOURCE_EXPORT_MANIFEST.txt` 按合并结果重新生成；合并补丁不含它（`omrs/source_export.py` 打包时直接写进 ZIP，worktree 里一般没有这个文件）。

## 验证

均在沙箱里对合并结果实跑：

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：160 OK（P6 160，P7 159）。
- `node --test tests/*.js tests/app/*.test.mjs`：318 / 318。合并前祖先 220、P6 在制 246、P7 292；318 = 246 − 61 + 133，与 P7 日志给的核对式一致。
- `tests/app/run_browser.py` 34 / 34。E2E：shell_router 20、ui_bridge 15、instant 23、feedback 31、questions 92、board_picker 31、board 35、dashboard 26、data 21、schedule 45、history 23、catalog 26、reports 24、settings 50、create 42，全部通过。
- `board.py` 第一次全量运行时有 1 项失败（「离开展示板页：待保存的版面改动立即落盘」读到 0.5），紧接着单独重跑 3 次都是 35 / 35；纯 P7 完整包在同一沙箱跑 4 次都是 35 / 35。按偶发处理，本机复核时留意。
- 冒烟：`smoke_schedule_workbench` OK；`smoke_board_lock.py` 退出码 0；`smoke_board_integrity`、`smoke_board_print`、`smoke_board_print_geometry` 共 15 项，1 项失败：`smoke_board_print` 的 `test_full_then_incremental_print`（仅补印新增的第一页不是占位页），祖先导出包在同一沙箱里同样失败、报错相同，与合并无关（P7 日志已记）。
- 门禁：`check_ui.py` 0 处问题（存量 handlers 13、html_assign 21、inline_style 39、color_literals 44、font_size_literals 96）；`check_contrast.py` 58 组 0 不达标；`check_docs.py --diff`（相对 P6 导出包）结果见 progress §4。
- `git diff --check` 无空白错误；全树没有残留的冲突标记。

## 落地（Codex · 完整）

1. 在 worktree 里 `git status --short`，确认工作区与导出包 `20260927T125544Z` 时一致（框选在制改动还在、之后没有新改动）；有新改动就先提交或另存补丁，否则第 2 步会冲突。`unset OMRS_SYSTEMD_SERVICE`。
2. `git apply --check changes-2026-09-27-p6wip-p7-merge.patch`，通过后 `git apply`。补丁是相对 P6 导出包的 `git diff --binary`，含新增、删除与改名，不含 `SOURCE_EXPORT_MANIFEST.txt`；应用后除这份清单外与合并完整包逐文件一致。若 worktree 里已经放过 P7 日志 `AI/logs/2026-09-27_frontend-rearch-p7.md`，先确认内容相同后删掉再应用（或加 `--exclude=` 跳过它）。框选在制代码会一并进入这个提交，若想分开，先把在制改动单独提交再应用。
3. 提交：`frontend-rearch: 合入 P7 r1–r6（v1.26.0–v1.26.5），与 P6 在制合并（v1.26.5）`，哈希填进 progress 状态块。P7 不再按轮拆提交：手里只有累计补丁与第 6 轮增量，第 1–5 轮的做法与验证都在 P7 日志与 changelog 里。
4. `python3 tests/check_docs.py --write-log-index`，让 `AI/logs/log.md` 收录 P7 日志与本日志。
5. 本机跑 `python3 -m unittest tests.smoke_board_print`：通过就在 progress §8 记为沙箱环境差异；仍失败就在 `AI/optimization.md` 记一条 `[ ]`（导出模板范围），§8 指过去。
6. 本机全量 E2E 与 `tests/app/run_browser.py`，计数应与 progress §4 相同；真实浏览器手工走一遍展示板主路径，另在 Firefox 或 WebKit 至少开一次展示板页。
7. 不部署，不重启生产。
