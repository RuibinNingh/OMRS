# 2026-07-24 Git 历史校准与文档治理

## 变更摘要

- 以 `HEAD=b481181` 为基线，复核 `20ce689`、`81a2922`、`7e7e6d7`、`d8d7874`、`6a4417e`、`262a256`、`b481181` 等近期提交，并用当前工作区代码、测试和配置校准 AI 文档。
- 补齐到期提醒字段和仪表盘、现代图表、难度零值显示、答案/解析忠实提取、Ledger 撤销恢复重放、A4 页脚安全区、KaTeX 与依赖边界等缺失或过时说明。
- 同步记录当前工作区已有的 Markdown 表格渲染、A4 双栏/单栏选择、题间留白参数，以及 AI 报告外部 HTTPS 材料能力；这些功能代码是任务开始前已有的未提交改动，本任务仅补齐对应文档。
- 新增根目录 `AGENTS.md`，把“开始前检查现状、按代码范围更新模块文档、每个持久化任务新增日志与索引、运行真实验证”设为仓库级完成准则。
- 修正 `pack_for_ai.bat` 的目录排除规则，使 AI 打包保留 `AI/logs/`；同时在根 `README.md` 和 `AI/README.md` 明确知识库、日志与 Git 历史的边界。

## 行为与兼容性

- 本任务没有修改 OMRS 应用运行逻辑；唯一脚本行为变化是 AI 打包现在包含任务日志。
- 当前行为以工作区代码、测试和配置为事实来源，Git 历史用于解释设计意图，AI 文档不得反向覆盖已验证行为。
- 任务开始前已经存在的未提交代码和旧日志修改均被保留，没有还原或改写。

## 修改文件

- 协作与入口：`AGENTS.md`、`README.md`、`pack_for_ai.bat`
- AI 维护规则：`AI/README.md`
- 模块说明：`AI/algorithm.md`、`AI/api.md`、`AI/data.md`、`AI/export.md`、`AI/frontend.md`、`AI/ledger.md`、`AI/optimization.md`
- 任务记录：本文件、`AI/logs/log.md`

## 验证

- `python -m unittest discover -s tests -v`：通过，9 项 `unittest` 测试全部成功。
- `python -m pytest -q tests -p no:cacheprovider --basetemp <独立临时目录>`：通过，13 项测试全部成功。
- 直接运行 `python -m pytest -q` 会尝试收集受权限保护的运行数据目录 `错题/`；这是测试收集范围问题，不是产品测试失败，因此改为显式限定 `tests/`。

## 同步过的文档

- 根准则与用户说明：`AGENTS.md`、`README.md`
- AI 总索引与维护流程：`AI/README.md`
- 算法、接口、数据、导出、前端、Ledger、优化：对应七份 `AI/*.md`
- 任务索引：`AI/logs/log.md`
