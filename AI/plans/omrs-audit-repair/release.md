# v2.2.0 发布与恢复材料

执行者：Codex 或 Hermes Agent，完整模式。已提交实现为757e1ed（v2.2.0）。本文是本地验收材料；生产停服、备份、切换、重启与推送须单独授权。

## 1. 升级与代码回退演练

### 1.1 已实际执行

运行 `python3 tests/check_upgrade_compat.py --ref 17d6d84`。脚本用 `git archive` 将旧代码导出到仓库外空目录，新旧代码各在独立 Python 进程中运行，只操作自己生成的临时 Vault。每个阶段单独断言、留日志和 JSON；环境清除生产控制变量。

2026-10-03 已重复纳入统一门禁的release组；每次运行生成独立results.json，最终实际证据清单存validation.json，六个阶段均符合断言：

| 阶段 | 实测结果 |
|---|---|
| 旧版建库 | 创建旧题、旧 Session、归档、同 UID 新题，共 4 条事实；旧整表唯一约束使投影只剩 1 个身份 |
| 升级 | 当前启动磁盘流程恢复 2 个身份，旧题仍归档；旧 Session 绑定创建时的旧 ID，UID-only 反馈明确拒绝；新反馈和元数据更新追加后共 8 条事实 |
| 仅回退代码重放 | 旧投影器将新题 SQL 标签重置为待攻克，链头未变化；新触发器在删除投影行时废止检查点 |
| 再升级 | 通过正常重建入口全量重算一次，SQL 与当前状态均为已击杀；8 条提交的 payload、时间、schema、哈希逐项不变 |
| 回退后旧代码写入 | 旧 Session 本应绑定旧题，旧版却给同 UID 的新题追加反馈；直接降级不安全 |
| 保留事实的前向恢复 | 当前代码保留全部已追加事实，明确追加 `review.retract` 纠正已确认的错归属反馈；最终 11 条事实，当前备份恢复到另一临时 Vault 后仍全部保留、链校验通过 |

退出码 0 表示上述演练结论经过验证，**不表示旧版本可以安全读写升级后的库**。该工具已在统一门禁的 `release` 组直接通过，最终证据以validation.json及任务日志登记为准。

### 1.2 升级约束

升级会移除题目投影 UID／路径的整表唯一约束，改为仅活动题唯一；新增 SQL 历史、修正索引、活动配置与正文版本引用索引。投影可从 Ledger 重建，既有提交、payload 与哈希不修改。稳定 Session 绑定由创建时状态证明，不能证明的 bootstrap 条目保留 unresolved。

上线前须保全当前全部存储的一致备份，在隔离副本上跑升级、Ledger 校验、正文盘点、身份主路径和统一门禁，再切换代码。旧 CSV 是显式导出物，不能作为升级后主数据回写 SQL；活动配置来源为 SQLite，镜像冲突须在监听前解决。

### 1.3 支持的回退策略

不得把 v2.1.0 直接启动在已升级并产生新事实的 Vault 上，也不得用升级前 Vault 归档覆盖上线后数据。实测旧 Session 会串题；旧代码不认识当前活动配置和助手事件存储等新契约。检查点失效触发器只能保证再次升级重建派生缓存，不能阻止旧程序错误写入。

发生问题时保留最新 Vault 与全部不可变事实，使用兼容 v2.2.0 存储契约的修复版本前向恢复。在隔离代码副本中修正造成事故的具体行为，保持稳定身份、活动配置、生命周期、事件库与迁移读写边界，跑完整门禁及本节演练。若曾误运行旧代码，先核对旧程序追加的事实，只有确认错误后才用现有历史修正接口追加撤销／替换；不自动改写它们。

完整模式的本地准备命令如下，代码路径和提交必须来自最终已提交的发布材料，Vault 只能使用临时备份副本：

```bash
git worktree add --detach "$OMRS_REPAIR_CODE_DIR" "$OMRS_V220_COMMIT"
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/run_gates.py --ref 17d6d84
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/check_upgrade_compat.py --ref 17d6d84
env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 omrs_engine.py --vault "$OMRS_REPAIR_TEST_VAULT" scan
python3 omrs_engine.py --vault "$OMRS_REPAIR_TEST_VAULT" content-audit --json
```

上述命令在待修代码目录运行；独立代码 checkout 中的修复还必须验证新事实前缀不变。脚本内的当前备份／隔离恢复阶段已经实际验证这条路径。生产备份、写操作暂停及切换仍是独立授权步骤，本轮未执行。

### 1.4 未执行的兼容性验证

没有对真实 Vault 升级或回退，没有切换生产服务，没有演练 Windows 文件锁，也没有穷举所有历史备份和外部集成。合成夹具能验证上述身份、投影与事实保留契约，不代替上线前的一致备份和真实副本核验。
