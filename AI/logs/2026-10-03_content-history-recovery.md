# 2026-10-03 历史正文缺口补回

## 背景

执行者 Codex，完整模式；基线 f170aa1 / v2.2.0，分支 codex/omrs-content-recovery。用户原话：「之前的缺口你打算怎么办」「所以没有影响? 如果没有那么部署生产,提交GitHub」。63 个不同历史正文哈希涉及 44 道题，当前题目正文完整；缺口影响对应历史正文查看与还原。此任务独立于已完成的19项修复和生产发布，不重写其历史验收记录。

## 行为变化

本机只读盘点10份Vault归档的2,820份Markdown候选未命中；进一步检查21份源码ZIP和4个9月旧部署数据副本，690份Markdown候选中命中15个哈希，涉及15个题目身份。全部哈希与正文 `_omrs_id` 校验通过，首次引用为12次创建和3次外部元数据修改；其余48个版本尚未找到。原文、来源文件名和逐项清单只放0700/0600私人恢复目录，不进Git。

新增 content-recover 维护命令：默认预览，明确 --apply 才写入；候选身份、哈希、原始事实和首次引用索引全部一致才整批补回。只补缺失正文并追加脱敏回填审计，不替换当前题目、不改变学习数据、不覆盖损坏blob、不改原始流水。故障整批回滚，重复和并发重试只产生一个有效回填事实。正文引用抽取归并为一个纯函数，供索引、盘点和补回复用。

## 影响文件

omrs/content_recovery.py、omrs/cli.py 为维护入口；omrs/ledger.py 和 omrs/content_history.py 统一引用解析；tests/test_content_recovery.py 为行为回归。README.md、AI/ledger.md、AI/data.md 同步当前命令及存储契约。生产结果和维护环境在实际执行后登记。

## 验证

已实际运行：正文补回17项及正文完整性、Ledger并发、历史投影关联测试共51项通过，无ResourceWarning。最初测试辅助函数使用原生SQLite上下文但未关闭连接，39项通过伴随ResourceWarning；改为显式关闭后关联51项干净通过，生产代码不受该测试辅助问题影响。

统一门禁实际执行 `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONWARNINGS=error::ResourceWarning python3 tests/run_gates.py --ref f170aa1 --groups unit,e2e --only unittest,pytest-export,e2e-audit_identity,e2e-shell_router,e2e-instant`：670项unittest（111.286秒）、7项pytest、3个原始E2E共62断言全部通过，无ResourceWarning。E2E实际为身份15、即时练习23、外壳24断言，原入口和等待时限未改。原始日志位于/tmp/omrs-content-recovery-validation-24y37zhc/gates/。

已取得生产新版可信全库备份，254,260,203字节，冻结0.739342秒。最新副本上补回15个版本，缺口63降至48，当前缺失和冲突均0；全部原事实、原blob、6个实库业务表和870个普通文件逐字段/哈希保持。重试新增0事实；强制重建投影后全部业务字段继续一致，30个真实临时HTTP历史/正文读取检查通过。核验材料放/root/workspace/apps/releases/OMRS-content-recovery-20261003T010842Z-uvv8l1w4/，目录0700、私人文件0600。

本轮未重复Node、组件、打印、UI/对比度、视觉、其余E2E和万题十万反馈容量：前次发布已有完整结果，本轮仅增加维护命令与共享引用解析，没有页面、算法、HTTP路由或Schema变化；已运行全后端、关联回归、三原始E2E及真实副本核验。Windows、外部冻结模型与ChatGPT账户联调仍未执行。

代码回退兼容性已在恢复后的私人副本演练：生产原ec12293/v2.2.0直接读取15个补回版本并重建投影，全部原事实、blob和学习字段保持，Schema变化0。此结论仅适用于相同v2.2存储契约，不能据此回退v2.1代码或覆盖新事实。

## 生产与GitHub

待隔离核验及门禁通过后执行，实际结果随后追加。余下48个缺口保持明确不可用，不保证从缺失材料重建原文；AI/OCR重建只能视作新版本。
