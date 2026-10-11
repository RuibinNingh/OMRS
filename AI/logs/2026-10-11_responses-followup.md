# 2026-10-11 Responses 测试反馈修复

## 背景

用户反馈「看不到思考摘要是吗」，截图问「这是什么情况」，随后补充「除此之外还有问题,似乎不会复用缓存」「MD标题不会渲染」。执行者：Codex，完整模式；代码基线 `d529689`，开工工作区干净。沿用本会话「部署一下生产我测试」的上线授权，修复同一功能测试反馈；不推送远端，版本保持 v2.3.9。

## 定位与行为变化

- 摘要：请求缺少主动开启参数；现在发 `reasoning.summary=auto`，不调整推理强度。已知非推理型号略过；不支持摘要的模型别名/网关可通过布尔兼容开关关闭。
- 工具：截图运行前 15 次调用完成，最后一轮只留下 10 个工具参数步骤，没有实际执行。合成 SSE 复现终态 `output:[]` 清空完整项并误判 stop；未抓取该次上游原始结束包，不能宣称生产原包已取证。现在终态无输出时恢复 `output_item.done`，未完成项或遗漏的工具调用明确报错，保留截断/失败/中止时不执行工具的边界。
- 缓存：生产用量里 cached_tokens 明确为零，不是前端漏读。运行时加载历史时过滤了 `_response_items`，丢失加密推理并改变前缀；现在保留并由 Responses 客户端展开。同一 Vault/对话/模型使用哈希缓存键，跨轮次、消息及重启稳定，不暴露路径或密钥。实际命中仍由供应商决定，不把零改为估算命中。
- Markdown：补齐六级井号标题、下划线标题和现有字号层级；标题内仍支持内联转义与引用。围栏代码按源码显示，避免其中井号误成标题；对话摘要去掉标题标记，兼容 CRLF。

## 影响文件

后端：`omrs/llm/responses.py`、`omrs/llm/compat.py`、`omrs/agent/config.py`、`omrs/agent/runtime.py`。前端：`assets/app/features/assistant/md.js`、`assets/app/features/assistant/assistant-run.css`。回归：`tests/test_llm_responses.py`、`tests/app/assistant.test.mjs`、`tests/e2e/assistant_responses.py`。同步说明：`AI/agent.md`、`AI/api.md`、`AI/api/queries.md`、`AI/data.md`、`AI/frontend/assistant.md`、`AI/frontend/architecture.md`、根 `README.md`；日志索引由脚本生成。

## 已实际执行的验证

- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 -m unittest tests.test_llm_responses tests.test_agent_loop tests.test_usage tests.test_agent_images -q`：51/51 通过，无跳过。
- `node --test tests/app/*.test.mjs`：457/457 通过，无跳过。新增标题测试第一次发现 CRLF 解析遗漏及转义预期错误，已修正并通过全量 Node 门禁。
- `python3 tests/check_ui.py`：0 问题；`python3 tests/check_contrast.py`：58/58 达标。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/app/run_browser.py`：34/34 通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL OMRS_RESPONSES_SCREENSHOTS=/tmp/omrs-responses-followup-ui python3 tests/e2e/assistant_responses.py`：24/24 通过。真实 Chromium、临时 Vault、随机端口、合成 HTTP 供应商；校验摘要 opt-in、空终态继续执行、标题 DOM、缓存回执统计、刷新及下一次消息的完整前缀、原生上下文持久化、双主题和 1440/390px 布局，无页面脚本错误。首批截图发现缩窄时仍在抽屉退场动画中，改用 reduced-motion 并等待抽屉隐藏、滚动到标题；新增真实可见且无遮挡的断言后重跑通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL python3 tests/visual/run.py --ref d529689 --pages assistant --out /tmp/omrs-responses-followup-visual`：4 组截图，0 差异、无脚本错误。此夹具为助手欢迎页；实际回答标题另有前述 E2E 的 4 张双主题/宽度截图。
- 已用 `git diff --name-status`、`git diff --stat` 和 `git diff --check` 复核实际改动；`python3 tests/check_docs.py --write-log-index` 已生成索引，`python3 tests/check_docs.py --diff HEAD` 检查 105 份文档，0 问题；2 条提醒为已有大计划文件。

## 发布及只读验收

- 实现提交：`f3b94bcfd342744c0a893adfe2f77b0bddab6507`。精确归档 `/root/workspace/apps/releases/omrs-f3b94bc`，1,296 个源码文件逐字节核验，复用既有生产 `.venv`；运行源码 pin 与部署文档提交分开，版本保持 v2.3.9，未推送远端。
- 在精确 release 和生产依赖下运行 `/tmp/omrs-responses-followup-release-20261011/validate-release.py`，4/4 组通过、无跳过：后端 68/68（Responses、循环、附图、用量、资源缓存）；Responses 闭环 24/24；原助手 59/59；设置页 71/71。全用临时 Vault/随机端口，清除生产控制环境变量，不调用真实付费模型。
- 本轮保全目录 `/root/workspace/apps/releases/OMRS-responses-followup-release-20261011T045621Z-0kfpba3p`（目录0700、文件0600），包括新旧源码、控制配置、停服后一致 Vault/maintenance tar、私人表/文件摘要、门禁和只读验收证据；tar 与原目录比较通过，992 个解包文件一致，副本 SQLite 完整性通过。
- 上线前核对各后台库活跃任务与等待确认均为零，恢复/正式改题/标记意图为空。只切换持久别名 `omrs-9b29d49` 并重启主服务。2026-10-11 12:58 CST 完成，至就绪 3.195 秒；主服务 PID399122，actual cwd 指向精确 release，active/running、NRestarts=0。
- 以本轮停服新基线核对：49 张业务表、935 个内容/关键配置文件、89 个控制文件/模型指针均保持；299 题、0 冲突、待审0。Tunnel/检测/Nginx 的 PID 和状态不变，未重启相邻服务；启动后错误级 journal 无记录。旧源码及全部既有保全继续保留；失败回退只恢复兼容源码指针，不恢复旧 Vault。
- `/tmp/omrs-responses-followup-release-20261011/read-live.py` 在生产依赖下只读验收通过：Markdown脚本、助手运行样式和main模块HTTP200，gzip解压字节与release一致，immutable与304通过，公网匿名资源401。客户端构造静态核对摘要、对话缓存键和运行时原生上下文保留；不发送模型请求。公网入口/授权摘要200，匿名status/MCP401，回环MCP无Key401。本机及公网真实浏览器390px PIN入口无横溢、无脚本错误，未输入PIN。

## 未执行与下一步

生产模型的摘要内容、真实缓存命中、PIN后工作台、Windows及实体手机未验证；隔离测试使用合成供应商，生产验收只读，不把合成 cached_tokens 当作生产证明。已完成实现与发布，下一步由用户刷新页面继续生产测试，按上游真实回执核对摘要及缓存命中。
