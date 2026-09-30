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

已执行 `git fetch origin main`，确认远端 `3c0df69` 是本地历史祖先；随后 `git push origin main` 成功，远端 `main` 从 `3c0df69` 快进到 `019fa4e`。`019fa4e` 是本次生产发布记录提交，运行时代码发布基线为其前一提交 `ebaaf80`；后续仅补写本节的文档提交不改变运行时代码。

## 生产部署

- 以提交 `ebaaf80` 的 `git archive` 生成 `/root/workspace/releases/omrs-ebaaf80`，共 928 个工作树文件；旧发布目录 `/root/workspace/releases/omrs-linebreaks-545b604cb25b` 保留用于代码回退。
- 切换前停止 `omrs.service` 并备份真实 Vault 到 `/root/workspace/backups/recycle/recent-changes-20260930T104035Z/vault-before.tar`；归档 SHA-256 为 `2d7efa4b64d3044cf44224c88cfdc957ae7c58173c29b41c7d525272861a1264`，旧 drop-in、前后状态、Ledger 和发布清单同目录保存。
- 替换 drop-in 后执行 `systemctl daemon-reload`、`systemctl start omrs.service`。当前服务 `active/running`，`MainPID=1696938`、`NRestarts=0`、`ExecMainStatus=0`、工作目录为新发布目录；错误级 journal 无记录。
- 生产 `/api/status` 返回 `status=ok`、`version=v2.0.0`、261 道题、workspace scan 变更 0 / 冲突 0；`/api/ledger/verify` 返回 `valid=true`、提交数 716；草稿计数为 cropping 0、review 1、done 19、discarded 7。
- 真实 Chromium 只读验收使用发布目录的 `omrs_dashboard.html` 响应绕过入口锁屏，桌面 1280×900 与手机 390×844 依次打开仪表盘、题库、即时练习、反馈录入、录入题目、展示板；12 个页面均就绪、无横向溢出、无脚本错误。录入页草稿审核均看到 Inspector / 来源入口，普通换行渲染为含 2 个 `<br>` 的单段；展示板预览唯一非 GET 请求为只读 `POST /api/export`。
- 5 个关键前端资源经 HTTP 返回并与发布目录 SHA-256 一致；生产浏览器结果保存在备份目录 `production-browser.json`，静态资源哈希在 `static-hashes.json`。

回退：恢复备份中的 `10-release.conf.before`，执行 `systemctl daemon-reload && systemctl restart omrs.service`；旧发布目录为 `/root/workspace/releases/omrs-linebreaks-545b604cb25b`。不要用 Vault 归档覆盖发布后新增数据。
