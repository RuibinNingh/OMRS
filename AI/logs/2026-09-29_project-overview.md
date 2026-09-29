# 2026-09-29 项目整体情况梳理与文档校正

## 背景

用户要求“整理OMRS项目整体情况”。Codex 以完整模式检查当前 `main` 工作区、代码入口、数据流、五份计划、近期任务日志和只读服务状态，基线为 `0478941`。开工前工作区的跟踪文件无改动；原有未跟踪的 `.playwright-mcp/` 文件保留。

## 行为变化

无产品行为变化。本轮将已与代码不符的概况文档改成可验证的当前行为：HTTP 服务已按连接开线程并用进程写锁串行持久化写入；主界面已是原生 ES Module，旧经典脚本和样式层已删除；Ledger 负责题目、学习和 Session 的核心状态，展示板、助手、草稿、收件箱与标注有独立存储；已入账的题目 Markdown 正文可从 blobs 取回，活动题可显式还原。

前端重构 P0–P8 与展示板改版已完成；AI 助手和 AI 草稿已合入、部署；框选训练面板与服务管理已部署，但新候选模型未达到替换旧 640 模型的条件。对应计划的过时状态块已校正，未改写历史执行记录。

## 影响文件

- `README.md`、`AI/README.md`、`AI/data.md`、`AI/ledger.md`、`AI/optimization.md`：校正项目结构、数据事实源、正文历史和当前技术债。
- `AI/frontend.md`、`AI/frontend/architecture.md`、`AI/frontend/components.md`、`AI/frontend/design-system.md`、`AI/frontend/shell.md`：校正 P8 后的加载链、组件、样式层、页面和测试规则。
- `AI/plans/ai-agent/progress.md`、`AI/plans/frontend-rearch/progress.md`：同步已完成的合入与部署状态，保留未见完成记录的验收项。
- `AI/routes.md`：文档新增了正文版本接口的说明引用，按脚本重新生成路由到文档的映射；路由代码未变。
- 本日志和自动生成的 `AI/logs/log.md`：记录本次校正及验证。

## 已执行验证

- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：349/349 通过。测试过程有 `ResourceWarning`，并在主动断开连接的并发用例中输出 `BrokenPipeError`；退出码为 0。
- `env -u OMRS_SYSTEMD_SERVICE python3 -m pytest tests/test_report_export.py -q`：6/6 通过，补跑了 `unittest` 不收集的 pytest 风格用例。
- `node --test tests/app/*.test.mjs`：368/368 通过。
- `python3 tests/check_ui.py`：五项违规计数均为 0；`python3 tests/check_contrast.py`：58/58 通过。
- `systemctl is-active omrs.service` 与 `systemctl show`：只读检查结果为 `active/running`、`NRestarts=0`、`ExecMainStatus=0`；drop-in 指向发布目录 `omrs-e339183`。`git diff e339183 HEAD` 仅涉及文档，当前主分支应用代码与该发布版本一致。
- `python3 tests/check_docs.py --write-routes`、`python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff HEAD` 与 `git diff --check`：索引已生成；文档门禁检查 54 份，0 处问题、2 条既有体积提醒；差异空白检查通过。

## 未执行验证与边界

本轮只修改文档，未重跑页面 E2E、视觉对比或实体打印；最近的浏览器验收记录见对应发布日志。本次没有读取真实题库内容、操作生产服务、部署或推送。文档检查既有两条体积提醒：`AI/api.md` 约 66KB、前端重构旧执行说明约 48KB；本次不拆分。

## 收尾结果

本次只提交文档校正、任务日志与生成索引；原有 `.playwright-mcp/` 未跟踪文件保持原样。应用代码与生产配置没有改动。
