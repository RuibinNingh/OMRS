# 2026-11-15 问题工作台生产发布

> **任务**
> - 标识：problem-workspace-release
> - 状态：进行中

## 背景

用户原话：「版本号+0.0.1,上线生产我看看」。执行者Codex，完整模式；明确授权将本聊天完成的问题工作台升级至v2.11.1并上线生产，不包含GitHub推送。基线f2b9d33，原生产源码231ce95、v2.11.0；开工未提交内容均属于本聊天前一项已交付的问题工作台任务，逐项保留并纳入本次发布。

## 行为变化

发布紧凑问题列表、搜索／排序／分页、跨页选择、批量状态、可恢复回收站、响应式详情与未保存保护。版本同步为v2.11.1。沿用现有依赖、私有配置和业务数据；发布以本地提交的精确归档切换源码，回退保留最新数据。

## 影响文件

已核对git status --short和git diff --stat：已有问题域、HTTP、前端、测试及对应文档改动属于本聊天。本次另更新omrs/version.py、omrs_dashboard.html、README.md、AI/README.md及AI/changelog.md的版本；当前生产事实在上线验收后同步AI/environment.md，日志索引由脚本生成。

## 已执行验证

已只读确认三个生产服务active/running、NRestarts=0，使用稳定源码别名；当前398道题、0冲突。发布预检的助手、录入、草稿、审核、网关、检测与受管操作活动数均为0，未完成恢复和写入意图为0，训练锁可获得。

使用生产同一套Python3.13.5依赖，清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL及共享CDP环境后执行`python -B -m unittest discover -s tests`，1184项全部通过，179.707秒、exit 0。证据目录为`/root/workspace/apps/releases/OMRS-workspace-v2111-m2m4illn`（0700），完整输出在candidate-python.log。文档门禁检查165份文档、0问题，5条既有篇幅提醒；git diff --check通过。

UI纪律检查0违规，对比度58组全部通过。前一任务真实执行的Node594项、组件35项及页面验证详见该任务日志；本次从正式提交执行的精确归档与生产结果在实际运行后补入。

## 未执行验证

本次发布回归、精确归档验证、停服备份与切换、生产只读验收尚未执行；完成后据实更新。未授权GitHub推送。
