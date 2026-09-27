# 2026-09-24 文档架构优化与维护环境记录

## 变更摘要
- **前端文档分册。** `AI/frontend.md`（94KB）拆成 `AI/frontend/` 下 10 份分册，每份 7–12KB：shell、dashboard、library、qview、board-ui、review、feedback、settings、create、records。原文件改为一页索引。拆分前后逐行核对，正文没有丢失。标题去掉了编号和版本号，分册之间的 § 互指改为指向具体文件。行内版本号从 57 处降到 1 处，保留的那处是 `styles.css` 注释段的名字；历史叙述已改写成现在时。
- **速查头。** 全部模块文档加上五项速查头：职责、入口、不变量、必跑测试、相关。
- **每类信息只留一份。**
  - `AI/README.md` 删掉重复的目录树和映射表，改为「按任务找文档」表加文件索引。
  - 根 `README.md` 的 API 表换成指向 `AI/api.md` 与 `AI/routes.md` 的链接。
  - 根 `README.md` 的版本表换成「当前版本加 changelog 链接」；`changelog.md` 缺失的 7 个版本（v1.0.x、v1.1.0、v1.1.1、v1.6.0、v1.8.0、v1.12.0、v1.13.0）先迁入 changelog 末尾，再删表。
  - 「AI 协作」一节不再抄目录树，改为链接。
- **`tests/check_docs.py` 重写。** 新增以下规则：
  - 速查头必填；
  - 行内版本号每份不超过 10 处；
  - 模块文档不链接 `AI/logs/`；
  - `AI/` 内的路径引用必须真实存在；
  - 路由总表与 `server.py` 一致，且每条路由至少有一份文档说明；
  - `log.md` 与日志文件同步；
  - 文档超过 40KB 时给出提醒。
  
  另新增三个模式：`--diff [BASE]` 按 `AGENTS.md` 映射表检查「改了源码却没改文档」和「没写任务日志」；`--write-routes` 生成 `AI/routes.md`；`--write-log-index` 生成 `AI/logs/log.md`。
- **新增 `AI/routes.md`。** 自动生成，94 条精确路由加前缀分派，每条标出说明所在的文档。
- **新增 `AI/environment.md`。** 记录三类维护者的环境、Claude Code Web 的实测工具清单、探测命令、受限模式配方（基线、门禁、隔离实例、远端模拟、后台长任务、交付补丁）、已知坑和完整模式的接手流程。
- **`AGENTS.md` 更新。**
  - 开工时先读「按任务找文档」；
  - 收尾改为运行 `check_docs.py --diff`，日志索引改为脚本生成；
  - 文档写法新增第 3–6 条：速查头、40KB 上限、不链接日志、每类信息只留一份；
  - 映射表指向前端分册，并新增安全模块、`check_docs` 两行；
  - 受限模式改为指向 `AI/environment.md`；
  - 删除指向 `AI/logs/` 的死链。
- **`optimization.md`。** 记一条待办：`api.md` 超过 40KB，建议拆分册。
- **修复死链。** `inbox.md`、`optimization.md`、`omr-import.md` 中指向日志和旧 § 编号的死链已修正。

## 行为与兼容性
只改文档和文档检查脚本，不涉及运行时代码。`AI/frontend.md` 的路径保持不变，外部引用仍然有效。完整模式第一次运行 `check_docs.py` 时，如果手写的 `AI/logs/log.md` 与生成结果不同会报失败，此时运行 `--write-log-index` 并审阅 diff。

## 修改文件
- 修改：`AGENTS.md`、`README.md`、`AI/README.md`、`AI/frontend.md`、`AI/algorithm.md`、`AI/api.md`、`AI/board.md`、`AI/changelog.md`、`AI/data.md`、`AI/export.md`、`AI/inbox.md`、`AI/labels.md`、`AI/ledger.md`、`AI/omr-import.md`、`AI/optimization.md`、`AI/security.md`、`tests/check_docs.py`。
- 新增：`AI/frontend/*.md`（10 份）、`AI/routes.md`、`AI/environment.md`、本日志。

## 验证
- 正向：`python3 tests/check_docs.py --diff <导出基线>` 结果为 0 处问题、1 条提醒（`api.md` 52KB）。
- 反向（在临时副本上）：
  - 同时注入 5 类问题（缺速查头、链接日志、引用不存在的文件、新增未写文档的路由、路由表不同步），5 条全部报出，退出码 1；
  - 只改 `assets/app/domain/labels/index.js` 时，`--diff` 报出「前端分册未更新」和「缺任务日志」两条；
  - `--write-log-index` 生成的索引与日志文件一致。
- 回归：Python 单测、Node 测试全部通过，计数见交付说明。

## 同步过的文档
即上文「修改文件」中的全部文档。
