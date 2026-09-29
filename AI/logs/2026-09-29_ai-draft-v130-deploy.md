# AI 草稿 v1.30.0 合入 main 与生产发布

## 背景

用户原话：“提交并入main,切入生产”。执行者 Codex · 完整模式。本次明确授权本地提交、合入 main、生产切换和服务重启；未推送远端。代码切片已是2c7299a、4a39275、8b6009a，部署前main为2bb401c，生产为omrs-63adade（v1.28.1）。

## 行为变化

main已快进合入8b6009a，生产omrs.service从固定目录/root/workspace/releases/omrs-8b6009a运行v1.30.0；真实Vault仍/root/workspace/apps/OMRS，端口8471。AI草稿审核、确认入库、手动/自动框选和独立训练任务现已上线。切换停止服务至健康检查通过约1.28秒；217道题保持不变。

## 已有改动保护

原main工作区含训练记录、box-detect计划及本任务旧规划。先备份未提交文档与补丁到/root/workspace/backups/recycle/ai-draft-v130-20260929T070208，精确暂存受合入影响的7份跟踪文档与2份原未跟踪草稿计划文件；保护stash为6675c383ff1bc74931cc8fed9bb78ea17e3c4517，保留不用pop。

草稿总纲、执行说明和规划日志经逐字节核对已在分支中；草稿旧进度和事实订正由完成后的文档承接，不将旧状态覆盖回来。训练目录、box-detect目录及它们的日志保持原未提交状态，AI/README中的两条训练索引和计划索引的box-detect行按原文恢复；日志索引生成后仍保留这些未提交日志入口。.playwright-mcp未修改。没有提交其他任务的改动。

## 备份与切换

发布目录由git archive 8b6009a生成，先在该目录用/usr/bin/python3（3.13.5）和临时Vault验证。确认助手没有活动运行后停止omrs.service，将完整错题目录归档为上述备份目录的vault-before.tar，保留数据库、原图、配置和附件；备份目录0700、数据归档0600。另保存10-release.conf.before与数据哈希基线。

只替换/etc/systemd/system/omrs.service.d/10-release.conf中的发布路径，daemon-reload后启动服务；Nginx、模型配置、真实Vault路径和端口不变。旧omrs-63adade仍保留。恢复代码时将drop-in改回旧目录并重启，不用旧数据覆盖上线后新增内容；数据归档仅供需要时专项恢复。

## 影响文件

AI/environment.md更新实际生产目录；AI/README.md补生产环境查找入口；AI/plans/README.md与ai-draft/progress.md更新完成/上线状态；新增本日志并生成AI/logs/log.md。业务代码未追加改动。

## 验证

已实际执行：

- 发布目录 `env -u OMRS_SYSTEMD_SERVICE /usr/bin/python3 -m unittest tests.test_draft_p4_http -q`：6/6，真实HTTP子进程/临时Vault。
- 生产systemd为active/running、ExecMainStatus=0；/api/status返回ok、v1.30.0、217题；主进程来自新发布目录。
- 生产真实浏览器只读验收9/9：草稿区、版本号、聊天训练统计、框选三模式、全文字开关、独立标注页、390px无横向溢出、无脚本错误、无写请求。请求拦截器禁止非GET/HEAD/OPTIONS；未上传测试图片或创建测试题。
- 317个用户文件（含题目、附件及关键配置）哈希一致；5份数据库quick_check通过，原有表内容保持。扫描表只更新workspace_fingerprint.last_seen_at和workspace_scan_status.last_scan_at，逐列核对其余数据一致。
- 草稿、助手与设置3份生产JS与发布目录逐字节一致；模拟未登录远端的草稿计数、草稿列表、数据集统计均401；重启后的错误级journal为空。
- `python3 tests/check_docs.py --diff HEAD`：通过；`git diff --check`：通过。发布代码此前已通过Python278、Node354、19个E2E共681条断言，本轮代码未改，不重复全套。

证据：备份目录metadata.json、data-baseline.json、verification.json；/tmp/omrs-v130-release-http.log、/tmp/omrs-v130-production-browser.json。未执行真实远端设备登录、真实模型识别与生产写入试验；本轮没有调用模型或消耗识别服务额度。

## 下一步

生产已启用v1.30.0，可直接使用；后续真实模型质量验收使用隔离配置。保留备份、旧发布目录与未提交文档保护stash，不因代码回退覆盖真实数据。
