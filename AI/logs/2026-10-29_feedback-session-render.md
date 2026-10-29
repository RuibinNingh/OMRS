# 2026-10-29 反馈录入同 UID 历史条目导致空白

> **任务**
> - 标识：feedback-session-render
> - 状态：已交付

## 背景

用户原话：「为什么这个不显示内容」，截图显示所选 Session 为 31/40 已录、9 待录，题目区域仍为空。执行者 Codex，完整模式；本次为独立故障修复，不属于进行中的执行计划。基线为 `293f084c8db53d69850dd675d465b83698f2f5e6`。

开工已有 `AI/plans/omrs-maintenance/validation.json` 未提交修改，完整保留，不纳入任务改动。只读 SQLite 诊断使用 `mode=ro` 精确查询截图中的 Session：40 条、31 已录、9 待录；第 7、31 条同 UID，前者已归档。旧视图为两条只读记录生成相同的列表 key，`each()` 抛错，整个视图生成中断，下拉框保留用户选择而题目区停留在此前空状态。诊断没有运行生产接口或向真实 Vault 写入。

## 行为变化

反馈页的可编辑行继续按行下标生成 key；已录只读条目复用领域模块的 `sessionEntryKey()`，优先用固定 `entry_id`，其次 `question_id`，旧计划回退 UID。归档旧题与新题同 UID 时各自保留，待录题正常加载和判定。学习记录、计划内容与持久化格式没有变化。

## 影响文件

- `assets/app/features/feedback/view.js`：只读条目的渲染 key 使用固定身份。
- `tests/app/feedback.test.mjs`：添加 31/40 同 UID 计划、空 UID 和旧计划兼容回归。
- `tests/e2e/feedback.py`：合成同 UID Session 响应，真实浏览器核对列表、题面、只读与判定，并保留四档截图。
- `AI/frontend/feedback.md`、`AI/frontend/architecture.md`、`README.md`：同步渲染身份与用户行为、测试边界。
- 本任务日志与脚本生成的 `AI/logs/log.md`：记录事实及验证。

## 已执行验证

- 修复前 `python3 tests/e2e/feedback.py`：原有主路径 31 通过、0 失败，说明原门禁没有覆盖同 UID 的两条已录记录。
- 修复前 `node --test tests/app/feedback.test.mjs`：24 通过、2 个新增用例失败，均报 `each()` 重复 key。
- 修复前独立调用 `run_reused_uids()`：浅深色桌面／手机均复现空列表及重复 key 脚本错误，0 通过、8 失败；合成 Vault、随机端口、独立 Chromium，已移除生产控制变量。截图及检查在 `/tmp/omrs-feedback-investigation-si1r6jnh/before/`、`/tmp/omrs-feedback-investigation-si1r6jnh/checks-before.json`。
- 修复后 `node --test tests/app/feedback.test.mjs`：26 通过、0 失败；`node --test tests/app/*.test.mjs`：564 通过、0 失败、0 跳过，完整输出在 `/tmp/omrs-feedback-investigation-si1r6jnh/node.log`。
- `python3 tests/check_ui.py`：五类全仓计数均为 0、0 问题；`python3 tests/check_contrast.py`：58 组、0 不达标。
- `python3 tests/app/run_browser.py`：35 通过、0 失败，输出在 `/tmp/omrs-feedback-investigation-si1r6jnh/browser.log`。
- `OMRS_FEEDBACK_SHOTS=/tmp/omrs-feedback-investigation-si1r6jnh/after python3 tests/e2e/feedback.py`：43 通过、0 失败；新增四档合成场景共 12 项检查通过，原有 31 项主路径仍通过，页面脚本错误为 0。输出在 `/tmp/omrs-feedback-investigation-si1r6jnh/feedback-after.log`。
- `python3 tests/visual/run.py --ref 293f084c8db53d69850dd675d465b83698f2f5e6 --pages feedback --out /tmp/omrs-feedback-investigation-si1r6jnh/visual`：退出 0，默认未选 Session 的四组前后对照全部 0% 差异、无脚本错误；报告为该目录的 `report.html`。独立同 UID 场景的浅色桌面、浅色手机、深色桌面、深色手机四组前后截图分别在 `before/` 与 `after/`：修复前均为空态，修复后均显示 31/40 进度、题目列表、第 32 题题面及 9 道待录统计，属于预期行为恢复；未修改版式与样式。
- 浏览器与视觉检查均使用临时合成 Vault、随机高端口、独立 Chromium；显式移除 `OMRS_SYSTEMD_SERVICE`、`OMRS_BOXDETECT_CONTROL`、`OMRS_TEST_CDP_URL`，没有以真实数据运行测试。
- 已用 `git diff --name-status` 和 `git status --short` 复核实际路径，`git diff --check` 退出 0；已运行 `python3 tests/check_docs.py --write-log-index` 生成日志索引。
- `python3 tests/check_docs.py --diff HEAD`：退出 0，155 份文档、0 问题、3 条既有体积提醒。已有 `validation.json` 的 SHA-256 保持 `3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9`，本次未改动该文件。

## 未执行验证

后端全套与其他页面 E2E 未执行：本次生产源码仅调整反馈视图的列表 key，相关前端全套及主路径已验证。生产发布、重启及线上功能验收未执行；没有生产变更授权。未升级版本、提交或推送；下一步如需线上生效，由用户单独授权发布本次修复。
