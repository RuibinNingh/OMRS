# 2026-09-28 独立框选标注页（训练数据采集）

## 背景

用户原话：「OMRS 有个 AI 训练部分，我现在在大量收集训练数据，你需要帮我在 OMRS 新建一个页面，独立于原本的主页，可以上传图片，然后做一个框选方便我标注，不需要记录其他，只需要标记题目和答案的范围，在 AI 训练页点击一个按钮直接跳转到新的链接打开，加一些快捷键辅助我快速标记」；补充：「这个页面是脱离题库存在的，旨在大规模录入」。

运行模式：受限模式（CCW）。判定依据：工作目录不是 Git 仓库，源码来自上传的 `OMRS-source-sanitized-20260928T131039Z.zip`。基线：该导出包原样提交（导出时间 20260928T131039Z）。不属于任何进行中的计划。

## 行为变化

- 新页面 `/annotate`（不经主页外壳）：批量上传截图（选择文件、选择整个文件夹、整页拖入文件或文件夹、`Ctrl + V` 粘贴），上传排队分批进行、可边传边标；每张图只画「题目」「答案」两类框；`Enter` 完成并跳到下一张未完成；导出 YOLO / JSONL（默认只含已完成）。快捷键与交互细节见 `AI/frontend/annotate.md`。
- 录入题目页「AI 训练」工作区新增「框选标注页」一栏：显示标注集进度，「打开标注页」在新标签页打开 `/annotate`。
- 数据存在 `错题/.omrs/annotate/`（`annotate.db` + `images/<sha256>.<ext>`），不写收件箱、Ledger、题目。YOLO 类别号与收件箱数据集相同（0=题目，1=答案）。
- 新增端点：`GET /annotate`、`GET /api/annotate/images|stats|raw|export`、`POST /api/annotate/upload|save|delete`（契约见 `AI/api.md`）。POST 在进程级写锁内处理，未加入豁免清单。
- 导出先写临时文件再分块发送，原图按 ZIP_STORED 存，避免大批量时在内存里拼几 GB 的 zip。
- 大批量渲染：队列按行增量 morph，序号表一次算好。

开发中由真实浏览器发现并修掉的问题：刚画完的框保持选中，导致按 `A` 切换角色时把刚画的题目框改成了答案框。现在 Q / A 只改点选或 Tab 选中的框。

## 影响文件

- 新增后端：`omrs/annotate.py`；`omrs/server.py`（`_annotate_get` / `_annotate_post`、导入 `shutil` / `tempfile`）。
- 新增前端：`assets/app/annotate.html`，`assets/app/features/annotate/` 下 `index.js`、`store.js`、`state.js`、`canvas.js`、`view.js`、`folder.js`、`annotate.css`。
- 改动前端：`assets/app/features/create/train.js`、`train-view.js`、`train.css`（AI 训练页入口栏）。
- 测试：新增 `tests/test_annotate.py`（6 例）、`tests/app/annotate.test.mjs`（11 例）、`tests/e2e/annotate.py`（34 项）；`tests/check_docs.py` 的 `ROUTE_METHODS` 登记 `_annotate_get` / `_annotate_post`。
- 文档：`AGENTS.md`（映射表）、`AI/frontend/annotate.md`（新分册）、`AI/frontend.md`、`AI/frontend/create.md`、`AI/frontend/architecture.md`、`AI/api.md`、`AI/data.md` §16、`AI/security.md`、`AI/environment.md`（门禁清单）、`AI/optimization.md`（备份导出在内存拼 zip 的技术债）、`AI/README.md`、`AI/routes.md`（生成）、根 `README.md`。

## 验证

已实际执行：

- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：217 例 OK（基线 211，新增 6）。
- `node --test tests/app/*.test.mjs`：337 通过 / 0 失败（基线 326，新增 11）。
- `python3 tests/check_ui.py`：0 处问题。`python3 tests/check_contrast.py`：58 组 0 组不达标。
- `python3 tests/app/run_browser.py`：32 通过 / 0 失败。
- `python3 tests/e2e/annotate.py`：34/34 通过（含桌面 / 手机 × 浅 / 深四项审计：字号 ≥12、无小于目标的点击区、无行内样式与事件、无横向溢出）。
- `python3 tests/e2e/create.py`：80/80 通过（AI 训练页加了入口栏后）。
- `python3 tests/visual/run.py --ref <基线>`：0 / 48 有差异，页面脚本错误无。默认页组不含「AI 训练」工作区，该区由 `create.py` 的审计覆盖。
- `python3 tests/check_docs.py --diff <基线>`：0 处问题（2 条存量提醒：`AI/api.md`、`frontend-rearch` 执行说明超过 40KB）。
- 规模实测（一次性脚本，不入库）：3000 张入库后打开 `/annotate`，首屏 1–2 秒，`→` 翻页每次约 17ms（行级 morph 前约 206ms），画框 + Enter 平均约 385ms（含 Playwright 鼠标步进与保存往返）。

未执行：

- 真实作业帮长截图与真实模型训练流程（沙箱无真实数据）。
- 其余 E2E 脚本（未改动对应页面）。
- Safari / Firefox 的文件夹拖入（`webkitGetAsEntry`），只在 Chromium 验证。

## 合入（仅受限模式交付）

- 补丁基线：`OMRS-source-sanitized-20260928T131039Z.zip`。
- 应用：`git apply --3way changes-2026-09-28-annotate-page.patch`。
- 门禁与预期：
  - unittest 共 217 例 OK；
  - node 337 通过；
  - `check_ui` / `check_contrast` / `check_docs --diff HEAD` 均退出 0；
  - `tests/app/run_browser.py` 32 通过；
  - `tests/e2e/annotate.py` 34/34，`tests/e2e/create.py` 80/80。
  - 若工作区在基线之后有新测试，计数按实际增加。
- 完整模式补做：
  1. `python3 tests/check_docs.py --write-log-index`，验收：`AI/logs/log.md` 含本日志且 `check_docs` 通过。
  2. 按版本惯例发版时在 `AI/changelog.md` 顶部登记「框选标注页」（本任务未改版本号，避免与进行中的计划冲突）；改版本号时同步 `omrs/version.py`、侧栏、根 `README.md`、`AI/README.md`。
  3. 重启生产服务后在真机打开「录入题目 → AI 训练 → 打开标注页」。验收：新标签页打开 `/annotate`，拖入一个截图文件夹能排队上传并逐张标注，导出的 YOLO zip 能与收件箱导出合并。
  4. 远端（PIN）访问 `/annotate`。验收：未登录跳 `/login?next=%2Fannotate`，登录后回到标注页。
