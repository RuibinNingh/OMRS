# 2026-09-05 AI 录入去除题目开头题号

## 变更摘要

AI 题目文本识别现在会去掉图片内容最开头的题号，例如 `11.`、`11、`、`11．`、`（11）`；答案识别在开头为“题号 + 答案/解析标题”时去掉题号。答案和解析内部的步骤编号、分点编号、选项编号保留。

## 行为与兼容性

- `POST /api/ai-recognize` 的 `question_text` 与 `answer` 返回字段不变。
- 快速录入和收件箱区域转文本共用同一清洗逻辑。
- 仅处理整段开头，不改题目或答案正文中的编号。

## 修改文件

- `omrs/ai_assist.py`：更新题目/答案提示词；新增统一提取文本清洗；接入快速录入和收件箱。
- `tests/test_ai_assist_taxonomy.py`：增加提示词与题号清洗边界测试。
- `AI/api.md`、`AI/frontend.md`、`AI/inbox.md`：同步接口、界面和收件箱行为说明。

## 验证

- `python3 -m unittest tests.test_ai_assist_taxonomy`
- `python3 -m unittest discover -s tests`

## 同步过的文档

- `AI/api.md`
- `AI/frontend.md`
- `AI/inbox.md`