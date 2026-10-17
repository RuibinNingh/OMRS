# 2026-10-18 作业帮识别提示提交 GitHub

## 背景与范围

用户原话：「提交一下GitHub」。执行者Codex，完整模式；本次提交上一轮已经验收的居中「识别中」提示，沿用v2.8.2。

远端main基线为19b31cf8aba2a05e3fb3d1757a52796aeb3ede04。开发分支另有未发布的设置日志导出提交cfd2727，因此先把识别提示按路径提交为447ea2a，再在独立工作树按增量应用到远端基线，目标为GitHub main。共享README、设计系统和日志索引逐项复核，未将设置日志导出带入本次范围。

开发工作区原有AI/plans/omrs-maintenance/validation.json保持不变，不纳入提交。上一轮日志保留其交付当时的验证和未发布状态，本次另建记录。

## 行为与影响文件

- assets/app/features/zuoyebang/zyb-dialog.js与zyb.css：识别期间在工作窗中央显示醒目状态卡；结束或失败自动移除，支持在途恢复、减少动效和继续填写。
- README.md、AI/zuoyebang.md、AI/frontend/zuoyebang.md、AI/frontend/design-system.md：同步现行行为。
- 上一轮识别提示日志、本日志与自动生成的AI/logs/log.md：保留验证证据并记录提交范围。

未修改后端、数据格式或版本号。本次不包含生产部署或服务重启。

## 已实际执行的验证

开发分支提交前再次运行python3 tests/check_docs.py --diff HEAD与git diff --check，146份文档0问题，3条既有大小提醒。发布工作树的两个业务文件与已验收开发文件逐一SHA256一致。

发布工作树在不含设置日志导出的main基线上重新运行：

- node --test tests/app/*.test.mjs：539通过，0失败／跳过；与开发分支542项的差额是未纳入的设置日志导出测试。
- 使用既有完整依赖解释器omrs-zyb-deps-20261011/.venv/bin/python运行tests/e2e/zuoyebang.py：156/156通过，0脚本错误；启动前清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL、OMRS_TEST_CDP_URL，使用临时Vault、随机端口及真实Chromium。产物为/tmp/omrs-zyb-recognizing-github-e2e。
- python3 tests/check_ui.py：五项计数均0，全仓0处问题。
- python3 tests/check_contrast.py：58组通过，0组不达标。
- python3 tests/check_docs.py --diff HEAD：146份文档，0处问题，3条既有大小提醒。
- git diff --cached --name-status、git diff --cached --check：复核仅本次范围，无空白错误。

本日志加入后重新以python3 tests/check_docs.py --write-log-index生成索引，再运行文档差异门禁；结果仍为146份文档0问题，3条既有提醒。

## 未执行与边界

上一轮已完成35项组件浏览器检查、12项识别提示专项和4组标准视觉对比，本轮复用原证据。没有使用真实作业帮账号、付费模型、生产端口或真实错题数据。未执行部署、systemd操作或实体手机验证。
