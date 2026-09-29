# OMRS 2.0.0 计划进度

> **状态**
> - 目标：完成 R1–R11，形成 v2.0.0 候选发布；生产部署另行授权。
> - 阶段：P0、P1 已完成，P2 进行中。
> - 基线：`1d082194ad959aaf6d754a90ed95db9183484adc` / `v1.35.0`。
> - 下一步：Codex · 完整模式，执行 `exec-2026-09-29-p2.md`，连续推进至 P7。
> - 更新：2026-09-29。

## 开工复核

- 当前 HEAD 与计划调查基线一致；已阅读根 `AGENTS.md`、`AI/README.md`、计划总纲、进度和 P0–P7 全部执行说明。
- 开工时仅有用户未跟踪的 `.playwright-mcp/`，本计划不触碰。
- 计划包只有文档；已解入本计划文件夹。没有导入业务代码或应用补丁。
- P0 实测确认：草稿首屏先显示来源图与框选，审核正文在下方；quick AI 会合并返回的 labels；上传区的 `.crw-pane label` 覆盖组件 flex；助手拖拽只绑定输入区；即时练习不创建正式 Session。对应源码位置见 `plan.md` 源码证据索引。

## 阶段状态

| 阶段 | 状态 | 实现提交 | 验收结果 |
|---|---|---|---|
| P0 基线与契约 | 已完成 | `3ae6722` | 11 项入口与契约见总纲 §3、§8；基线门禁通过 |
| P1 AI 草稿审核工作台 | 已完成 | 待本轮提交 | 审核主路径 52/52、训练扩展 24/24；前端门禁通过 |
| P2 快速录入与字段安全 | 进行中 | — | 待验收 |
| P3 助手附件与移动交互 | 未开始 | — | 未执行 |
| P4 分类与 AI 草稿编辑工具 | 未开始 | — | 未执行 |
| P5 聊天练习卡与幂等反馈 | 未开始 | — | 未执行 |
| P6 历史摘要与用量 | 未开始 | — | 未执行 |
| P7 集成验收与 v2.0.0 发布准备 | 未开始 | — | 未执行 |

## P0 基线门禁

| 命令 | 实际结果 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 379 通过 |
| `node --test tests/app/*.test.mjs` | 377 通过 |
| `python3 tests/check_ui.py` | 0 处问题 |
| `python3 tests/check_contrast.py` | 58 组通过 |
| `python3 tests/app/run_browser.py` | 32 通过 |
| `python3 tests/e2e/drafts.py` | 44/44 通过 |
| `python3 tests/e2e/create.py` | 104/104 通过 |
| `python3 tests/e2e/assistant.py` | 58/58 通过 |

## 契约与夹具

- 总纲 §3.3、§3.7、§3.8、§3.11 固定了 quick 允许字段、草稿 revision/CAS、PracticeCard/反馈幂等和 usage 口径；实施时先写对应失败用例，再改生产代码。
- 现有隔离 Vault 夹具：`tests/fixtures/make_vault.py`；草稿多图、纯文本、独立训练任务见 `tests/e2e/drafts.py` 与 `tests/e2e/drafts_p4.py`；助手假模型见 `tests/fixtures/agent_faux.json`；浏览器启动见 `tests/browser_runtime.py`。阶段 E2E 继续复用，不连接真实数据。
- 基线草稿手机截图：`/tmp/omrs-ai-draft-p2-shots/light-mobile.png`。可见来源图和画布排在题目、答案正文前，长页需要大量滚动。该 `/tmp` 截图是本机临时验证物，不属于仓库交付物。

## 遗留与下一步

P2 需完成快速录入居中与空态、AI 字段补全与标记禁写、页码活动路径退役、共享控件；之后按 P3–P7 连续执行。P1 已在 Chromium 手机触摸环境验证逐题操作，真实设备软键盘仍属于 P3/P7 验收，不能记为已通过。

## P1 实测

- 默认阅读题目与答案，来源区显式展开；手机队列默认收起，题目 / 答案解析 / 信息切换；局部编辑在点击后显示。已入库草稿的独立训练框保持可编辑。
- 入库前重新读取当前 revision；版本变化时保留本地编辑并停止，成功时刷新并进入下一份待审草稿。旧入库身份与训练逻辑未改。
- `tests/e2e/drafts.py` 52/52（含服务端已入库但响应丢失后的同身份重试）、`tests/e2e/drafts_p4.py` 24/24；`node --test tests/app/*.test.mjs` 378/378；`tests/app/run_browser.py` 32/32；UI 0 处、对比度 58 组通过。
- `tests/visual/run.py --ref 1d082194ad959aaf6d754a90ed95db9183484adc --out /tmp/omrs-v2-p1-visual`：48 个仓库标准页面 0 差异、无脚本错误；该 fixture 没有草稿，实际草稿前后差异由专门 E2E 截图记录。基线手机图先出现来源大图/画布，当前图先出现题目与切换控件，来源按需展开。
