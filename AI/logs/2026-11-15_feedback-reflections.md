# 2026-11-15 反馈录入页显示统一错因

> **任务**
> - 标识：feedback-reflections
> - 状态：已交付

## 背景

用户原话：「反馈录入页面没有错因显示的地方啊」。执行者 Codex，完整模式，本地修复与隔离验证。任务属于问题中心 U5 的反馈页补充，基线为 d4c0ecde1f36d8a4bc5b330b565c888e02513730（开工工作区干净）。题目备注已经排除错因，而反馈页没有挂载独立错因区，导致该页无法阅读已有错因。

## 行为变化

判定栏接入共享错因区，默认显示历史，可切到「记录本次」补记；旧文本与日期化历史仍读取统一 Markdown。已录入作答的题保留错因入口。作答备注明确为页码或作答情况；错因独立保存。按稳定身份切换，保护未保存草稿，同题弹窗与反馈页的页签 ID 分离。

## 影响文件

- `assets/app/features/feedback/`：模板挂载点、样式、共享控制器生命周期与换题／离页守卫。
- `assets/app/domain/question/`：公开共享错因控制器，支持不同宿主页签前缀。
- `tests/e2e/feedback_reflections.py`：真实临时 Vault、Session、保存失败、学习状态、换题、提交及双主题窄屏回归。
- `AI/frontend/feedback.md`、`AI/frontend/qview.md`、`AI/frontend/architecture.md`、`README.md`：同步可验证的页面行为与共享模块契约。
- 问题中心计划及进度、本任务日志与自动生成索引：保存需求、实现与实际门禁结果；交付前按实际差异复核。

## 已执行验证

- `python3 tests/check_ui.py`：0 违规；`python3 tests/check_contrast.py`：58 组全部通过。
- `node --test tests/app/*.test.mjs`：首次 593/595，两处控制器测试的替身缺少路由方法；给可选调用补齐方法守卫后，595/595 通过。
- `python3 tests/app/run_browser.py`：35 项全部通过。
- `python3 tests/e2e/feedback.py`：43 项全部通过。
- `python3 tests/e2e/reflection_layout.py`：44 项全部通过，复核 `modal.log` 的实际断言计数。
- `python3 tests/e2e/feedback_reflections.py`：21 项全部通过，涵盖旧文本与日期化历史、Markdown、判定不重建错因区、取消换题、失败保留及重试、错因不提交作答、空状态、同题弹窗ID唯一、离页取消、保存后换题、作答提交和已录题历史。浅深色1440/1024/390/320px共8档真实滚轮可达，无横向溢出或脚本错误。
- `python3 tests/visual/run.py --ref HEAD --pages feedback --out /tmp/omrs-feedback-reflections-visual`：4 组空选择态零差异、无脚本错误。另以证据目录中的 `compare_selected.py` 复用该门禁，在生成一次夹具后创建合成Session与错因，向前后两个隔离副本提供完全相同数据并选中计划；`visual-selected/report.html` 为结果。
- 选中计划四组前后差异逐项核对：浅桌面1.370%、深桌面1.359%，新增右侧错因区并下移统计／提交；浅手机16.569%、深手机16.642%，错因区增加文档高度、后续题面顺延。作答备注的标签与占位同时更明确。四组无小点击目标、行内样式、横向溢出或脚本错误，已查看最终桌面与窄屏像素。
- 新错因回归初轮通过读取、保存失败保留、快捷保存及学习状态检查，滚轮在连续切换视口时有等待超时；改为独立浏览器上下文验证各尺寸。另一次弹窗测试由稳定编号改为实际UID，仍按稳定身份核对结果；离页测试原先等待路由守卫Promise，导致无法继续点击确认框，已中断该轮并改为发起导航后操作守卫，最终完整通过。保留原失败日志，不把中途结果当整项通过。
- 文档门禁初次在新日志落盘前执行，报告缺任务日志；收尾补日志、进度与索引后重跑。架构分册将本次共享错因说明合并到原渲染段落，保持小于40KB。
- 最终 `python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff HEAD` 检查165份文档、0问题，3条现存体积提醒。`git diff --check` 通过，并结合 `git diff --name-status` 与未跟踪文件列表复核全部15个任务路径；没有纳入其它改动。

证据目录：`/root/workspace/artifacts/omrs-feedback-reflections-20261115/`。全部功能测试使用合成数据、随机端口，并清除生产控制环境变量。

## 未执行验证

未跑全量后端单测，业务改动仅为前端挂载与交互；未做实体手机验证、生产部署或Git推送。本轮没有新提交，版本保持v2.11.2；代码、测试与文档留在工作区。
