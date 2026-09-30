# 2026-09-30 最近修改调查、GitHub 合入与生产更新

## 背景

用户原话：「调查最近全部修改然后提交GitHub
同时更新生产到最新版本」。本次由 Codex 在完整模式执行。开工时 `main` 比 `origin/main` 超前 4 个提交，工作区另有 AI 草稿审核台、答案块边界、Markdown 普通换行兼容三组未提交改动；`.playwright-mcp/` 为本机浏览器记录，保留但不纳入提交和生产。

## 调查结果

- `origin/main..main` 的 4 个提交为手机版题目详情滚动、展示板动效设置、题目创建时间排序、题目创建信息与助手检索增强，均已存在本地 `main`。
- 工作区未提交源码与文档改动集中在三项：AI 草稿审核台桌面 Inspector / 来源工作区与移动端标签；答案无图片时合并为单一文字块；题目 Markdown 默认保留普通换行并同步导出与助手卡片。
- 当前生产在切换前运行 `/root/workspace/releases/omrs-linebreaks-545b604cb25b`，版本 `v2.0.0`，261 道题，workspace scan 变更 0、冲突 0；它只包含换行兼容切片。

## 行为变化

最终发布包含上述 4 个本地提交及工作区三项改动。生产继续使用真实 Vault `/root/workspace/apps/OMRS`、8471 端口、Nginx 和现有检测服务；新增行为见对应主题日志 `2026-09-30_ai-draft-ui.md`、`2026-09-30_answer-blocks.md`、`2026-09-30_markdown-linebreaks.md`。

## 影响文件

- 前端：`assets/app/domain/question/`、`assets/app/features/assistant/`、`assets/app/features/create/`、`assets/app/features/questions/`、导出模板 CSS。
- AI 草稿：`omrs/agent/prompts/system.md`、`omrs/agent/tools/drafts.py` 及对应 Node / Python / E2E 测试。
- 文档与记录：相关 `AI/*.md`、`README.md`、三份主题日志及本日志；`AI/logs/log.md` 由脚本生成。
- 本次没有纳入 `.playwright-mcp/` 未跟踪浏览器记录，也没有修改真实 Vault 数据文件。

## 验证

已实际执行：

- `python3 tests/check_ui.py`：0 处问题。
- `python3 tests/check_contrast.py`：58/58 通过。
- `python3 tests/check_docs.py --diff HEAD`：0 处问题，3 条既有大文件提醒。
- `python3 tests/app/run_browser.py`：34/34 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test*.py' -q`：417/417 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/drafts.py`：56/56 通过。
- 定向 `tests.test_agent_draft_tools` 与 `tests.test_report_export`：16/16 通过。
- `node --test tests/app/*.test.mjs`：394 项中 393 项通过；唯一失败是既有 `core.test.mjs` 的 `undefinedundefined#/board` 测试环境断言。

未完成或需记录：首次草稿 E2E 因列表异步刷新竞态超时，复跑已 56/56 通过；视觉脚本首轮在路由初始化前读取 `window.__omrs` 失败，需用真实浏览器 E2E 截图审计结果作为本次草稿页面验收依据。

## GitHub 推送

待最终提交、门禁和远端快进确认后补写提交哈希、远端指针及推送结果。

## 生产部署

待最终提交后补写发布目录、生产备份、systemd 切换、只读接口 / 浏览器验收和回退路径。
