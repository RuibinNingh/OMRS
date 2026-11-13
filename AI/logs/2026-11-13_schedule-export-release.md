# 2026-11-13 复习导出 v2.10.0 发布与 GitHub 合入

> **任务**
> - 标识：schedule-export-release
> - 状态：已交付

## 背景

用户原话：「很好,版本号+0.1 上线生产,提交GitHub合并main」。执行者 Codex，完整模式，已获版本升级、提交、推送、合并 main、生产切换及必要服务重启授权。按三段式版本号升级次版本，v2.9.0 → v2.10.0。

开工基线 `f33f6f7`，当前 main 与远端一致；工作区已有本聊天交付的复习导出功能和文档，全部保留并随本次提交。原功能证据见本日 `schedule-export-history` 任务记录。生产实际为 `01ec30b` 精确归档、v2.9.0；独立的 SVG 发布任务已提交，不重复修改其历史记录。

## 行为变化

将已验收的导出参数记忆与历史柱状图发布到生产。版本号、侧栏、根 README、AI 项目摘要和版本变更记录同步到 v2.10.0。发布只切换已提交源码，沿用生产依赖和配置；业务数据不参与功能测试。

## 影响文件

已用 `git status --short` 识别本聊天导出功能全部已跟踪与新增路径。新增版本改动为 `omrs/version.py`、`omrs_dashboard.html`、`README.md`、`AI/README.md`、`AI/changelog.md`，以及本任务日志和自动生成的日志索引；生产事实在实际上线后更新 `AI/environment.md`。

## 已执行验证

- 核对 main、远端、最近提交和三服务；开工 active/running、NRestarts=0，原别名为 `omrs-01ec30b`。`git fetch origin main` 成功。功能与版本提交 `a9f567261e79652a7cf32fe376951ad8feb80094`，通过 `git merge --ff-only codex/schedule-export-history` 合入 main，`git push origin main` 成功，GitHub REST ref 再次核对同一提交。
- 生产候选使用 `git archive` 精确归档 `/root/workspace/apps/releases/omrs-a9f5672`，1650 文件逐字节核对，复用原依赖、不安装或升级包。发布脚本与私有证据放 `/root/workspace/apps/releases/OMRS-export-v2100-qbzxnujl`，目录0700、备份0600，不进入 Git。
- 从精确归档运行 `release.py validate`，`gates.json` 记录10项全通过。后端119项（导出、历史投影、字体、边界、缓存、安全、写锁、MCP及备份），Node578项、组件浏览器35项、调度E2E46项、导出E2E22项、打印与字体19项；均无失败或跳过。实际命令、退出码、耗时保存在门禁清单和逐项日志中。测试清除两个生产控制环境与共享CDP，仅使用临时Vault及随机高端口。
- UI零问题、58组对比度达标；归档文档检查160份、零问题、3条既有体积提醒。`visual-check.py` 按基线 `f33f6f7` 实跑浅深色桌面与手机4档，桌面差异0.012%/0.011%，查看差异图确认仅侧栏版本文字；手机零差异，页面审计无问题。排版面板和纸面另由导出专项截图覆盖。
- 发布预检的业务任务、恢复意图、框选操作均为零，训练锁空闲。持锁停服保全：Vault及网关1513文件、9库，框选2文件、1库，解包逐字节与SQLite完整性均通过。最终切换及核验5.171秒，三服务实际cwd指向新归档且active/running、NRestarts=0，Nginx及隧道未重启。
- 切换前后51张业务表原列原行完全一致；1313个正文/图片/SVG/关键配置哈希、网关与框选私有数据、凭据、模型、unit及控制配置保持。当前397题、0冲突。8个线上版本化资源与归档生成的响应一致，immutable、ETag304通过；主样式按AssetStore合并并改写资源后的实际输出计算哈希。
- 重跑记录如实保留：最初 `git ls-remote` 60秒网络超时，未切换；随后核对成功。第一次实际切换的检查脚本误将合并CSS响应和源文件比较，自动回退到原源码并保留当前数据；回退后再次逐表、逐文件核对完全一致。在原生产验证合并CSS校验方式，保留 `attempt-2-evidence` 的状态、备份和失败日志，修正检查脚本后再次发布成功。最终远端核对使用GitHub REST ref，未修改产品代码或跳过资源检查。
- 生产浏览器首轮在手机隐藏的侧栏上使用inner_text导致断言失败；桌面真实下载与PDF已通过。改为读取text_content后，浅深色×1440/390/320px共6档浏览器通过，脚本错误、溢出和业务写请求零；仅允许已核实只读的导出POST。真实导出1题、6条有效历史，顺序、柱高和对错标识正确，无外部网络，PDF分页一致，成功后参数记忆通过。使用归档文档、本机生产资源和真实业务读取，不宣称验证了真实PIN登录。


- 公网及鉴权8项最终全部通过；HTTPS监听地址另做6项原Host/SNI与证书验证。公网间歇性TLS断连，urllib并行核验失败后改用curl顺序有界重试，首页200、未鉴权状态/MCP/网关/框选401、网关health200、隧道就绪200、回环MCP401；MCP鉴权第2次、网关health第3次成功。失败日志、HTTP进度和最终汇总均保存，没有调整生产网络或鉴权配置。
- 最终数据核对发现验收期间一次正常API正文编辑CMT-000947，时间为2026-11-13T14:10:22Z，晚于切换完成及全部浏览器关闭。先保留快照与当前数据差异，再用只读SQLite及停服备份对照：原946条提交全部保留，仅新增该正文提交、blob和版本引用；题目投影只改对应content_hash与updated_seq，projection_meta只推进last_seq与head_hash，实际文件哈希与新Ledger一致，其它业务表、1312个受保护文件、网关及框选私有数据保持。核验脚本初版漏计updated_seq及head_hash的正常推进，补全后通过，未写或恢复生产数据。
- `final-audit.py` 最终通过：6档浏览器、8项HTTP、8个版本化资源、三服务真实cwd及状态、配置模型保全、并行正文编辑审计和错误级日志0，汇总于 `live-check.json`。原始严格快照差异断言及修正过程留在私有证据中，不将并行业务编辑误报为发布回归。

- 收尾再次复核 `git diff --name-status`，仅本任务生产事实与发布日志变化；`python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD` 与 `git diff --check` 通过，160份文档零问题、3条既有体积提醒。发布记录另行提交并推送 main；纯文档提交无需重启已核验的生产源码。

## 未执行验证

实体打印机、Windows Edge、实体手机、Obsidian客户端与真实模型供应商未验；本轮不向生产提交合成题目、反馈或审批。
