# 2026-11-17 练习历史统一左旧右新

> **任务**
> - 标识：history-order
> - 状态：已交付

## 背景

用户原话：「帮我修改练习历史显示,不应该左旧右新吗」；确认计划后要求「Please implement the plan.」。执行者为 Codex，完整模式，以 `55afe35` 与开工工作区为基线。这是独立的小范围显示修正，不属于既有计划目录；未更改版本号。

开工时已有多份文档及日志索引的未提交修改，以及 7 份未跟踪文档。本次在既有 `AI/export.md`、`AI/frontend/architecture.md`、根 `README.md` 上只修改相关段落，其余内容保留；日志索引按脚本生成。初始状态、完整差异及本次涉及文件的副本保存在 `/tmp/omrs-history-order-20261117-gcg24cl6/baseline/` 及同级 `baseline.status`、`baseline.diff`。

## 行为变化

- 导出参数面板示意、A4 与屏幕版历史图统一左旧右新，方向标注改为「旧 → 新」。首尾日期左早右晚，单条只显示一个日期。
- 分数、对错、颜色与提示信息随完整记录排列，无障碍说明与柱子顺序一致。示意保留原有每次练习的对错关系，默认示例日期由左 `11/13`／右 `10/02` 改为左 `10/02`／右 `11/13`。
- 服务端仍按原规则选取最近 N 条并输出新到旧数组，前端对副本反转；重复渲染不会改变原始记录。接口、数据格式和浏览器偏好键保持兼容，已导出的离线文件需要重新生成才应用新显示。

## 影响文件

- `assets/app/features/schedule/export-dialog.js`、`omrs/export_templates/history.js`：修正示意和共用离线历史图的方向、日期与完整记录排列。
- `tests/e2e/schedule_export.py`：在已有真实导出链路增加预览、两种 A4 位置、屏幕版、空／单条／16条、跨年、同日、无障碍顺序和原数组保护验证。
- `tests/test_schedule_export_history.py`：用20条合成反馈验证1／8／16及超上限参数始终选最新记录。
- `AI/export.md`、`AI/frontend/review.md`、`AI/frontend/architecture.md`、`README.md`：同步当前显示规则、后端数组兼容与回归覆盖。
- 本任务日志及 `AI/logs/log.md`：记录任务和生成索引。已用 `git diff --name-status` 复核实际路径；开工已有文档改动不算入本任务。

## 已执行验证

证据目录为 `/tmp/omrs-history-order-20261117-gcg24cl6/`。服务均由现有 `start_server` 使用临时 Vault、随机高端口启动，启动环境移除 `OMRS_SYSTEMD_SERVICE` 和 `OMRS_BOXDETECT_CONTROL`；未访问生产端口或真实题库。浏览器任务顺序执行。

- 修改前 `OMRS_EXPORT_SHOTS=<证据目录>/before python3 tests/e2e/schedule_export.py`：22项通过，保留原预览、A4截图、HTML与PDF，输出见 `before.log`。
- 修改后 `OMRS_EXPORT_SHOTS=<证据目录>/after python3 tests/e2e/schedule_export.py`：31项通过，页面脚本错误0；真实打开面板、下载离线HTML、核对物理横坐标与完整记录、生成PDF，并验证320／390／1440px浅深主题布局。输出见 `after.log`。
- `python3 -m unittest tests.test_schedule_export_history tests.test_export_fonts -q`：11项通过，输出见 `backend.log`。
- `python3 -m unittest tests.test_board_export tests.smoke_a4_print tests.smoke_board_print -q`：23项通过，输出见 `print.log`；含A4跨栏、打印媒体和历史图关闭细节的真实Chromium/PDF回归。
- `python3 -m pytest tests/test_report_export.py -q`：7项通过，输出见 `report.log`。
- `node --test tests/app/*.test.mjs`：601项通过、0失败、0跳过，输出见 `node.log`。
- `python3 tests/app/run_browser.py`：35项通过、0失败，输出见 `components.log`。
- `python3 tests/check_ui.py`：全仓5类违规计数均为0；`python3 tests/check_contrast.py`：58组对比度全部通过。输出见 `ui.log` 与 `contrast.log`。
- `python3 tests/visual/run.py --ref HEAD --pages schedule --out <证据目录>/visual`：4组浅深／桌面手机页面对比均无差异，脚本错误0，报告为 `visual/report.html`。调度页基础布局保持；该脚本不打开导出模态，模态和导出本身另由下述截图对比核验。
- `python3 tests/check_docs.py --write-log-index`：生成索引；中间的 `python3 tests/check_docs.py --diff HEAD` 检查均为171个文档、0问题，但本次追加使架构文档超过40KB。随后精简本次涉及的同一段落，保持原有职责与验证信息。
- 最终 `python3 tests/check_docs.py --diff HEAD`：171个文档、0问题、0提醒，退出码0，输出见 `docs-final.log`；架构文档40958字节，满足40KB上限。
- `git diff --check`：通过；按开工差异逐文件对照，17份无关已修改文件的差异完全保留。与开工副本相比的本次差异另存 `task.diff`。

专项截图对比逐项说明：

- `before/` 与 `after/` 的默认浅深面板及1440px面板：历史文案、柱子、分数／对错与首尾日期调整为左旧右新；页面结构、图高与题头位置一致。
- 320／390px面板：示意按既有规则隐藏，预期差异只有「左旧右新」说明；暗色截图另含主题过渡捕获到的表单颜色差异，非样式修改。
- `export-history-detail.png`：同尺寸题头，只有方向文案、柱子／数值／对错及日期位置有差异。
- `export-feedback-page.png`、`export-question-page.png`：相同页尺寸与题面布局，历史区域反向排列；两次独立合成Session的生成编号和时间另有文本差异。
- 原E2E截图在切主题与控件操作后直接截取，默认与1440px整面板另有焦点环、数字框箭头及主题过渡捕获差异；修改未涉及CSS。已人工查看默认浅深预览、原暗色面板和实际A4题头，确认图表从左旧到右新。单独裁出的示意保存在 `before/history-preview.png`、`after/history-preview.png`。

## 未执行验证

未执行全量后端及全部业务页面E2E；本次只改变导出历史的展示顺序，已运行导出模块所列回归、全量Node与强制前端门禁。未在实体手机、Windows／Edge或外部设备打印机验证，未部署、推送或访问生产服务；本次授权为本地实现。
