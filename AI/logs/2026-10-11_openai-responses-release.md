# 2026-10-11 Responses 生产部署

## 授权与范围

用户原话：「部署一下生产我测试」。执行者：Codex，完整模式。开工main为 `1c745214e73454dcb761890019ec26132f7dac63`，工作区干净。本轮发布上一任务已完成的OpenAI Responses适配，版本保持v2.3.9；授权覆盖生产目录切换和主服务重启，未推送。上一实施日志中的「未部署」保留为当时事实。

生产原服务运行精确提交 `716426f`，真实Vault为 `/root/workspace/apps/OMRS`；unit使用持久别名 `/root/workspace/apps/releases/omrs-9b29d49`，开工指向 `omrs-716426f`。本轮实测 `/etc` 所在根挂载为rw，沿用既有发布指针而不修改服务配置。未修改生产模型、PIN或MCP Key权限，没有发送真实模型请求或执行生产业务工具。

## 发布源码与实际验证

候选 `/root/workspace/apps/releases/omrs-1c74521` 来自精确提交的 `git archive`，1,294个源码文件逐字节核验。`.venv`相对链接复用既有生产依赖：Python3.13.5、MCP1.28.1、Pillow12.3.0、Playwright1.62.0，没有安装或升级依赖。

`python3 /tmp/omrs-responses-release-20261011/validate-release.py` 在该release与生产venv实跑4/4组，全部退出0，无跳过：

| 实际命令（python使用release的 `.venv/bin/python`） | 结果 |
| --- | --- |
| `python -m unittest tests.test_llm_responses tests.test_agent_loop tests.test_usage tests.test_asset_cache tests.test_web_assets -q` | 49项，21.404秒，通过 |
| `python -u tests/e2e/assistant_responses.py` | 13/13通过；真实Chromium、临时OMRS、合成HTTP供应商，含连接探测、图片、工具续轮、加密推理、上下文重读和双宽度 |
| `python -u tests/e2e/assistant.py` | 59/59通过；原助手、中止、确认、图片与窄屏 |
| `python -u tests/e2e/settings.py` | 71/71通过；设置保存及双主题双宽度审计 |

所有业务测试仅访问临时Vault、随机端口；验证脚本移除 `OMRS_SYSTEMD_SERVICE`、`OMRS_BOXDETECT_CONTROL` 和 `OMRS_AGENT_FAUX_SCRIPT`，原助手脚本自行指定其合成模型。完整命令、原始输出和耗时存入私密保全。上一实施提交的全仓885项等门禁未在部署轮重跑，不计为本轮实跑。

## 首次切换与历史导入核查

首次备份位于 `/root/workspace/apps/releases/OMRS-responses-release-20261011T042910Z-3h2gvi_2`。候选启动后的严格整表摘要核验发现 `ai_review.db/operations` 从129行变为132行，脚本自动恢复旧源码指针并启动旧服务；没有恢复旧Vault。立即核对旧服务active/running、实际cwd、题数299、冲突0、待审0；正文、图片、关键配置及控制指纹保持，相邻服务没有变化。

通过只读副本逐行比较：原129条操作所有字段保持，追加的3条均为失败的 `propose_question_update` MCP历史，history_readonly/history_incomplete均为1。新增稳定身份、工具、参数、结果和来源actor全部匹配停服备份中早已存在的runtime记录，没有新增题目提交或重放业务。

当前及旧源码的 `ai_review.initialize` 在监听前调用 `_import_mcp`，通过 `INSERT OR IGNORE` 补录未入审核库的历史；该行为与 `AI/ai-review.md` §5一致，相关源码在此次协议适配中未改动。首次失败属于发布核验未区分合法历史追加；未放宽最终业务表检查。保留首次备份及核查证据后，以已补录的当前事实重新停服备份，复用逐字节复核后仍相同的候选和已通过的4组门禁，进行第二次切换。

## 最终部署与保全

最终保全 `/root/workspace/apps/releases/OMRS-responses-release-retry-20261011T043300Z-tpecshr1`，目录0700、文件0600。包含精确新旧源码tar、unit/drop-in与真实Nginx/模型控制配置、一致Vault/maintenance tar、私人数据库/文件摘要、验证脚本、原始门禁输出及生产入口截图。停服tar与原目录比较通过，独立解包992个文件逐字节核对，副本SQLite完整性通过。递归SHA256清单与权限核验通过。

2026-10-11 12:33:11 CST最终成功切换；停主服务、备份、原子替换相对发布链接至就绪2.578秒。持久别名指向 `omrs-1c74521`，主服务PID325805、active/running、NRestarts=0，实际cwd和启动脚本路径核对通过。unit/drop-in字节保持，无需daemon-reload。失败处理仅恢复旧源码链接并启动服务，绝不以旧Vault覆盖当前事实。

最终严格核对49张业务表、935个内容/关键配置文件、89个实际控制文件/模型指针全部保持；299题、0冲突、待审0。Tunnel PID875442、检测服务PID1532134及Nginx状态保持，未重启相邻服务。原源码 `omrs-716426f`、更旧目录以及全部历史保全仍保留。

## 上线只读验收

`/root/workspace/apps/releases/omrs-1c74521/.venv/bin/python -u /tmp/omrs-responses-release-20261011/read-live.py` 退出0：

- 设置模块 `assets/app/features/settings/agent-view.js` 与 `assets/app/main.js` 本机HTTP200，gzip解压与release字节一致；资源指纹变化、immutable缓存和ETag304通过，公网匿名资源401。
- 设置源码含「OpenAI（Responses）」，精确源码构造的OpenAI客户端为ResponsesClient，构造核对使用合成参数且不访问模型。
- 公网 `https://home.ruibin-ningh.top:8472` 入口及授权摘要200，匿名status/MCP401，回环MCP无Key401；现有鉴权边界保持。
- 本机与公网390px真实浏览器PIN入口无横向溢出、无脚本错误；没有输入PIN或进入生产工作台。
- 启动以来错误级journal为空；验收后再次核对源码、PID/cwd、业务表、文件和控制指纹通过。

## 仓库收尾与未执行项

本轮仓库持久化范围为 `AI/environment.md`、本日志及生成的 `AI/logs/log.md`，同步当前生产事实及发布核验配方。源码pin保持 `1c74521`，纯文档收尾不再次重启服务。已执行 `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD` 与 `git diff --check`：105份文档、0问题、2条既有计划大小提醒，退出0。两份保全分别24/21个递归文件SHA256通过、目录0700及文件0600通过；仅本轮三条路径纳入本地收尾提交。

未执行：真实供应商模型调用、生产PIN登录后的业务写、Windows或实体手机、全仓Python/Node/组件重跑与无关页面E2E。生产以精确源码、资源、隔离真实浏览器主路径和只读业务核对验收，真实模型由用户测试。

## 下一步

用户刷新生产页面，在「设置 → AI助手」选择「OpenAI（Responses）」并保存后测试。保留新旧源码和两份保全；任何后续发布仍先检查活动任务、恢复journal、发布别名和实际源码。
