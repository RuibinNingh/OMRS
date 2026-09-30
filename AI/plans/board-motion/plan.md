# 展示板页面切换动效

## 目标

在展示板纸面工具条增加动效设置，支持渐隐渐显、左右滑页、抽纸和关闭动效，并用滑杆调整 100–800ms 的过渡时长（步进 50ms，默认 280ms）。设置仅保存在浏览器本地，纸面翻页与切换展示板时生效；独立下载与打印保持静态。

## 约束与决策

- 执行者：Codex，完整模式。
- 复用常驻预览 iframe、现有 `brd-pop` 浮层和设计 token，不新增后端字段。
- `prefers-reduced-motion: reduce` 时立即完成切换；动画未结束再次操作时取消当前动画，只执行最新目标。
- 板切换固定使用渐隐渐显；滑页和抽纸只用于同一板的单页切换。
- 动效配置使用 `localStorage["omrs-board-motion"]`，格式为 `{kind:"fade|slide|paper|none",duration:100..800}`。

## 计划范围

实现 `assets/app/features/board/` 的偏好、浮层与宿主消息，更新 `omrs/export_templates/board.js` / `board.css` 的嵌入式过渡，并同步展示板、导出与协议文档。补充 Node、浏览器、展示板 E2E、导出打印、UI、对比度、视觉和文档门禁。
