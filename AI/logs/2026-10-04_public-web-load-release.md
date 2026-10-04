# 2026-10-04 公网加载优化 v2.3.1 生产发布

## 背景

用户原话：「版本升级0.0.1」「然后部署生产,提交GitHub」。执行者：Codex，完整模式。开发提交 `ec2ebca`，开工工作区干净，生产源码 `de10022` / v2.3.0，GitHub main 为 `21b4bb1`。本日志为独立发布任务，不改写已交付的开发日志。

## 行为变化

版本升级为 v2.3.1，发布 gzip、原生模块预加载、主样式合并和内容版本静态缓存。沿用既有 Vault、Web / MCP 端口、公网地址、PIN、MCP 权限、Nginx、Tunnel、模型服务和虚拟环境，不安装或升级依赖。本次不改变数据库 schema 或题库格式。

## 影响文件

`omrs/version.py`、`omrs_dashboard.html`、根 `README.md`、`AI/README.md` 同步版本；`AI/changelog.md` 添加版本摘要；`AI/frontend/shell.md` 更新可验证的加载约定与侧栏版本。发布后更新 `AI/environment.md` 当前环境事实。本日志与脚本生成的 `AI/logs/log.md` 记录发布、验证和推送结果。部署脚本、原始 Vault 保全及私人对照材料只存仓库外。

## 发布前核对

主服务 active/running、NRestarts=0，代码目录 `/root/workspace/apps/releases/omrs-de10022`，主 PID1977331；Tunnel PID875442、检测服务 PID1532134，均正常，活动题262。GitHub main 无新分歧，可正常快进；禁止强推。agent / inbox / drafts / runtime / ai_review 五个运行库未终结任务数均为0，无整库恢复 journal 或正式题目写入意图；切换前再次复核。

## 验证

开发轮实际已通过 809 项 Python、449 项 Node、资源专项 17 项及相关真实浏览器验证，56 组截图无视觉差异。本轮只针对版本与精确 release 运行适当检查，不无因重复全套业务门禁。

已实际运行 `python3 tests/check_ui.py`（五类全仓计数0）、`python3 tests/check_contrast.py`（58组全部通过）、生成日志索引和 `python3 tests/check_docs.py --diff HEAD`（102份文档0问题，2条既有篇幅提醒）。`python3 tests/visual/run.py --ref ec2ebca --pages dashboard --out /tmp/omrs-v231-version-visual` 比较桌面/手机与浅/深四档：桌面差异0.001%为侧栏 v2.3.0 → v2.3.1 文案，手机侧栏底部隐藏、差异0%，尺寸一致、无脚本错误。

精确 release 的现有 venv 已核对 Python3.13.5，含浏览器验证依赖；未安装或升级包。发布源码和隔离测试实际结果待执行后补入。

## 生产与 GitHub

待生成精确 Git 归档 release，复用旧虚拟环境，停主服务保存完整 `错题/`、`.omrs-maintenance/` 及原 unit/drop-in 后原子切换代码路径。启动失败不以旧 Vault 归档覆盖新事实，保全当前现场。部署后核对版本、文本压缩、缓存、Web/MCP 授权和原业务事实；正常推送 origin/main 并核对远端 SHA。

## 下一步

完成版本门禁、精确 release 验证、生产切换与 GitHub 推送，补齐本日志和环境文档。用户已授权这些步骤，连续执行。
