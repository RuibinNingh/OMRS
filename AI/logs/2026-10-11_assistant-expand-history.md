# 2026-10-11 助手运行记录一次展开

## 背景

用户原话：「这个东西能不能改一下,一次就完全展开」，截图指向「继续读取运行记录」。Codex · 完整模式，基线 `574aed6`，开工工作区干净。本次独立于已经交付的 Responses 反馈修复，不变更协议、模型配置、存储或版本号；沿用本会话「部署一下生产我测试」的授权，发布结果在本日志补记，不推送远端。

## 行为变化

运行轨迹首屏仍最多读取 200 条事件。入口改为「展开完整运行记录」：点击一次清除该运行的处理过程折叠状态，按每页最多 500 条自动续读到末页，全程显示「正在展开…」并禁止重复点击。读完移除按钮和未完整提示，单个工具卡沿用既有展开偏好。

失败保留已读页和游标，恢复入口，重试继续断点。空续页、不前进或缺失的续页游标会提示错误并停止循环。发起对话切换、替换运行对象或离页时停止续页，迟到的成功和失败响应不进入新对话；活动运行继续由已有长轮询读取。

## 影响文件

- `assets/app/features/assistant/history.js`：单次自动续页、请求身份检查、失败保留与忙碌态收束；通知依赖默认使用已有 toast，供控制器测试记录错误。
- `assets/app/features/assistant/view.js`：完整展开与读取中的按钮文案。
- `tests/app/assistant-history.test.mjs`：自动续页、重复点击、断点重试、切换/卸载、坏游标与活动运行回归。
- `tests/e2e/audit_identity.py`：夹具扩为 1212 条事件，一次点击完成三个后续页，验证完整回答与处理过程恢复展开；双主题和双宽度验收、可选截图输出。
- `AI/frontend/assistant.md`、`AI/frontend/architecture.md`、`README.md`：同步当前行为与门禁；本日志及自动索引记录交付。

## 已实际执行的验证

所有业务测试使用临时 Vault、随机端口，移除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`；未调用生产模型。

| 命令 | 结果 |
|---|---|
| `node --test tests/app/assistant-history.test.mjs` | 13/13，无跳过 |
| `node --test tests/app/*.test.mjs` | 470/470，无跳过 |
| `python3 -m unittest tests.test_agent_pagination -q` | 4/4 |
| `python3 tests/check_ui.py` | 全仓五项计数均为 0，0 问题 |
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 tests/app/run_browser.py` | 34/34，无页面错误 |
| `python3 tests/e2e/audit_identity.py` | 修正增补测试的等待后 24/24；一次点击读完 1212 事件，浅/深色 × 1440/390px 入口可见、无遮挡且无横溢 |
| `python3 tests/e2e/assistant.py` | 59/59 |
| `python3 tests/e2e/assistant_responses.py` | 24/24，合成 HTTP 模型 |
| `python3 tests/e2e/assistant_p3.py` | 23/23 |
| `python3 tests/e2e/assistant_race.py` | 两条竞争路径通过 |
| `python3 tests/e2e/assistant_review.py` | 28/28 |
| `python3 tests/visual/run.py --ref 574aed6 --pages assistant --out /tmp/omrs-assistant-expand-history-visual-20261011` | 欢迎页 4 组差异均为 0，无脚本错误、行内样式或横溢 |

首次增补的 E2E 未等待 requestAnimationFrame 后的折叠状态，出现一条时序断言失败；重复进入同一 hash 也没有重载页面，后续截图找不到已消失的分页入口。已改为条件等待和真实 reload，第二轮 24/24 通过，没有为此改变业务代码。

视觉产物在 `/tmp/omrs-assistant-expand-history-visual-20261011/report.html`；长运行展开前后 8 张截图在 `/tmp/omrs-assistant-expand-history-shots-20261011/`。已实际查看深色手机前后图：入口文案清晰，点击后处理过程与历史摘要展开、正文续接，完整读取提示消失；欢迎页没有该入口，所以四组基线比较没有差异。

`python3 tests/check_docs.py --write-log-index` 已生成索引；`python3 tests/check_docs.py --diff HEAD` 检查 105 个文档，0 问题，仅两份既有计划的大小提醒。`git diff --check` 通过；实际改动复核限定在本任务的代码、测试、页面文档、README、日志和索引。生产发布结果在执行后补记。

## 未执行的验证与遗留

未运行无关后端全仓门禁，也未代用户发送真实付费模型请求。Windows、实体手机和生产 PIN 后的实际历史由用户验收；当前主路径已在真实 Chromium、临时题库中验证。生产切换前须重新检查任务与恢复意图、采集本轮数据基线，并保留一致备份；不采用上一轮数量作为本轮证明。
