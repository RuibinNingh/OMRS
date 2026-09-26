# 2026-09-24 前端重构 P0：设计 token 与门禁

---

## 基本信息

| 项 | 值 |
|---|---|
| 版本 | v1.19.0 → v1.19.1 |
| 执行者 / 模式 | Claude Code Web / 受限模式（用户声明"你是 Claude Code Web"） |
| 基线 | 导出包 `OMRS-source-sanitized-20260924T154156Z.zip`，本地基线提交 `6ac228e` |
| 用户原话 | "重设计一个前端架构，让 CCW 能进行修改的同时，提升可维护性，还有实现 UI 的精致化打磨"；"开始 P0"；"继续，到时候生成的文档记得是交接的" |
| 计划 | 前端重构计划 P0（计划文件随上一轮交付，不在仓库内） |

## 行为变化

1. **设计 token 集中管理。** 新建 `assets/app/styles/tokens.css`，结构为三段：
   - 语义 token：`--surface-*`、`--fg-*`、`--border-*`、强调色、四种状态色及其 `-soft`/`-fg`/`-rgb`、焦点环、阴影层级。
   - 尺度 token：字号、行高、字重、间距、控件高度、圆角、动效、层级。
   - 旧名别名：`--bg`、`--fg2`、`--red` 等继续可用，指向语义 token。

   `styles.css` 顶部原有的 4 个 token 块删除；`omrs_dashboard.html` 在 `styles.css` 之前加载 `tokens.css`。
2. **浅色主题对比度修正**（深色主题未改）：

   | token | 修改 | 对比度 |
   |---|---|---|
   | 辅助文字 | `#8b9198` → `#6b7178` | 在白底上 3.18 → 4.93 |
   | 绿 | `#16a34a` → `#15803d` | 3.30 → 5.02 |
   | 黄 | `#ca8a04` → `#a16207` | 2.94 → 4.92 |
   | 红 | `#dc2626` → `#d02020` | 在页面底上 4.50 → 5.01 |
   | 击杀芯片字 | → `#166534` | 4.49 → 6.38 |
   | 顽固芯片字 | → `#854d0e` | 4.38 → 6.09 |
3. **删除死代码 `recommend.js`。**
   - 31 个函数中 28 个无外部引用；它按 id 操作的 15 个元素中 14 个在页面里已不存在。
   - 仍在用的 `showRecommendPanel()`（行动推荐"开始常规复习"）与 `showExportPanel()`（"全题库导出 ↗"）并入 `schedule.js`。
   - `core.js` 删除只被它使用的 `REC_DATA`、`REC_SELECTED`、`REC_VIEW`、`REC_PREVIEW_MODE`。
   - `labels.js` 中 `typeof renderDualLists === 'function'` 分支自然失效，不影响任何页面。
4. **脱敏源码导出收录 `tests/` 下的 JSON。** 否则 `tests/ui_baseline.json` 不随包导出，受限模式下 `check_ui.py` 会失败。其它目录的 JSON 仍排除。
5. **新增门禁与工具：**
   - `tests/check_ui.py`：新代码零容忍规则 R1–R9，旧代码按文件的棘轮基线。
   - `tests/check_contrast.py`：48 组对比度检查。
   - `tests/ui_baseline.json`：棘轮基线。
   - `tests/test_ui_gates.py`：12 个用例，其中包括"仓库本身通过两道门禁"，所以完整模式跑 `unittest` 就会覆盖这两道门禁。
   - `tests/fixtures/make_vault.py`：演示 Vault 生成器。
   - `tests/visual/run.py`：前后截图对比与运行时审计。

## 影响文件

| 类别 | 文件 |
|---|---|
| 新增 | `assets/app/styles/tokens.css`、`tests/check_ui.py`、`tests/check_contrast.py`、`tests/ui_baseline.json`、`tests/test_ui_gates.py`、`tests/fixtures/make_vault.py`、`tests/visual/run.py`、`AI/frontend/design-system.md`、本日志 |
| 删除 | `assets/recommend.js` |
| 修改（代码） | `assets/styles.css`、`assets/schedule.js`、`assets/core.js`、`assets/dashboard.js`（注释）、`omrs_dashboard.html`、`omrs/source_export.py`、`omrs/version.py`、`tests/test_source_export.py` |
| 修改（文档） | `AGENTS.md`（映射表加两行、收尾第 8 条）、`README.md`、`AI/README.md`、`AI/api.md`、`AI/changelog.md`、`AI/environment.md`、`AI/optimization.md`、`AI/frontend.md`、`AI/frontend/shell.md`、`AI/frontend/qview.md`、`AI/frontend/review.md` |

## 验证（已实际执行）

- **Python 单测**：`python3 -m unittest discover -s tests -p 'test_*.py' -q`，149 个 OK。基线 137 个，新增 12 个。
- **Node 测试**：`node --test tests/*.js`，140/140 通过。
- **两道新门禁**：
  - `python3 tests/check_ui.py`：0 处问题。旧代码存量：行内事件 277、innerHTML 类 198、行内样式 263、颜色字面量 195、硬编码字号 418。按同一口径，基线提交上是 286 / 212 / 271 / 245 / 418。
  - `python3 tests/check_contrast.py`：48 组，0 组不达标。
- **文档检查**：`python3 tests/check_docs.py --diff 6ac228e` 退出码 0（1 条既有提醒：`AI/api.md` 52KB）。
- **前后截图对比**：`tests/visual/run.py --ref 6ac228e`，12 页 × 浅/深 × 桌面/手机，共 48 组。
  - 浅色 24/24 有差异，像素变化 0.03%–1.5%，全部来自上表的颜色修正。
  - 深色桌面 12 组的差异只在侧栏底部版本号 `v1.19.0` → `v1.19.1`；深色手机 0 差异。
  - 数据复盘页"数据基准时间"是服务端实时值，已登记为截图遮罩。
  - 页面脚本错误 0。
- **端到端（真实 Chromium，full fixture）**：
  - 仪表盘"开始常规复习"进入复习调度，`SCH_VIEW=arrange`。
  - "全题库导出 ↗"进入导出，`SCH_VIEW=export`，`SCH_EXPORT_RETURN=arrange`。
  - `typeof renderDualLists` 为 `undefined`；页面错误 0。
- **既有失败**：`PYTHONPATH=. python3 tests/smoke_schedule_workbench.py` 在基线提交和当前工作区都在第 138 行失败（到期=今天筛选期望 14、实得 0），与本任务无关，已记入 `AI/optimization.md`。

## 未执行的验证

- 生产重启、远端设备与手机实机验收（受限模式不做，见交接清单）。
- `check_docs.py --write-log-index`（受限模式不生成索引）。
- 浏览器兼容性只测了 Chromium 141。

## 设计基线审计（P3–P7 的验收底稿）

使用 full fixture、浅色主题，数据来自 `tests/visual/run.py --audit-only`。"小目标"指高度小于 28px 的可点元素。

| 页面 | 字号种数 | 最小字号 | 小目标 | 行内样式元素 | 手机页面横向溢出 |
|---|---|---|---|---|---|
| 仪表盘 | 18 | 9px | 4 | 8 | 否 |
| 数据复盘 | 15 | 8.7px | 0 | 186 | **是** |
| 题目库 | 7 | 9.6px | 43 | 137 | 否 |
| 展示板 | 10 | 9.75px | 13 | 7 | 否 |
| 目录 | 9 | 9.45px | 25 | 52 | 否 |
| 复习调度 | 11 | 9.6px | 41 | 64 | 否 |
| 即时练习 | 9 | 9.6px | 3 | 4 | 否 |
| 反馈录入 | 7 | 9.72px | 0 | 8 | 否 |
| 录入题目 | 12 | 9.9px | 0 | 7 | **是** |
| 历史记录 | 7 | 10.2px | 0 | 6 | 否（36 个元素内容溢出） |
| 报告 | 8 | 10.2px | 0 | 6 | 否 |
| 设置 | 6 | 10.2px | 0 | 1 | 否 |

目标（计划 §2）：每页字号不超过 6 种，正文不小于 13px，辅助文字不小于 11px，小目标为 0。目前没有一页全部达标。

另外，空库下的反馈录入、即时练习空状态，以及 390px 下即时练习筛选下拉框文字被裁切，仍与计划 §1.3 的描述一致，留给 P2/P3 处理。

## 生产合并与验收补记（2026-09-25）

- **生产生效**：补丁已合入 `/root/workspace/apps/OMRS` 并重启 `omrs.service`；服务 `active/running`、`NRestarts=0`。`GET /api/status` 返回 `v1.19.1`、208 题、0 冲突；`/api/auth/session` 显示新实例、本机已认证，远端 PIN 尚未配置。未创建 Git commit，保留生产工作树未提交状态。
- **生产门禁**：Python `unittest` 149 项通过；UI 门禁 0 问题；48 组浅/深色对比度均通过；`check_docs.py --diff HEAD` 通过。Node 为 139/140：唯一失败仍是 `tests/smoke_frontend_actions_catalog.js` 的 3 条行动计划断言；在部署前回滚源码快照、包候选与生产树结果完全相同，且测试涉及的 `assets/actions.js` / `assets/catalog.js` 不在 P0 补丁内，归类为既有基线失败（不是本次引入）。
- **浏览器实测**：Browser Use Chromium 打开生产首页，标题与版本 `v1.19.1` 正确，先加载 `tokens.css` 再加载 `styles.css`，页面错误 0。设置页实际切换浅/深主题并恢复深色；390px 视口下首页及复习调度无横向溢出；“开始常规复习”进入 `arrange`，全题库导出入口进入 `export`，返回后仍为 `arrange`。这些交互及设置页源码导出只有 GET 请求。
- **源码导出**：设置页按钮显示“已下载”；同一 `/api/source/export` 返回 ZIP（HTTP 200、6,407,906 字节、324 项、CRC 完整），包含 `assets/app/styles/tokens.css`、`tests/ui_baseline.json`、`SOURCE_EXPORT_MANIFEST.txt`，未包含题库、Ledger、boards 等运行数据。
- **数据保护**：部署前后 224 个题目 Markdown 的清单及 SHA-256 完全一致。与 2026-09-24 数据备份比较，`.omrs` 的 214 项中 212 项逐字节一致；剩余 `config.json` 差异是 9 月 24 日 21:25 已存在的 `lan_pin_exempt_cidrs` 设置，`ledger.db` 的 SQLite integrity check 前后均为 `ok`，所有业务表行数相同，仅 `workspace_fingerprint.last_seen_at` 与 `workspace_scan_status.last_scan_at` 因启动扫描更新。重启后服务日志无 POST/PUT/PATCH/DELETE；题目数、冲突数不变。
- **远端限制**：真实 Chromium 访问 `https://home.ruibin-ningh.top:8472/` 到达 OMRS 登录页，并明确提示尚未配置 PIN。未代用户设置 PIN，因此没有已认证远端页面或实体手机验收；配置 PIN 后再做远端登录验收。
- **验证差异**：包内原始记录称 Node 140/140；本机完整复跑为 139/140，已通过未部署基线复测确认相同失败。隔离 Playwright 视觉审计在基线与升级副本均遇到 Chromium 页面崩溃；生产首页的真实浏览器 DOM、主题、移动视口与交互验收已完成，但不把它表述成 48 组生产截图对比。
