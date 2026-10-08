# 2026-10-08 区域文字提取的公式 JSON 转义修复

## 背景

执行者：Codex，完整模式。用户反馈「为什么重试很多次都失败,自己调一下马上就好,这肯定有问题」，随后要求「那怎么修复」。本次任务基线为 `71748c0`。开工时标记整理相关代码、文档和测试已有未提交修改，后续还有其它测试修改；均保留，不纳入本任务范围。

只读检查这张截图的区域和任务记录，题面裁图为 606×783，框内正文完整；题目区域连续五次报「模型未返回有效的可提取判断」，答案区域成功。使用相同裁图和实际配置的模型复现：模型返回 convertible=true 和正文，但 JSON 字符串中的数学定界符漏转义，标准解析器报 Invalid escape。原框、微调和加白边的少量对比均有成功或失败，不能把微调当成可靠解决方式；原图不变、修正输出要求即可成功。

## 行为变化

题目与答案的转录规则和输出要求分开复用；判断模式只要求一个 JSON 对象，明确布尔值、美元符号公式以及反斜杠、换行和引号的 JSON 转义，避免同时要求只输出正文。

严格 JSON 解析失败时，仅为区域提取在本地补齐四种数学定界符前缺失的反斜杠转义。已经正确转义的内容保持原样，成对的数学定界符转为现有页面支持的美元符号格式。缺失布尔判断、正文为空、其它非法转义、结构错误和截断结果仍失败；兼容不推断可提取性，不增加模型请求，不修改框位或裁图，也不放宽分类等其它解析入口。

## 影响文件

- `omrs/ai_assist.py`：分离提示词输出要求，增加区域限定的定界符转义兼容和正文格式统一。
- `tests/test_ai_region_extraction.py`：12 项回归，覆盖漏转义、合法格式保真、边界拒收与框位不变的真实收件箱写回。
- `tests/e2e/create.py`：仅替换外部模型响应，让真实解析器处理漏转义公式；浏览器核对框位不变和 KaTeX 实际渲染。
- `AI/inbox.md`、`AI/api.md`、`AI/api/extensions.md`、`AI/frontend/create.md`、`AI/frontend/architecture.md`、根 `README.md`：同步当前行为、边界及验证职责。
- 本任务日志与脚本生成的日志索引；最终按限定路径的 `git diff --name-status` 复核。

## 验证

已实际执行：

- 修复前新增回归测试能够复现漏转义导致的拒收和不能渲染的定界符；修复后 12 项全部通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests.test_ai_region_extraction tests.test_inbox tests.test_ai_assist_taxonomy tests.test_drafts tests.test_draft_p3_http tests.test_draft_p4_http tests.test_usage -q`：84 项通过。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL PYTHONDONTWRITEBYTECODE=1 python3 tests/e2e/create.py`：116/116，通过真实隔离服务、临时 Vault、随机端口和 Chromium；含四档结果态审计与 360px 触摸布局。外部模型使用固定响应，真实解析器未替换。
- 读取现有配置和裁图后直接调用真实模型，不连接生产 HTTP 接口、不修改真实收件箱：同一张原裁图连续 3 次成功，正文分别 464、465、462 字符；公式命令保留，定界符完成规范化。此小样本验证当前截图，不代表所有题图的识别质量保证。
- 限定本任务路径的 `git diff --check` 通过；`python3 tests/check_docs.py --write-log-index` 已生成索引。
- `python3 tests/check_docs.py --diff HEAD`：整工作区检查退出 1，发现两处其它任务的前端文档尚未同步，分别为整批标记预览与助手审核卡片，不属于本次修复。为保留其它任务修改，使用临时 Git 索引把 25 个非本任务路径的现有改动固化为树基线，未修改正常索引或分支；`python3 tests/check_docs.py --diff 148dac0e9d90e7ccece9d288cf48defe316a6718`：检查 105 个文档，0 处问题、2 条既有文件大小提醒，退出 0。

未执行：全仓单测、其它页面浏览器和版面视觉差分；本次只改提取后端与回归测试，没有修改页面资源或样式，已验证受影响的真实录入路径。没有生产部署、重启服务、推送或修改真实业务数据；生产运行固定发布目录，修复须经单独授权部署后生效。

## 下一步

本地修复与相关验证完成。生产部署须遵守根 `AGENTS.md`「完整模式」的单独授权要求；上线后原框直接重新提取，不需要手动微调。真实识别仍须人工核对公式与文字。
