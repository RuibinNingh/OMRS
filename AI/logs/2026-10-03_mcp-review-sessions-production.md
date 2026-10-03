# 2026-10-03 MCP 正式复习调度生产发布

## 背景与授权

开发已交付b41a65a（v2.2.1）。用户随后明确要求「部署生产,推送GitHub」，并补充「不需要验收」。执行者Codex完整模式，开工工作区干净，生产为omrs-066f39f / v2.2.0，GitHub main为afbad60。本日志是独立发布任务，不改写开发日志历史计数。

## 发布结果

源码为b41a65a1fdd473ef78570f040bac3ae75ec236e7，使用git archive创建/root/workspace/apps/releases/omrs-b41a65a；venv相对链接复用omrs-bbf3757/.venv，没有安装或升级依赖。停服后将完整错题目录（含SQLite主库/WAL/SHM）归档，仅原子替换/etc/systemd/system/omrs.service.d/10-release.conf的三个release路径，再daemon-reload并启动主服务。

实际备份、切换和启动确认1.750秒，完成时间2026-10-03 10:09:55北京时间。主服务active/running、PID491135、NRestarts=0；本机/api/status返回v2.2.1。Tunnel保持PID875442，检测服务保持PID1532134，均active/running、NRestarts=0，未重启其它服务。真实Vault、端口、公网URL、Nginx、PIN与既有Key权限未修改。新增session:create仍须用户显式启用，并同时保留omrs:read后刷新客户端工具清单。

## 保全与失败恢复

保全目录/root/workspace/apps/releases/OMRS-v221-release-20261003T020953Z-yd48j3uz为0700、材料为0600。含vault.tar、旧unit/drop-in、精确Git代码归档、部署脚本、deployment.json及SHA清单。旧代码release和依赖目录保留。本次未发生发布失败或回退。

部署脚本在启动失败时恢复旧drop-in并启动原主服务，不恢复旧Vault。人工代码恢复也只恢复10-release.conf.before，再daemon-reload并重启主服务；不得以备份覆盖上线后新增数据。

## GitHub

实际执行git push origin main，正常快进afbad60..b41a65a，无强推。git ls-remote --heads origin main返回b41a65a1fdd473ef78570f040bac3ae75ec236e7，与发布源码一致。本次实际发布记录作为独立文档提交，随后继续正常推送；不将真实Vault、备份、私有状态或数据库加入Git。

## 实际确认与未执行项

按用户「不需要验收」不运行新增验收：没有复跑Python、Node、浏览器/E2E、生产SDK或生产业务数据对照，没有创建验收Key或测试业务对象。仅在发布前确认没有queued/running/pending任务、保存停服一致备份，切换后确认服务启动与本机版本；这是发布步骤，不冒充业务验收。开发轮已通过的718项Python、437项Node与220项网页验收保持原记录，没有重复计入本轮。

未做公网业务写入、ChatGPT账户联调或Windows实机验证。未查看或修改用户正文、反馈、学习状态与模型。

## 影响文件与收尾

更新AI/environment.md当前release与恢复路径、AI/mcp.md线上能力、AI/plans/README.md、mcp-review-sessions/plan.md与progress.md的追加授权和发布状态；新建本日志，AI/logs/log.md由脚本生成。业务源码、版本与开发日志未改动。生产仍为精确b41a65a源码，发布文档提交单独推送。文档生成及格式检查不访问生产或执行业务验收。
