# v2.0.0 生产部署与 GitHub 同步

## 授权与范围

用户明确授权“部署生产，提交GitHub”。本轮基线 dccbe6b，main；用户未跟踪的 .playwright-mcp/ 原样保留。仅切换主服务固定发布目录，不修改 Nginx、检测服务、模型或真实配置。

## 发布与数据

从 git archive HEAD 生成 /root/workspace/releases/omrs-dccbe6b。确认助手 56 次运行、收件箱 145 个任务均 done 后停止主服务，完整归档真实错题目录并解包逐文件、数据库核验。备份 /root/workspace/backups/recycle/omrs-v200-20260930T000153Z，保存原 drop-in、哈希基线及 verification.json；目录 0700、归档 0600。归档 SHA-256：0b838e63226998f37601161b15159f5ee02994f7a6ea9a1062cfd35f85bb071b。

仅替换 10-release.conf 中代码路径，daemon-reload 后启动。停服至健康响应约 2.20 秒，v2.0.0、239 题、扫描无冲突，active/running、NRestarts=0、ExecMainStatus=0，错误级 journal 为空。5 个数据库 quick_check 通过；agent.db 新增 practice_cards/practice_attempts 表，原有表内容不变。Ledger 仅启动扫描时间戳变化，694 个提交链验证有效；原有非数据库文件哈希全部一致。

回退代码时恢复备份 10-release.conf.before 并 daemon-reload、重启；旧 omrs-c94e459 保留。不得用旧 Vault 覆盖发布后新数据；归档仅在确认数据损坏后专项恢复。

## 验证

固定发布目录执行 /usr/bin/python3 -m unittest tests.test_migration_compat -q：4/4 通过。首次误用不存在的 tests.test_v2_migration，导入失败；定位真实测试后纠正重跑。备份解包后文件哈希和数据库表计数与静止原库一致。生产只读 verify_ledger 返回 valid=true、errors=[]。curl 本地 /api/status 返回 v2.0.0；HTTPS 经 home.ruibin-ningh.top:8472 的未登录 API 返回 401，鉴权有效。

真实 Chromium 只读浏览器检查：1440×900 与 390×844 下 create、assistant、history 共 6 条路径通过，显示 v2.0.0，无横向溢出、脚本错误或写请求。证据 /tmp/omrs-v200-production/results.json 与截图。python3 tests/check_docs.py --write-log-index 已生成索引；python3 tests/check_docs.py --diff dccbe6b 检查 67 份文档、0 问题、3 条既有体量提醒；git diff --check 通过。生产未执行写入型 E2E、真实模型调用或真机验收；这些限制与 P7 交付一致。

## 文档

更新 AI/environment.md 的实际发布、备份路径和计划 progress 的上线状态；生成任务日志索引。不修改业务源码。

## GitHub 同步

发布前 git fetch origin 后 origin/main 与本地无分叉，本地领先 15 个提交。部署记录提交后执行 git push origin main，并核对远端提交；不创建额外 tag 或 Release。
