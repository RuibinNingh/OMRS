# 2026-10-11 AI 助手的 OpenAI 选项使用 Responses

## 背景

用户原话：「那OpenAI协议后面加个括号(Responses)」「然后该协议为Responses」。执行者：Codex，完整模式。开工基线为 `2b030a6e4cbd916a60c42883ba34547734bc924b`，`git status --short` 为空。本次是协议适配的新任务，不重开已交付的 AI 助手计划，不修改生产配置、真实题库、服务、远端或版本号。

协议对照使用 OpenAI Docs 的[迁移指南](https://developers.openai.com/api/docs/guides/migrate-to-responses)、[函数调用指南](https://developers.openai.com/api/docs/guides/function-calling)和[流式事件参考](https://developers.openai.com/api/reference/resources/responses/streaming-events)，实际代码与合成 HTTP 走查结果作为本仓库行为依据。

## 行为变化

- 设置中的 OpenAI 选项显示为「OpenAI（Responses）」，保存值仍为 `openai`；选中后主对话、工具和连接测试实际请求 `/responses`。通用、阿里云百炼和 DeepSeek 继续使用 Chat Completions。
- 接受基础 `/v1`、完整 `/responses`，以及原先保存的完整 `/chat/completions` 地址；后者在发送时替换协议路径，不改写已保存配置。
- Responses 请求使用 `input`、`max_output_tokens`、平铺 function schema、`input_image` 和按 `call_id` 对应的工具输出。显式保留 `strict:false`，避免改变已有可选参数契约。
- 使用本地上下文与 `store:false`，保留原生 output 和加密推理项，不依赖 `previous_response_id`。旧消息按需转换，原生项随现有消息 JSON 持久化，不迁移表结构。
- SSE 文字、拒答、推理和工具参数事件归一成原助手事件；截断、失败、非法事件、缺终态断流和中止沿用既有安全结束规则。工具只在成功的完整响应后执行。
- 用量兼容 Responses 的输入、输出、缓存与推理明细；缺失、显式零、异常和子集规则保持。AI 识别和图片转述继续使用独立配置。

## 影响文件

- `omrs/llm/responses.py`：独立协议适配器，复用既有 HTTP 连接、超时、调试和中止。
- `omrs/agent/config.py`、`omrs/llm/compat.py`：按保存的选项选择协议。
- `omrs/agent/loop.py`、`omrs/llm/openai_compat.py`：统一结果中传递原生 output，并随助手消息保存和重放。
- `omrs/llm/usage.py`：兼容两套 token 字段。
- `assets/app/features/settings/agent-view.js`：选项名称与地址、协议提示。
- `tests/test_llm_responses.py`、`tests/test_usage.py`：请求转换、SSE、工具续轮、存储重读、截断、错误与用量回归。
- `tests/e2e/assistant_responses.py`：真实 Chromium、真实临时 OMRS 与合成 HTTP 供应商的完整闭环；统一门禁自动发现此脚本。
- `AI/agent.md`、`AI/data.md`、`AI/data/storage.md`、`AI/frontend/settings.md`、`AI/frontend/assistant.md`、`AI/frontend/architecture.md`、根 `README.md`：同步当前协议、存储与页面行为。日志索引由脚本生成。

## 已实际执行的验证

所有业务测试使用合成数据、临时 Vault 和随机端口，清除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`；新 Responses E2E 同时移除 FauxClient 环境变量，真实走 HTTP 协议适配器。

| 命令 | 实际结果 |
|---|---|
| `python3 -m unittest tests.test_llm_responses tests.test_agent_loop tests.test_usage -q` | 首轮 31 项通过；收尾追加参数类型回归后 32 项通过 |
| `python3 -m unittest discover -s tests -p 'test_*.py' -q` | 首轮 884 项通过；参数类型修复后最终 885 项通过，128.531 秒，退出 0，无跳过 |
| `node --test tests/app/*.test.mjs` | 455 项通过，无失败与跳过 |
| `python3 tests/check_ui.py` | 全仓五类违规计数均为 0 |
| `python3 tests/check_contrast.py` | 58 组通过，0 组不达标 |
| `python3 tests/app/run_browser.py` | 34 项通过，无页面错误 |
| `python3 tests/e2e/assistant_responses.py` | 13/13 通过：名称、保存与刷新、工具和图片探测、真实工具续轮、推理摘要、持久上下文、缓存入口、双宽度与错误审计 |
| `python3 tests/e2e/assistant.py` | 59/59 通过：原助手、确认与撤销、插话、中止、图片和窄屏主路径 |
| `python3 tests/e2e/settings.py` | 71/71 通过：原配置、保存、调参、连接相关界面和双主题双宽度审计 |
| `python3 tests/visual/run.py --ref 2b030a6e4cbd916a60c42883ba34547734bc924b --pages settings --settings-section assistant --out /tmp/omrs-responses-visual-20261011` | 浅/深主题 × 桌面/390px 共 4 组完成，无脚本错误、行内样式、小点击目标或横向溢出 |
| `git diff --check` | 通过 |
| `python3 tests/check_docs.py --write-log-index` | 已生成本次日志索引 |
| `python3 tests/check_docs.py --diff HEAD` | 105 个文档，0 处问题，2 条既有计划大小提醒，退出 0 |

新 E2E 首次使用非 ASCII 合成密钥导致请求不能发送，已改为 ASCII 合成密钥，并等待设置读取完成后填写表单；上述 13/13 是修正后的实跑结果，不使用假模型替代该链路。

收尾复核实测发现：供应商把工具参数返回为对象时，统一结果生成中的参数解析会抛出 AttributeError。已在 Responses 的工具项和参数事件处校验文本类型，保持「协议错误作为统一错误结果返回」的契约；新增对象、数组、数字和 null 的流式/非流式回归，专项 32 项全部通过。修复后再次运行全库单测（885 项通过）与 Responses 浏览器闭环（13/13 通过）。

## 视觉差异

报告在 `/tmp/omrs-responses-visual-20261011/report.html`。逐项核对截图与差异热区：

| 页面组合 | 差异比例 | 解释 |
|---|---|---|
| 浅色桌面 | 0.179% | API 地址提示改为按选项补全路径；协议提示改为 Responses / Chat Completions 的对应关系 |
| 深色桌面 | 0.172% | 同上，仅提示文字像素变化 |
| 浅色手机 | 0.373% | 同上；窄列中文字换行产生相应像素变化，表单仍为单列 |
| 深色手机 | 0.361% | 同上；各控件尺寸和水平布局审计保持通过 |

默认通用选项仍显示「通用」，新增名称由 Responses E2E 实际检查 option 内容与保存后的选择。未改设计 token、布局或样式。

## 未执行的验证与边界

- 未向真实 OpenAI 或第三方 Responses 服务发送付费模型请求，未读取生产模型密钥；HTTP、工具、图片和多轮上下文由独立合成供应商及真实浏览器验证。第三方必须实现对应 Responses 契约。
- 未运行依赖外部模型/数据的训练验收、Windows 或实体手机验证；本次不改这些路径。
- 未部署、重启生产或推送。生产当前运行独立发布目录，本地提交不会自动生效。

## 收尾

已按 `git diff HEAD --name-status` 复核本任务 19 个文件；日志索引由 `python3 tests/check_docs.py --write-log-index` 生成。文档门禁检查 105 个文档，0 处问题、2 条既有计划大小提醒；没有修改这两份历史计划。本次本地提交包含代码、测试、文档和本日志，版本保持 v2.3.9。没有已知未完成的本地实现；真实供应商验收与生产发布未执行，生产发布需要用户另行授权。
