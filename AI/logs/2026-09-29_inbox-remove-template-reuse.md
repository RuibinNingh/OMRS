# 2026-09-29 收件箱移除模板与沿用框位并上线重置

## 背景

用户要求：「这两个功能不需要了,删掉吧」「你要审查相关代码,不要只删前端」「做完后提交main,然后连着之前的部署生产」。图片所指为收件箱框选工作区的「模板框选」和「沿用上一张框位」。执行者 Codex，完整模式；本次获授权提交 main 并部署生产，连同前一轮未提交的「重置此图」。基线 main `7234b5b`，生产旧发布 `omrs-2459490`。开工时已有 `AI/logs/log.md` 的用户改动、两份 2026-09-28 未跟踪日志和 `.playwright-mcp/`，保留且不纳入本任务提交。

## 行为变化

处理区和网格批量栏移除模板框选与沿用框位；收件箱状态、动作、区域复制函数和在线模板提供方同时删除。草稿自动框选与收件箱只使用 `vlm` 或 `local_http`；旧配置 `template` 读取时回退到 `vlm`，新配置和显式任务请求拒绝该值。训练用的历史模板几何基线独立放在离线 `evaluate.py`，已完成实验仍可复算；独立标注页的快捷键不属于收件箱入口，保持现有标注流程。前一轮的「重置此图」与本次一起发布，保留原图，旧任务结果不会恢复清空的进度。

## 影响文件

以交付前的 `git diff --name-status` 为准。业务代码涉及收件箱前端、收件箱与草稿框选后端、配置提供方校验、离线评估工具；测试覆盖前后端和浏览器；同步 README、模块文档、版本与变更记录。本次不改真实 Vault、模型文件、检测服务或 Nginx。

## 验证

已执行：Python 全量单测 348/348、Node 全量单测 367/367、录入页 E2E 104/104、助手 E2E 54/54、组件浏览器 32/32；UI 检查 0 处问题、对比度 58 组均通过。旧配置空 provider 微调后，相关 Python 单测再次运行 38/38。`git diff --check` 通过。部署前再次运行文档差异门禁并在下方记录结果。

视觉对比 `python3 tests/visual/run.py --ref HEAD --pages create --create-stage process`：4/4 截图有预期差异，桌面约 2%，手机约 16–18%，处理区按钮删去后画布和下方内容上移；无脚本错误。`--create-stage train`：4/4 截图有预期差异，桌面浅色和深色均 0.002%，手机浅色 5.214%、深色 5.142%；提供方说明删去模板文字后卡片高度缩短，下面的输入项上移；无脚本错误。两组桌面与手机浅色截图已目视检查，无异常遮挡。报告分别在 `/tmp/omrs-inbox-remove-process-visual/report.html` 与 `/tmp/omrs-inbox-remove-train-visual/report.html`。

文档差异门禁 `python3 tests/check_docs.py --diff HEAD`：54 个文档，0 处问题，2 条既有大文件提醒。固定发布目录 `/root/workspace/releases/omrs-f803f2d` 再跑相关 Python 单测 38/38。生产只读 Chromium 在桌面/手机、浅色/深色四档均确认 v1.33.1、重置入口可见、两个旧入口消失、无横向溢出、脚本错误和写请求；5 份关键 JS 与发布目录逐字节一致。证据 `/tmp/omrs-remove-production/results.json` 及同目录截图。

未执行：真实外部模型识别质量和真实远端设备登录；本任务验证应用逻辑、隔离浏览器路径和生产只读页面，不把测试替身当作模型质量验收。

## 部署

功能提交 `f803f2d` 已提交 main；固定发布目录 `/root/workspace/releases/omrs-f803f2d`。切换前确认助手运行均 done（25）、收件箱作业均 done（115）、草稿无作业；原服务从 `/root/workspace/releases/omrs-2459490` 运行 v1.33.0。

停主服务后备份真实 Vault 和原 `10-release.conf` 到 `/root/workspace/backups/recycle/inbox-remove-template-f803f2d-20260929T050505Z`，归档 SHA-256 为 `92389eb282cacf860458a1d51568214cff6c6358cbc950bae87e02197d04c763`。切换后 5 个数据库 `quick_check` 通过且各表行数未变；732 个非数据库文件哈希一致。主服务 active/running、ExecMainStatus=0、NRestarts=0，v1.33.1 HTTP 响应正常，近时段错误级 journal 无记录。检测服务 PID 保持 512746，模型配置和 Nginx 未改。

回退时恢复备份中的 `10-release.conf.before`，执行 daemon-reload 并重启主服务；旧发布目录保留。不得用旧 Vault 覆盖上线后新增数据。本次未推送远端；已授权的 main 提交与本机生产部署完成，下一步为用户刷新页面使用。
