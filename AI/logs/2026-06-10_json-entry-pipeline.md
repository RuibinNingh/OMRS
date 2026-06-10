# 2026-06-10 录入系统改造：外部 AI → JSON → 录入/反馈 管线

## 背景

录入系统四项需求：① 支持**分多次录入**；② 支持 **JSON 导入**录入信息；③ 录入页可**复制提示词**，发给任意外部 AI 配截图生成规范 JSON（不依赖设置页 API 配置）；④ **屏幕版**支持把当前作答信息复制为 JSON，并与主程序反馈**对接**。

## 设计

- 定义两种**前端层** JSON 交换格式（详见 `data.md` §11）：题目 JSON `{type:"omrs-questions", questions:[…]}`（字段与 `POST /api/create` 对齐）、作答 JSON `{type:"omrs-feedback", session_id, items:[{uid,is_correct,sub_score}]}`。解析统一走 `parseLooseJson`（容忍 ```` ```json ```` 围栏 / 裸数组 / 单对象），两个导入框互相识别误贴类型并引导。
- 「分多次」用**录入队列**承载：草稿存 `localStorage["omrs_create_queue_v1"]`，跨会话不丢；导入可累积、表单可暂存、创建即出队。
- 屏幕版 → 主程序的回传通道：`meta.session_id` 注入导出件，作答 JSON 自带 Session 归属，反馈页导入时自动关联。

## 改动

**后端 / 模板**
- `omrs/exporting.py`：`_build_export_data` meta 新增 `session_id`；`_SCREEN_BODY` 抽屉操作区新增「📋 复制作答 JSON（导入主程序反馈）」独占一行（避免 380px 三键挤压）。
- `omrs/export_templates/screen.js`：新增 `sessionId()`（meta.session_id，旧件回退正则解析 meta.sub）、`buildAnswersJson()`（仅导出已判定题；score 为 null 时按对→10 / 错→4）、`copyAnswersJson()` 三级兜底（`navigator.clipboard` → `execCommand` → 自动下载 .json）；`build()` 绑定按钮。
- `omrs/export_templates/screen.css`：`.sh-actions button.share` accent 配色（仿 `.reset` 模式）。

**前端（主程序）**
- `assets/core.js`：全局 `CR_QUEUE` / `CR_QUEUE_ACTIVE_ID` / `CR_DRAFT_SEQ`；通用工具 `parseLooseJson` / `copyTextToClipboard`（clipboard→execCommand 双兜底）/ `looseBool`。
- `assets/app.js`：录入队列全套——`crLoadQueue`/`crSaveQueue`、`crTaxonomy`、`crBuildPrompt`（8 条规则 + 已有科目/分类/知识点清单 + 输出骨架 + 禁围栏指令）、`crCopyPrompt`、`crNormalizeDraft`（清洗/钳制/别名兼容）、`crImportJson`（单题 + 空表单自动填入）、`crLoadDraft`、`crCreateDraftDirect`（confirm 后无图直建）、`crStashForm`（暂存不清空表单）、`crDeleteDraft`/`crClearQueue`、`crOnCreated`（创建成功出队）、`crRenderQueue`；`init()` 末尾恢复并渲染队列。
- `assets/schedule.js`：`doCreate` 成功后调 `crOnCreated()`；新增 `importFeedbackJson`（uid + looseBool 校验、缺省分对10/错4 钳 0–10、Session 匹配选中 / 不在列表仍按该 ID 写历史 / 无 ID 手动模式；填充 `fbRows` 后**不自动提交**）。
- `omrs_dashboard.html`：反馈页顶部「📥 从屏幕版导入作答 JSON」卡片；录入页右列包进纵向容器、顶部新增「📥 JSON 导入与录入队列」卡片（复制提示词 / 导入框 / 队列）；创建按钮旁加「⏳ 暂存到队列」；使用说明补「无 API 方案」。

## 验证

- 静态：Python `compileall`、`node --check` 四脚本、HTML 内联调用交叉核对、13 个新函数齐全——全过。
- 行为级（node stub，单次 eval 还原浏览器共享全局词法环境）：**32/32 断言通过**——围栏解析、宽松布尔、草稿清洗钳制、两题入队 + 跳过无效 + localStorage 持久化、单题自动填表、误贴互导、创建出队、暂存、删除/清空、脏项过滤、提示词含清单/骨架/禁围栏、反馈导入（Session 匹配/未知 TMP 保留/字符串分数/缺省分钳制/误贴引导）。
- 端到端：testvault 真实导出 screen 件（含 `copyJsonBtn` 与 `meta.session_id`），stub 中 `build()` 不抛错，模拟判对第 1 题 / 判错第 2 题后点复制——剪贴板收到的 JSON 结构、session_id（TMP-）、默认分全部正确；并顺带验证 clipboard 缺失时自动落入下载兜底。

## 使用流程

录题：录入页「复制 AI 提示词」→ 发给任意 AI + 题目/答案截图 → 粘贴回复 JSON「导入到队列」→ 分批「填入表单」配图创建（或纯文字「直接创建」）。
回传：手机屏幕版复习 → 抽屉「复制作答 JSON」→ 主程序反馈页粘贴导入 → 自动关联 Session 填充 → 核对后提交。
