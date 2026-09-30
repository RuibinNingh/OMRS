# 2026-09-30 AI 答案块边界

## 背景
用户反馈 AI 草稿最近又把纯文字答案拆成多个块，要求只有答案文字被图片隔开时才拆分。运行模式为 Codex 完整模式；工作区原有 `omrs/server.py`、入口页资源和前端路由的未提交改动保留，不属于本任务。

## 行为变化
提示词明确答案块规则：没有图片的答案必须只有一个文字块，步骤、公式和段落用换行保存；只有图片夹在答案文字中间时才按图片处分块。`create_draft` 工具会合并连续的答案文字块，避免模型按段落拆块；图片前后的文字仍按阅读顺序保留独立块。

## 影响文件
- `omrs/agent/prompts/system.md`：补充答案分块硬规则。
- `omrs/agent/tools/drafts.py`：创建草稿前合并连续答案文字块。
- `tests/test_agent_draft_tools.py`：覆盖纯文字答案合并和图片隔开时保留分块。
- `AI/agent.md`、`AI/drafts.md`：同步助手与草稿块契约。

## 验证
已实际执行：
- `python3 -m unittest tests.test_agent_draft_tools -q`：16/16 通过。
- `python3 -m unittest tests.test_agent_draft_tools tests.test_drafts -q`：36/36 通过。
- `python3 tests/check_docs.py`：0 处问题，3 条既有体量提醒。
- `python3 tests/check_docs.py --write-log-index`：通过并更新索引。
- `git diff --check`：通过。
- `python3 -m unittest discover -s tests -p 'test*.py' -q`：410 项中 409 项通过；唯一失败是既有未提交入口页改动使 `test_lock_screen_is_the_first_page_and_unlocked_dashboard_stays_guarded` 仍检查旧的「输入 4–12 位 PIN」文案，与本任务无关。
- `python3 tests/e2e/assistant.py`：38/39 通过；唯一失败发生在既有入口页 / 路由改动导致设置页导航等待超时，答案草稿路径的「纯文字草稿保留指定来源截图」检查通过。
- `python3 tests/check_docs.py --diff HEAD`：唯一问题是同一份既有 `omrs/server.py` 入口页改动触发 `AI/api.md / AI/data.md` 映射提醒；本任务没有修改该文件，工作区原改动已保留。
- 以临时基线 `19b306c995eb74e7acee3615a1d9815d327e2841`（包含上述既有 `omrs/server.py` 改动）执行 `python3 tests/check_docs.py --diff`：0 处问题，3 条既有体量提醒。
