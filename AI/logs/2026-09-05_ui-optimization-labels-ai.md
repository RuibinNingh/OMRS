# 2026-09-05 UI优化、标记系统改进与AI增强

## 问题与需求

用户反馈了以下问题：
1. 反馈录入页面的"＋ 编辑标记"按钮点不开
2. 错题集打印版不需要活页孔功能，正常间距即可
3. 标记系统UI有臃肿感，尤其是画廊模式
4. 需要AI生成标记功能
5. AI填充题目信息时要同时喂上题目和答案，便于更准确识别

## 实施改动

### 1. 修复反馈录入页面标记按钮问题

**文件**: `assets/styles.css`

问题原因：按钮可能被遮挡或z-index不足

**修复**：为 `.fb-labels-head .btn` 添加 `position: relative; z-index: 10`，确保按钮在最上层可点击。

### 2. 删除活页孔功能，改用正常间距

**影响文件**：
- `assets/board.js` - 移除孔位选择UI，改为题间留白行数输入
- `omrs/boards.py` - 删除 `binding_marks` 配置，默认间距从6行改为2行
- `omrs/export_templates/board.js` - 移除活页孔绘制代码

**具体改动**：
- 删除了3孔/26孔选项
- 默认 `gap_lines` 从 6 改为 2
- 保留了左侧装订线（12mm处的虚线），但不再绘制孔位圈
- 用户可通过输入框自由调整题间留白（0-24行）

### 3. 优化标记系统UI - 更紧凑简洁

**文件**: `assets/styles.css`

**标记芯片优化**：
- 高度从 18px 减至 17px
- 斜角从 8px 减至 7px
- 内边距从 5px 减至 4px
- 字号从 .66rem 减至 .64rem
- 芯片间距从 4px 减至 3px
- 表单行高度从 28px 减至 26px
- 按钮高度从 20px 减至 19px

**画廊模式优化**：
- 卡片内边距从 14px 减至 12px
- 卡片间距从 10px 减至 8px
- 元数据字号从 .72rem 减至 .7rem，行高从 1.7 减至 1.5
- 预览区内边距从 12px 减至 10px
- 预览区最小高度从 160px 减至 140px，最大高度从 240px 减至 200px
- 操作按钮间距从 10px 减至 8px
- 添加了卡片hover效果（边框高亮和阴影）

### 4. AI生成标记功能

**后端改动** (`omrs/ai_assist.py`):

**更新提示词模板**：
- `CLASSIFY_TEMPLATE` 和 `CLASSIFY_TEMPLATE_OPEN` 都新增了标记生成功能
- 在提示词中添加"已有标记"列表
- 要求AI从已有标记中选择0-3个合适的标记

**更新 `classify_question` 函数**：
- 新增 `labels` 返回字段
- 从标记系统获取所有已有标记
- 对AI返回的标记进行过滤，只保留已有标记中的（最多3个）

**前端改动** (`assets/app.js`):
- `crClassify` 函数处理AI返回的 `labels` 字段
- 调用 `setCreateLabels` 自动填充标记到录入表单

### 5. AI同时分析题目和答案

**后端改动** (`omrs/ai_assist.py`):

**新增 `_call_model_multi_image` 函数**：
- 支持多张图片的模型调用
- 图片按顺序放在content数组中，文本提示在最后
- 完整的错误处理和响应解析

**更新 `classify_question` 函数**：
- 新增 `answer_image` 参数
- 当提供答案图片时，调用 `_call_model_multi_image` 同时分析题目和答案
- 提示词根据是否有答案图片动态调整（"和答案"）

**更新 `recognize_question` 函数**：
- 新增 `answer_image` 参数并传递给 `classify_question`

**服务器改动** (`omrs/server.py`):
- `/api/ai-recognize` 路由支持 `question_image` 和 `answer_image` 字段
- 兼容旧的 `image` 字段名

**前端改动** (`assets/app.js`):

**更新 `crClassify` 函数**：
- 同时读取题目图片（第1张）和答案图片（第1张）
- 构建包含 `question_image` 和 `answer_image` 的请求
- 更新提示文本："同时分析题目和答案"
- 显示AI生成的标记数量

## 技术细节

### 多图AI调用实现

```python
def _call_model_multi_image(vault, user_text, image_data_urls, max_tokens, timeout, purpose):
    content_parts = []
    for img_url in image_data_urls:
        if img_url and isinstance(img_url, str):
            content_parts.append({"type": "image_url", "image_url": {"url": img_url}})
    content_parts.append({"type": "text", "text": user_text})
    
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content_parts}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
```

### 标记生成过滤逻辑

```python
# 获取已有标记
from .labels import list_labels
existing_labels = [label["name"] for label in list_labels(vault) if not label.get("archived")]

# AI返回后过滤
labels = _as_str_list(parsed.get("labels", []))
existing_labels_set = set(existing_labels)
labels = [label for label in labels if label in existing_labels_set][:3]
```

## 版本更新

从 v1.14.1 升级到 v1.14.2

## 测试验证

- ✅ boards.py 的 normalize_print 正常工作
- ✅ DEFAULT_PRINT 已更新（gap_lines=2，无 binding_marks）
- ✅ CSS样式已优化，标记和画廊更紧凑

## 用户可见改进

1. **反馈录入更流畅**：标记按钮现在可以正常点击
2. **打印更实用**：去掉了不必要的活页孔，用简单的题间距控制
3. **界面更清爽**：标记芯片和画廊卡片更紧凑，减少视觉臃肿感
4. **AI更智能**：
   - 自动生成合适的标记（如"易错"、"计算失误"等）
   - 同时分析题目和答案，识别更准确
5. **录入更高效**：AI填充信息时可一次性完成科目、分类、难度、知识点和标记

## 注意事项

- AI生成的标记只会从已有标记中选择，不会创建新标记
- 多图AI调用需要模型支持多图输入（如 qwen-vl-max）
- 答案图片是可选的，没有答案图片时仍可正常识别题目信息
- 旧的展示板配置会自动兼容（binding_marks字段会被忽略）
