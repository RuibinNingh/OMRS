# 2026-10-03 OMRS v2.2.0 生产部署与 GitHub 推送

## 背景与授权

用户原话：「完成后部署生产,提交GitHub」。执行者 Codex，完整模式。修复及完整验收已独立完成，工作区干净，基线719db03；实现757e1ed，v2.2.0。本任务只实施发布、上线核验、文档与正常推送，不改写开发日志。

## 发布准备（进行中）

只读实测生产仍为omrs-97e0927/v2.1.0，主服务PID2579856，Tunnel及检测服务active/running、NRestarts=0。262活动题、扫描零冲突；助手67运行、收件箱169任务、草稿3任务均结束，MCP无running记录。七个.db路径中六个为实际SQLite，顶层旧inbox.db为空历史文件；全部quick_check为ok。磁盘约40GiB空闲。

已fetch远端，origin/main是本机main的祖先，修复分支与远端无分叉。生产源码将从精确719db03归档，共享既有venv，不升级依赖或模型。升级后的存储不允许仅回退v2.1代码，故障需保全新事实并保持v2.2契约前向恢复。

## 已实际执行的验证

已完成git状态/远端、systemd及监听、HTTP状态、纯SQLite只读盘点、任务与模型操作探测。首次停服一致文件归档在/root/workspace/apps/releases/OMRS-v220-preflight-20261002T180201Z/，tar比较及五项SHA全部通过，归档300431360字节；从停服到旧服务恢复约1.086秒，生产仍为旧版。真实副本的纯字节摘要验证720提交/269blob、六库integrity_check全部通过；新版scan后262活动题与1归档身份，当前正文无缺blob或冲突，既有历史缺口63项待原始副本对照。

复用生产Python3.13.5、MCP1.28.1、Pillow12.3.0与既有依赖，清除两个生产控制变量。全量unittest651项，110.678秒，退出0，无ResourceWarning或Traceback；系统Python的pytest报告7项通过（生产venv不含pytest，未安装依赖）。五个原始E2E：audit_identity15、instant23、MCP39、MCP扩展17、shell_router24，全部通过；六阶段升级/再升级/前向恢复再次通过。生产切换和推送待真实副本最终核验后执行。

门禁命令为env清除OMRS_SYSTEMD_SERVICE/OMRS_BOXDETECT_CONTROL后调用生产venv的python -W error::ResourceWarning -m unittest discover -s tests -p test_*.py -q，以及tests/run_gates.py --ref 17d6d84 --groups e2e,release --only e2e-mcp,e2e-mcp_expansion,e2e-shell_router,e2e-instant,e2e-audit_identity,upgrade-compat。原始日志保存在/tmp/omrs-v220-deploy-umcty7w1/。一次门禁命令误填不存在的e2e-audit_regressions，参数验证退出2且未运行测试；改成仓库真实audit_identity入口后全部直接通过。

## 未执行与下一步

真实副本迁移、生产切换、公网SDK/浏览器及GitHub推送待执行。已有本地完整验收结果见计划report.md与validation.json，不重复计入本次部署。

## 正文盘点发布前修复

部署契约审查发现，正文盘点后半段通过普通Ledger连接读取历史，旧库会被自动迁移。现改为单一SQLite只读事务覆盖投影、blob和全部历史引用，缺库时不创建错题目录；存在待恢复journal时领域入口及CLI均拒绝盘点。生命周期租约仍可建立独立维护锁文件，不修改业务数据。影响omrs/content_history.py、tests/test_content_integrity.py与AI/ledger.md。

实际验证：正文模块22项通过；正文加备份恢复关联36项通过。新增原生旧Schema夹具同时走领域入口及真实CLI子进程，逐项断言Schema、完整commits、全部文件SHA256和mtime不变，并覆盖缺库及待journal边界。使用719db03旧实现运行该回归时，领域与CLI两路均复现不变断言失败。全部使用临时合成Vault，未运行真实源初始化，源保全归档不变。

本修复收尾：已生成日志索引；`python3 tests/check_docs.py --diff HEAD` 检查94份文档、0处问题（2条既有大文件提醒），`git diff --check` 通过。未修改计划或维护环境文件，未提交，由发布主执行者集成。

## 影响文件（发布前切片）

已用git diff复核：正文盘点代码及三个回归、AI/ledger.md；计划总纲/进度登记追加授权，本独立日志与自动日志索引。没有修改页面、版本、生产配置、密钥权限或模型。后续生产环境及发布证据文档在上线验收后单独提交。
