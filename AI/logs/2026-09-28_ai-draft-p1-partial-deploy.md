# 2026-09-28 AI 草稿 P1 前三步提前合入生产

## 背景

用户原话：「合并到生产,我要打包」；针对 P1 尚未完成，明确选择「现在合入已完成的三步」。执行者：Codex，完整模式。代码基线为生产 `d7b48ef`（v1.28.1）；发布提交为 `f863761`，含 P1-1 至 P1-3，另含已记录的展示板部署文档提交。原执行说明要求 P1-5 完成前不部署，本次按用户新指令提前部署；P1-4、P1-5 继续执行。

## 行为变化

- `omrs.service` 从固定目录 `/root/workspace/releases/omrs-f863761` 运行，真实 Vault 仍是 `/root/workspace/apps/OMRS`，端口仍为 8471。服务状态为 active。
- 主 AI 后端已能接收附图并创建独立草稿；前端贴图入口、缩略图、设置开关和草稿审核区尚未上线。旧工具 `create_text_question` 已下线，AI 录题暂存草稿，不直接入题库；当前草稿只能经接口查看。
- 用户可在当前工作区运行 `pack_for_ai.bat` 打包；本次未运行 Windows 打包脚本，也未推送远端。

## 影响文件与仓库外状态

- `README.md`：说明当前 AI 录题行为与未上线的入口。
- `AI/environment.md`：更新生产发布目录。
- `AI/plans/ai-draft/plan.md`、`progress.md`：记录用户授权的提前部署和剩余步骤。
- 本日志及脚本生成的 `AI/logs/log.md`：记录本次生产合入。
- 仓库外：新增发布目录 `/root/workspace/releases/omrs-f863761`；systemd drop-in 指向新目录；生产 `agent.db` 的一致性备份及 `config.json`、`boards.json`、`mastery_data.csv` 备份位于 `/root/workspace/backups/recycle/ai-draft-p1-partial-20260928T213003`。旧发布目录保留以便代码回退。

## 验证

已实际执行：`python3 -m unittest discover -s tests -p 'test_*.py' -q` 为 220/220 OK；`node --test tests/app/*.test.mjs` 为 326/326；`python3 tests/check_docs.py --diff d7b48ef` 为 46 个文档、0 处问题、2 条已有体积提醒；`python3 tests/e2e/assistant.py` 用临时 Vault 和假模型在真实浏览器通过 22/22。发布目录用临时 Vault 和随机高端口启动，`/api/status` 与 `/api/drafts/counts` 正常。生产重启后 `/api/status`、`/api/agent/status`、`/api/drafts/counts` 均返回 200；服务 active，错误级 journal 无新记录；备份前后 `config.json`、`boards.json`、`mastery_data.csv` 逐字节一致。

未执行：真实模型附图录题（P1-4 前端入口未完成）；Windows `pack_for_ai.bat`（由用户在打包环境运行）；远端推送和远端设备验收。

## 回退

若需回退代码，把 `/etc/systemd/system/omrs.service.d/10-release.conf` 的发布路径从 `omrs-f863761` 改回 `omrs-d7b48ef`，再运行 `systemctl daemon-reload` 与 `systemctl restart omrs.service`，核对 `/api/status`。本次未恢复真实 Vault 数据；备份仅在确认数据损坏时使用。
