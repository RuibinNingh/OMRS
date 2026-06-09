# 2026-06-08 导出答案图片渲染修复 + AI 知识点限定开关

## 1. 导出 Word（带答案）：答案区图片不渲染 → 修复

**问题**：`POST /api/export` 带 `include_answers=true` 时，「三、答案」一节按行只走 `_parse_math_runs`，没有解析图片嵌入。答案里的 `![[<uid>-a-N.png]]`（由 `creation._section_body` 写入）于是被当作**字面文本**输出，Word 中看到的是 `![[...]]` 而非图片。题目区因走 `_extract_embeds` + `_render_image_embed` 一直正常，只有答案区漏了。

**改动**（`omrs/exporting.py`）：
- 抽出共享渲染函数 `_render_text_block(vault, ctx, text)`：按行解析 `![[名]]`/`![](路径)` 嵌入 → `_render_image_embed`，其余文本 → `_parse_math_runs`（OMML/源码回退）。
- `_question_block` 的题目正文循环改为调用该函数（行为不变）。
- `_build_docx_bytes` 的答案分支由「逐行 `_parse_math_runs`」改为 `body.extend(_render_text_block(...))`，与题目共用同一条路径——答案图片、答案里的 LaTeX 自此同样渲染。

**测试**：合成 vault（题目图 + 答案图各 1 张，均以 `![[..]]` 嵌入），`include_answers=True` 导出后：全部 XML part `ET.fromstring` 良构；`word/media/` 含 2 张图；`document.xml` 出现 2 个 `<w:drawing>` 且**不再含字面 `![[`**；2 条 image 关系；`include_answers=False` 仍只含题目图、无「三、答案」（回归）。另用 LibreOffice headless 把 docx 转 PDF→PNG **目视确认题目图与答案图都显示**。

## 2. AI 自动识别：新增「仅从已有知识点中选择」开关

**需求**：此前 `classify` 的 `knowledge_tags` 被**无条件**硬过滤为「已有分类 ∪ 已有知识点」；希望用户能在设置里选择是否限定。

**改动**：
- `omrs/common.py`：新增 `CONFIG_DEFAULTS = {"allow_external": False, "ai_restrict_tags": True}`，`load_config` 三个返回点统一用它（缺省即「限定」，与历史行为一致）。
- `omrs/ai_assist.py`：
  - 新增宽松提示词 `CLASSIFY_TEMPLATE_OPEN`（仅第 3 条不同：知识点**优先复用已有、无贴切项才可新建**）。
  - `classify_question(..., restrict_tags=None)`：`None` 时读 `config.ai_restrict_tags`（默认 `True`）。`True` 用严格模板 + 硬过滤；`False` 用宽松模板，结果仅 `_as_str_list` 归一化并**取前 4 个**（允许新词）。返回体新增 `restrict_tags`。
  - `recognize_question` 透传 `restrict_tags`。
  - 服务端 `/api/ai-recognize` 不变（不传该参→读 config，即时生效、无需重启）。
- 前端：
  - `omrs_dashboard.html`「设置 → AI 自动识别」卡片新增复选框 `#st-ai-restrict`（默认勾选）+ 说明（仅影响知识点；科目/分类一直允许新建）。
  - `assets/app.js`：`loadSettings()` 按 `cfg.ai_restrict_tags!==false` 回填勾选；`saveAiSettings()` 的 `POST /api/config` 体新增 `ai_restrict_tags`。

**测试**（monkeypatch `_call_model`，无网络）：模型返回「已有项 + 新造词」时——`restrict_tags=True` 只留已有项且用到「禁止创造」提示词；`False` 保留新词且用「优先从」提示词；`None` 读 config（默认过滤，置 `false` 后保留）；`recognize_question` 透传生效；无限定时输出截断到 4 个。`load_config` 默认含 `ai_restrict_tags=True`。

## 数据/兼容性

- 不改 Markdown 文件格式、CSV、UID 规则。`config.json` 新增可选键 `ai_restrict_tags`（缺失=`true`，旧库零改动即保持原行为）。
- `/api/export` 请求/返回不变（`include_answers` 早已支持，本次补文档并修复其答案图渲染）。`/api/ai-recognize` 的 `classify` 返回新增 `restrict_tags` 字段（增量、不破坏）。
- 文档：`api.md`（config GET/POST、ai-recognize、export 补 include_answers 与答案图渲染）、`data.md`（config.json 表 + CONFIG_DEFAULTS）、`frontend.md`（设置 AI 卡片开关、录入页 classify 说明）同步更新。
