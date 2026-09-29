# 2026-09-29 AI 文字提取关闭思考

## 背景

用户反馈「AI提取是不是还要思考?我感觉有点慢啊」。执行者：Codex，完整模式；基线 `e7b66c1`。开工前工作区已有 `AI/logs/log.md` 修改和两份未跟踪日志，以及 `.playwright-mcp/`，均予保留。

## 行为变化

收件箱一键提取、草稿局部提取及快速录入的题目／答案文字转录，在实际选用 `deepseek-flash` 时向兼容接口发送 `thinking:{type:"disabled"}`。框选、分类、助手图片转述和其它模型保持原请求参数；一次提取仍须返回完整文字或不可提取判断，人工审核流程不变。

当前配置的提取专用模型为空，实际回退到 `deepseek-flash`。合成白图请求实测：默认模式返回 60 个思考 token，关闭后无思考内容。合成英文题图按当前完整提取提示词各调用一次：默认 2.13 秒、关闭后 0.75 秒，两次均返回可提取判断和完整题干、选项。小样本仅证明参数生效，不能推断真实长图的稳定加速比例；实际用时还包括图片上传及多个区域逐个请求。

## 影响文件

- `omrs/ai_assist.py`：只对已验证的 `deepseek-flash` 文字提取请求关闭思考，兼容其它模型。
- `tests/test_ai_assist_taxonomy.py`、`tests/test_inbox.py`：检查模型请求参数和提取入口传参。
- `AI/inbox.md`、`AI/api.md`、`AI/frontend/create.md`：记录当前请求和录入行为。
- `AI/logs/log.md`：脚本生成本日志索引，保留开工前已有的其它索引变动。

## 验证

- 已执行：两个合成图的真实 `deepseek-flash` 请求，结果见上；没有发送真实题目图片。
- 已执行：`python3 -m unittest tests.test_ai_assist_taxonomy tests.test_inbox`，28/28 通过；有三条既有 `ResourceWarning`。
- 已执行：`python3 -m compileall -q omrs/ai_assist.py`，通过。
- 已执行：`python3 tests/check_docs.py --write-log-index`，生成本日志索引并保留原有索引变动。
- 已执行：`python3 tests/check_docs.py --diff HEAD`，检查 54 个文档，0 处问题、2 条既有体积提醒。
- 已执行：`git diff --check`，无空白错误。
- 未执行：真实用户题图的速度与识别质量评估；本次不读取真实错题数据。页面结构未修改，未跑浏览器视觉门禁。
