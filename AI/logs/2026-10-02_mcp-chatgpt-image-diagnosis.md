# 2026-10-02 ChatGPT 题图调用诊断与环境事实订正

## 背景

用户原话：「ChatGPT似乎还是不行,你知道原因吗?」。用户补充 ChatGPT 可以查草稿及正式题目文字、图片引用，却不能看图。本轮以 e8bc06d 为基线，执行者 Codex，完整模式；只读调查业务与生产配置，不修改工具契约、不重启服务、不创建密钥。

## 实测与结论

直接以只读 SQLite 连接查询运行记录：运动学58 在 09:11:41、09:19:09、09:22:23 UTC 的调用均为 get_question；近期亦有 get_draft、list_drafts、search_questions。唯一 get_question_image 成功记录仍是上线验收的 seq=3，用户反馈对应路径没有到达新读图工具。

从生产发布代码调用共享读题和题图领域函数，确认运动学58 的 images[0] 为运动学58-000262-q-1.png，完整解码校验通过，原件为 PNG、89648 字节。此处是领域读取实测，没有冒充本轮对该图片做过公网 SDK / ChatGPT 视觉验收。

get_question、get_draft 返回引用是现有契约；正式题图需第二步调用 get_question_image(uid, image_index)。草稿图片读取未被本批扩展。最可能的客户端原因是工具清单尚未刷新、未启用新工具或模型未选用它；本轮没有读取账户工具清单，不能在这些解释间定案，也不能据此认定 ChatGPT 不支持 ImageContent。

已使用 OpenAI Docs 技能实际获取官方 Developer Mode 页面。该页明确支持在应用详情刷新工具、描述与 instructions，启用/禁用工具，并建议明确工具名和输入顺序。参考：https://developers.openai.com/api/docs/guides/developer-mode 。官方 reference 页面说明 content 会提供给模型，但没有在本轮文档证据中验证该账户的原生图片视觉链路。

systemctl show tunnel-client-omrs.service 实测 active/running、NRestarts=0，原 AI/environment.md 的「尚未启动」不符合当前状态。相邻 Tunnel 验收报告来自 2026-10-01，仅证明当时九个只读工具；没有据旧报告臆测当前客户端仍缓存九项。

## 行为变化与影响文件

无业务行为变化。订正 AI/environment.md 的真实 Tunnel 状态；AI/mcp.md 明确独立读图调用与客户端刷新步骤；MCP progress 记录本轮证据和未验证项。新增本日志，AI/logs/log.md 按脚本生成；历史发布日志中的「本轮未联调」保留为该轮验证边界，没有重写历史。

## 验证与边界

已实际执行 Git 状态复核、官方文档获取、只读运行记录查询、指定题目安全图片读取、Tunnel 服务状态读取。未修改或重启生产，不读取密钥明文，没有新增调用记录或生产测试数据。

未重复 Python/浏览器/Node 门禁，本轮只订正文档。账户工具刷新、显式调用新工具、原生图片视觉处理与草稿原图读取均未在本轮实现或验收；前两项可由用户在 ChatGPT 应用详情及对话确认。

已执行 python3 tests/check_docs.py --write-log-index；python3 tests/check_docs.py --diff HEAD 检查 81 个文档、0 问题、3 条既有大文件提醒，退出码 0。git diff --check 通过，git diff --name-status 与未跟踪文件复核仅涉及本轮五项文档路径。文档订正独立提交并沿用本会话的 GitHub 同步授权，不切换生产 release。
