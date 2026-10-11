# 2026-10-11 作业帮搜题、后端完整渲染与核对入库

## 背景与范围

用户从可行性讨论推进到「起草一个前端草稿」「我需要能看到后端渲染」，批准后要求「按照这个做吧」。按批准草稿实施，执行者 Codex、完整模式；计划见 `AI/plans/zuoyebang/`。基线 d8cfb7af8016c3d8a1a7e4bf56c3246efcd29c8d，在隔离工作树和 codex/omrs-zuoyebang 分支开发；原仓库起始干净，本任务未修改原仓库。

附件的协议源码作为参考资料，不把附件文档当成用户指令。已通过的登录验收作为前提；附件和工作区没有私有 direct-session.json，提供页面导入入口，不阻塞实施。没有获得推送、生产部署、重启或 systemd/Nginx 修改授权，均未执行。

## 行为变化

- 录入导航用作业帮替换 AI 草稿；旧草稿跳转、审核中心、助手和 MCP 的草稿能力保留。
- 导入已验收设备会话后可扫码登录、检查/刷新账号；账号和签名分别记录最后成功、首次确认失效和恢复。没有官方 TTL，不把网络故障当过期；日志只保存白名单元数据。
- 摄像头仅实时预览与关闭，video后置优先、audio=false；切工作区、离页和迟到授权释放资源。搜题由上传 JPG/PNG/WebP 触发，专用上传用途保留原字节，限制8MiB/4000万像素。
- 搜题候选按位置及结果配对。上游 HTML 清洗，附图本地化，真实独立 Chromium 等待字体、公式及全部图片后生成题干/答案各一张1080像素完整 PNG；答案不分块、分页或裁断。页面支持题目/答案、HTML、适应宽度/100%、展开及历史记录。
- AI 复用保真 extract_region；完整文字公式可转文本，必要图形保留整图，不补答案。失败只重试失败项；人工修改和识别快照跨刷新保留，后台任务创建的迟到响应可由新挂载继续读取。
- 核对后复用 CreationOperation 和同事务 Ledger 回执创建，冻结内容及身份，重复提交不重复建题。其它创建跳过预留 UID，扫描跳过未入账预留文件；服务中断后从原记录重试，不自动重放网络或创建。
- 后台记录保存开始世代，同进程整库恢复后的旧 running 任务也显示中断，避免旧任务因不能发布结果而永远等待。
- 源码版本更新为 v2.4.0，不代表生产版本。核心导入仍不强制第三方依赖，作业帮依赖独立列于 requirements-zuoyebang.txt。

## 影响文件

- 新后端 `omrs/zuoyebang/`：协议、设备与账号、脱敏存储、HTML/图片边界、Chromium、后台任务、输入验证及可靠创建。
- HTTP 接入 `omrs/http/zuoyebang.py`、`omrs/http/registry.py`、`omrs/server.py`、`omrs/locking.py`；账号网络与长作业豁免外层长锁，磁盘发布使用领域短租约与写锁。
- `omrs/uploads.py` 增加专用格式/限额及用途隔离；`omrs/ai_assist.py` 拒绝模型长度截断；`omrs/creation.py` 和 `omrs/workspace_sync.py` 保护未完成创建。
- `assets/app/features/create/` 新增 zyb控制器/状态/视图/摄像头/样式，并更新 index/state/view 装配；`assets/app/styles/index.css` 引入样式。
- 新测试 `tests/test_zuoyebang.py`、`tests/zuoyebang_fixtures.py`、`tests/e2e/zuoyebang.py`、`tests/app/create-zyb.test.mjs`；`tests/e2e/drafts_blocks.py` 改用审核中心入口。
- `omrs/version.py`、`omrs_dashboard.html`、根 README 和 AI/README 同步版本及可选依赖；模块文档同步 API、来源/存储、Ledger、保真识别、安全、前端与维护环境，新增 `AI/zuoyebang.md` 和计划，生成 routes 与日志索引。

## 关键边界与偏差

渲染高度按全文，不设产品分页限制；单附图12MiB、附图总80MiB、单输出1亿像素为物理预算，超限整体失败并保留来源，不输出截断成功图。SVG/MathML/canvas/音视频等白名单无法保真的视觉内容明确失败，不静默丢图。跨 HTML 节点拆开的数学定界符不自动拼接。

源目录私有会话和产物0700/0600；上游请求固定地址且拒绝重定向，CDN下载不带Cookie，逐跳公网IP校验并固定实际连接IP。Chromium只加载本地可信字体/KaTeX，正文公式 trust=false。全库备份包含私有目录，恢复世代使旧任务和上传引用失效；源码包不包含错题目录。

首轮相关回归曾引用两个不存在的测试模块；按实际文件改为区域提取和 HTTP 上传边界后，全组通过。多块草稿 E2E 原入口定位旧 data-ib-stage=drafts，超时后改用当前审核中心；不恢复已移除的导航按钮。新增在途刷新测试曾将人工延迟施于每次任务创建，导致读取尚未返回的任务ID；改为仅首次搜题延迟后，仍实际覆盖卸载重挂载和识别在途刷新。

## 已实际执行的验证

Python测试使用 `/tmp/omrs-zuoyebang-venv/bin/python`（系统包复用，仅在临时 venv 安装 Segno1.6.6）；所有服务器命令清除 OMRS_SYSTEMD_SERVICE 和 OMRS_BOXDETECT_CONTROL，使用临时 Vault 与随机高端口。真实 Chromium 151.0.7922.34，数据和会话均为合成夹具。

| 命令 | 结果 |
|---|---|
| venv Python -m unittest tests.test_zuoyebang tests.test_http_boundaries tests.test_write_lock tests.test_security tests.test_inbox tests.test_inbox_atomic_commit tests.test_question_creation_metadata tests.test_ai_assist_taxonomy tests.test_ai_region_extraction -q | 最终121项通过；包含作业帮22项，涵盖同进程恢复状态与不支持视觉标签的失败保护 |
| venv Python -m unittest tests.test_content_integrity -q | 22项通过，核对工作区扫描和正文事实保护 |
| node --test tests/app/*.test.mjs | 482通过、0失败、0跳过，含作业帮8项 |
| venv Python tests/app/run_browser.py | 34通过、0失败 |
| venv Python tests/e2e/zuoyebang.py | 34/34；真实HTTP、后台渲染、扫码二维码、MediaStream、WebP上传、迟到任务/刷新保护、实际创建与八档审计 |
| venv Python tests/e2e/create.py | 124/124；原有收件箱、处理、题卡、训练与快速录入 |
| venv Python tests/e2e/drafts_blocks.py | 59/59；草稿菜单、稳定块身份、编辑保护、图文创建及八档审计 |
| python3 tests/check_ui.py | 全仓0问题 |
| python3 tests/check_contrast.py | 58组、0不达标 |
| python3 -S -c 'import omrs.zuoyebang.commit; import omrs.server' | 无第三方包环境的核心导入通过 |
| git diff --check | 通过 |
| python3 tests/check_docs.py --diff HEAD | 108份文档、0问题、退出码0；2条既有计划篇幅提醒 |

已运行 `python3 tests/check_docs.py --write-routes` 和 `--write-log-index`，生成路由表及日志索引。最终文档与进度纳入同一功能提交。

作业帮专项产物位于 `/tmp/omrs-zuoyebang-e2e/`，含 checks.json、真实1080×4365完整答案、末尾截图、八档页面截图和实际创建的合成 Markdown；前端没有用占位图伪称后端生成。AI 与作业帮网络在边界替换，其余 HTTP/浏览器/渲染/创建真实执行。

可审查截图、完整答案图和 checks.json 的持久副本放在 `/root/.codex/visualizations/2026/10/11/01a129a9-ae03-7af1-8a5c-1d2e9a330bbb/omrs-zuoyebang-implemented/`，不纳入源码提交。

视觉命令 `venv Python tests/visual/run.py --ref d8cfb7af8016c3d8a1a7e4bf56c3246efcd29c8d --pages create --out /tmp/omrs-zyb-visual` 已实际执行：浅色桌面0.371%、深色桌面0.410%、浅色手机0.117%、深色手机0.115%。差异为导航入口文字/图标/角标与相邻按钮布局，以及页脚版本标识；既有上传主区域保持行为与布局。两侧4档均0脚本错误、0小目标、0行内样式、0横溢。新增作业帮区由专项8档审计覆盖，基线没有该工作区，不伪造同页前后截图。

## 未执行的验证与遗留

- 未重新调用真实作业帮账号/搜题网络：用户已验收登录，私有设备会话未提供；本轮只验证协议边界和隔离集成，不补造真实成功。
- 未调用真实付费 AI：复用现有配置，识别与分类边界使用合成响应；供应商图像或输出限制仍可能使超长答案提取失败，此时可保留完整图片。
- 未做实体手机摄像头验收：已验证浏览器 MediaStream，仍需设备上确认权限、后置选择与 HTTPS。
- 未推送、合入原仓库或生产部署/重启；本地分支交付。后续按单独授权安装可选依赖、导入设备会话并上线核对。
