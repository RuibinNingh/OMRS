# 2026-09-30 AI 助手界面重设计

## 背景

用户要求重设计助手页面：查询过程改为“处理”且默认展开、删除输入框展开 / 收起按钮、上下文与缓存同时展示、本次总量按输入 + 输出 + 缓存呈现，并修复欢迎页手机布局。Codex 完整模式，基线为任务开始时的工作区（仅有未跟踪 `.playwright-mcp/`，未触碰）。

## 行为变化

- 每次运行使用“处理中 / 处理完成”等总字段，过程默认展开；完成后不自动折叠，用户点击折叠图标后才收起。最终回答、确认卡和写入结果保持可见。
- 输入区移除“展开 / 收起”控件，文本区按内容自动增长；上下文占用与缓存命中率在同一入口并列显示，弹层合并为上下文构成与缓存统计。
- 运行详情把输入未缓存部分、输出、缓存列为互斥组成，本次总量以三项相加；缓存未知时明确显示未知。
- 欢迎页改为带能力说明的紧凑卡片布局，手机端单列排列，长文案不再挤压权限标签；输入区和头部满足窄屏触控尺寸。

## 影响文件

- `assets/app/features/assistant/view.js`、`index.js`、`usage.js`、`insp-view.js`、`mobile-layout.js`：运行过程、用量和输入状态。
- `assets/app/features/assistant/assistant.css`、`assistant-run.css`、`assistant-side.css`、`assets/app/styles/tokens.css`：欢迎页、处理栏、输入框和用量样式。
- `tests/app/assistant.test.mjs`、`tests/e2e/assistant_usage.py`：默认展开、收起、用量三项和手机回归。
- `tests/visual/run.py`、`AI/environment.md`：助手页面隔离截图配方。
- `AI/frontend/assistant.md`、`README.md`：同步用户可见行为。

## 验证

已实际执行：

- `node --test tests/app/assistant.test.mjs`：18/18 通过。
- `python3 tests/check_ui.py`：0 处问题。
- `python3 tests/check_contrast.py`：58 组对比度全部通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant_usage.py`：7/7 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant_p3.py`：23/23 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant.py`：58/58 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref 9edda17 --pages assistant --out /tmp/omrs-assistant-ui-visual`：桌面 / 手机、浅色 / 深色截图完成，无页面脚本错误；差异为预期的欢迎页与输入区重设计。

未执行：真机 Android / iOS；当前环境只有 Chromium，真机需接入设备后补验。
