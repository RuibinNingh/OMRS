# AI 录题与草稿区多智能体执行规划

## 背景

用户原话：“AI 录题与草稿区  我要推进,你做一个计划,这个计划的目的是为了等会执行委派几个智能体一起干活,模型是GPT 6 Sol Xhigh”。执行者：Codex · 完整模式；本轮只规划，未委派智能体。基线 `2bb401c`，v1.29.0；开始时已有未跟踪 `.playwright-mcp/`，保留不动。

## 行为变化

没有业务行为变化。新增 P2–P4 统一执行说明，安排主控 + 三个 GPT‑6 Sol / xhigh 执行智能体，分别负责后端、草稿工作区、助手与设置。每期并行实现、串行集成与提交，先交审核入库，再做手动框选 / 训练、自动框选；阶段验收不是默认停止点。本轮未改代码、测试或运行配置，未创建实现提交，未推送或部署。

计划按当前代码补齐：全文字草稿的来源图关联、图文块顺序、revision 与确认版本、跨 Ledger / 草稿 / 文件的入库恢复、训练专用队列隔离、独立训练任务与后台作业、图片引用安全清理。以上均是待实现契约，不是宣称已完成的功能。

模块文档订正：草稿有事件日志，“不进 Ledger”不等于“不留痕”；补充现有源码未保存完整来源图集合的事实；未来更新接口统一为 update。收件箱文档的单线程说法改为当前 ThreadingMixIn + 全局写锁行为。

## 影响文件

- 新增 `AI/plans/ai-draft/exec-2026-09-28-parallel.md`：十节执行说明，包含分工、文件所有权、派发模板、API / 数据契约、验收、完整命令、停止与恢复规则。
- 更新 `AI/plans/ai-draft/plan.md`：追加本轮原话、协作方式与已明确的技术决定，标明原立项快照；旧 P1 执行说明保留。
- 更新 `AI/plans/ai-draft/progress.md`、`AI/plans/README.md`：切换下一步到统一执行入口，记录实测门禁，区分规划与实现。
- 更新 `AI/drafts.md`、`AI/inbox.md`：订正本轮已核实的文档事实。
- 新建本日志，使用 `tests/check_docs.py --write-log-index` 生成 `AI/logs/log.md`，不手改索引。

过程中观察到其他任务新增 `AI/training/`、`AI/logs/2026-09-28_training-records.md`，以及 `AI/README.md` 和日志索引的相关变更。本任务保留这些改动；生成日志索引时保留它们的条目，不纳为本任务交付。

## 验证

已实际执行：

- `git status --short`、`git log --oneline -8`，并在收尾用 `git diff --name-status` 复核持久改动范围。
- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：226 个测试，OK；输出在 `/tmp/omrs-ai-draft-plan-python.log`。
- `node --test tests/app/*.test.mjs`：339/339，通过；输出在 `/tmp/omrs-ai-draft-plan-node.log`。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant.py`：真实浏览器 32/32，通过；输出在 `/tmp/omrs-ai-draft-plan-assistant.log`。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/create.py`：真实浏览器 80/80，通过，含四档页面审计；输出在 `/tmp/omrs-ai-draft-plan-create.log`。
- 临时 Vault 探测：带 images 的全文字 create_draft_tool 得到 review，但其文本块 image_sha 为 None，现有草稿库只有 images / conv_images / drafts / blocks；没有单独来源关联。调用 `_section_body` 的结果为两段文字之后才插图，印证有序块入口的必要性。探测代码仅以内联命令运行，未进入仓库。

- `python3 tests/check_docs.py --write-log-index`：成功生成索引，保留其他任务条目。
- `python3 tests/check_docs.py --diff HEAD`：退出码 0，检查 48 个文档，0 处问题；两条已有体积提醒来自 `AI/api.md` 和前端重构执行说明，本任务不拆分无关文档。
- `git diff --check`：通过。

上述基线测试不代表 P2–P4 已验收。

未执行：P2–P4 新功能测试（尚未实现）；真实模型识图与真实生产验证（本轮只规划，不使用生产数据 / 密钥）；全量其它 E2E 与视觉前后对比、UI / 对比度门禁（没有页面、样式或业务代码变更，已做相关两条浏览器基线回归）。

## 下一步

用户开始执行后，由 Codex · 完整模式按 `AI/plans/ai-draft/exec-2026-09-28-parallel.md` 阶段 0 复核，再委派三名 GPT‑6 Sol / xhigh 执行智能体连续完成 P2–P4。本轮不启动实现，不把部署作为本地交付前置条件。
