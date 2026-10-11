# 2026-10-11 Responses 输出速度、推理摘要与诊断

## 背景

用户原话：「参考Hermes的实现,稍微加一些日志用于排查,修复问题,上线生产」。执行者 Codex，完整模式；本轮用户明确授权生产发布。基线 `43d6cba`，开工工作区干净，版本保持 v2.3.9。范围限于助手 TPS、Responses 摘要保留及少量诊断，不修改题库、模型设置或网关配置。

此前只读调查中，运行 `run_6434a061` 的四轮供应商输出共 1187 token，其中推理 48；输入不曾计入 TPS。前端却使用约 878.43 token 的字符估算作平均速度分子，而且活动轮次耗时尚未入分母；历史只读初页时完成耗时为零。日志中的推理项摘要为空，缺原始 SSE，不能判定上游未返回还是链路丢失。

参考 Hermes Agent 的固定提交 `d4d2ab7b5d104166e7e22a02cafd12f1fe456a31`：`agent/codex_runtime.py` 保存 `output_item.done`，摘要增量按 `summary_index` 分段；`agent/codex_responses_adapter.py` 分离可读摘要和加密上下文。OpenAI Docs 的推理指南确认输出用量已含推理，摘要需 `summary:auto` 显式请求；现有 OMRS 请求已带此项，本轮不调整推理强度。

## 行为变化

- 已结束轮次的 TPS 使用供应商输出回执，推理不重复加，输入／缓存／图片辅助不计；当前轮次估算输出与生成耗时同步统计，估算显示 `≈`。
- 未读全的历史不发布最终平均速度；耗时由起止元数据补齐，完整事件到达后以 `run.end` 为准。
- Responses 的分段摘要、仅完整摘要事件和推理完成项逐段补齐并去重；终态清空或省略推理项时保留完成项与加密上下文。工具完整性门槛保持。
- `analysis/commentary` 消息沿用 Hermes 的思考通道；工具参数之后补发的摘要也能在页面出现。
- 既有模型日志开关下每个流式请求增加一条 `responses.stream` 计数诊断，不新增正文、工具参数或加密内容日志；断流与中止也记录。

## 影响文件

- `omrs/llm/responses.py`：完成项与摘要补齐、分段和去重、思考阶段消息、计数诊断。
- `assets/app/features/assistant/state.js`、`view.js`、`insp-view.js`：TPS、历史耗时和迟到摘要的归约与展示。
- `tests/test_llm_responses.py`、`tests/app/assistant.test.mjs`、`tests/e2e/assistant_responses.py`：协议边界、真实回执口径及真实浏览器重放。
- `AI/agent.md`、`AI/frontend/assistant.md`、`AI/frontend/architecture.md`、`README.md`：同步当前行为；本日志与自动索引记录验证和发布。

## 验证

所有业务验证使用临时 Vault、随机高端口，移除 `OMRS_SYSTEMD_SERVICE` 与 `OMRS_BOXDETECT_CONTROL`；未发送生产付费模型请求。初步专项 Python 41 项、助手与历史 Node 37 项通过。最终实际门禁如下，均无跳过：

| 命令 | 实际结果 |
|---|---|
| `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_llm_responses tests.test_agent_loop tests.test_usage tests.test_agent_tools tests.test_agent_pagination tests.test_agent_images tests.test_asset_cache tests.test_web_assets -q` | 88/88 通过 |
| `node --test tests/app/*.test.mjs` | 474/474 通过 |
| `python3 tests/app/run_browser.py` | 34/34 通过 |
| `python3 tests/e2e/assistant.py` | 59/59 通过 |
| `python3 tests/e2e/audit_identity.py` | 24/24 通过 |
| `python3 tests/e2e/assistant_responses.py` | 30/30 通过 |
| `python3 tests/check_ui.py` | 五类计数全零，0 问题 |
| `python3 tests/check_contrast.py` | 58 组，0 不达标 |
| `python3 tests/visual/run.py --ref 43d6cba --pages assistant --out /tmp/omrs-responses-metrics-visual-20261011` | 欢迎页双主题、双宽度 0/4 差异，无脚本错误 |
| `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD` | 索引已生成；105 份文档，0 问题，仅既有两份大计划的拆分提醒 |
| `git diff --check` | 通过 |

Responses 真实合成 HTTP／Chromium 闭环覆盖分段、仅 done、终态摘要丢失、去重、供应商输出 TPS 和刷新重放；验证每轮恰好一条计数诊断且无敏感正文。截图在 `/tmp/omrs-responses-metrics-shots-20261011/`；检查器实图可见两段摘要、含推理的 60 输出 token 和不含首 token 等待的速度说明。UI 文案变化不影响欢迎页四组基线；专项运行截图逐项检查摘要段落、检查器口径、标题层级与横溢，全部符合预期。

真实历史仅用 SQLite `mode=ro` 读取并在 Node 中重放，未改生产数据：`run_6434a061` 首 200 事件的耗时由元数据补为 36,287ms、TPS 暂不展示；完整 1092 事件的耗时 36,283ms，输出 1187、生成耗时 24,144ms，平均 49.163353214 tok/s。推理 48 已含在 1187 中，不重复相加。原记录无 think 事件且可读原生摘要为空，旧缺失摘要不能追溯恢复。

首次专项命令误填不存在的 `tests.test_llm_usage`，正确模块为 `tests.test_usage`；没有据此记为通过。新增 E2E 首次从已停用的 `events_json` 读取事件，导致空列表除零，已改为持久事件分页；这属于验证代码错误，不是模型速度为零。记录实际通过的后续结果。

## 生产发布与遗留

生产发布将在完整门禁通过后执行，先检查未终结任务与恢复意图，再一致备份、精确源码归档和原子切换。发布证据、实际状态及未执行验证将在完成后更新。上游若未返回可读摘要，本轮不能从加密内容生成；新增诊断用于区分阶段丢失。Windows、实体手机与真实生产模型摘要仍需实际使用验证。
