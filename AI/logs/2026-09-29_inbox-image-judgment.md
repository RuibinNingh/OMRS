# 2026-09-29 一键提取留图判断提示词

## 背景

用户要求修复「一键提取」遇到题图仍转述成文字的问题，并授权提交 main、更新生产。执行者：Codex，完整模式；基线 `b482785`。开工前主分支有另一项收件箱重置工作的未提交代码、文档与日志改动，以及先前留存的未跟踪文件；本任务不纳入这些改动。

## 行为变化

收件箱「一键提取」的同次转录与判断提示词改用信息保留标准：若删掉区域裁图后，文本和 LaTeX 不足以保留解题或理解解析所需的信息，模型应返回 `convertible=false` 并说明原因。题干依赖图形、曲线、位置关系、表格或图片时，不因文字识别完整或能概述图意而判为可转。纯装饰图、软件界面控件不影响判断；能完整转录行列关系的简单表格仍可转。接口、存储格式和人工审核入口未变。

## 影响文件

- `omrs/ai_assist.py`：只调整 `JUDGE_SUFFIX`，供收件箱 `judge=True` 的一键提取使用。
- `AI/inbox.md`、`AI/api.md`：同步当前判定标准与不变的响应契约。
- `AI/environment.md`：同步当前生产发布目录、备份与旧发布回退位置。
- 本日志及脚本生成的 `AI/logs/log.md`：记录验证与部署结果。

## 验证

- 已执行：当前配置的 `deepseek-flash`（思考关闭）对三张合成图分别使用改动前、改动后的提示词各判一次。改动前：纯文字、函数图、依赖线段交点的几何题均判 `true`，后两者仅输出题干；改动后：纯文字 `true`，函数图和几何题均判 `false` 并说明需保留视觉信息。未发送真实错题图片；三例不能证明所有题型都准确。
- 已执行：`env -u OMRS_SYSTEMD_SERVICE python3 -m unittest tests.test_inbox tests.test_ai_assist_taxonomy -q`，31/31 通过；有三条既有未关闭文件的 `ResourceWarning`。
- 已执行：`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/create.py`，临时 Vault、随机端口及真实 Chromium，100/100 通过，含提取与人工切换保存方式的页面路径。
- 已执行：`python3 -m compileall -q omrs/ai_assist.py` 与 `git diff --check`，通过。
- 已执行：`python3 tests/check_docs.py --write-log-index` 与 `python3 tests/check_docs.py --diff HEAD`，54 份文档、0 处问题；两条既有文件体积提醒。
- 已执行：从提交 `2459490` 生成的发布目录内用系统 Python 运行 `tests.test_inbox tests.test_ai_assist_taxonomy`，28/28 通过；同三张合成图在该目录再次得到纯文字 `true`、函数图与几何图 `false`。
- 未执行：真实用户题图的批量误判率评估；本次未读取真实错题图片，三张合成图仅验证已复现的误判案例及纯文字回归。

## 部署

功能提交 `2459490` 已进入 main，源码经 `git archive` 固定到 `/root/workspace/releases/omrs-2459490`，发布目录的 `omrs/ai_assist.py` SHA-256 与提交内容相同。切换前 `omrs.service` active、`NRestarts=0`，助手、收件箱、草稿正在运行或排队的作业均为 0；原发布目录为 `omrs-ffccf6b`。

停止主服务后，将真实 Vault 一致性归档到 `/root/workspace/backups/recycle/inbox-image-judgment-20260929T044309Z/vault-before.tar`（187453440 字节），保存原 `10-release.conf` 和数据库表计数。更新 drop-in 并启动主服务；失败脚本会恢复旧 drop-in 并重启，本次无需回退。主服务的新 PID 为 825522，工作目录为 `omrs-2459490`；`omrs-boxdetect.service` PID 保持 512746，未重启。

上线后本机 `/api/status` 返回 ok、v1.33.0、题目数 217、工作区扫描变更与冲突均为 0。`omrs.service` active/running、`ExecMainStatus=0`、`NRestarts=0`，部署以来错误级 journal 无记录。五个数据库在切换前后 `quick_check` 均为 ok，全部表行数完全一致；备份目录内保存 `db-before.json`、`db-after.json`、`verification.json`。未推送远端。

如需代码回退，恢复备份目录内 `10-release.conf.before` 到 `/etc/systemd/system/omrs.service.d/10-release.conf`，执行 `systemctl daemon-reload` 并重启 `omrs.service`；旧 `omrs-ffccf6b` 发布目录仍在。不要用旧 Vault 覆盖上线后的数据。
