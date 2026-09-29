# 2026-09-30 v2.0.0 P3 助手附件与移动交互

## 背景

按 `AI/plans/v2.0.0/exec-2026-09-29-p3.md` 执行 R3、R4，基线 `46d41c8`，Codex 完整模式，独立工作树。未访问真实 Vault、生产服务或 Git 远端。

## 行为变化

- 聊天主面板接收 PNG/JPEG/GIF 文件拖放，进入时显示统一遮罩；文字与链接拖拽不接管。PDF/TXT 等不支持格式明确提示。图片处理中计入 6 张上限并禁用发送；切换会话、清空、卸载时使迟到读取失效，切换详情返回时再次清空期间拖入的附件。
- 待发送图、历史图和 AI 草稿来源图共用站内图片预览：切换、缩放、下载、新标签次级入口、Esc/返回键关闭、焦点恢复和背景滚动锁。历史图继续使用已存 SHA，不重复上传。
- 手机助手合并为一层聊天头部，保留主导航、对话列表、新对话和运行详情。输入区按可见视口调整，空输入一行、约四行后内部滚动，可展开编辑；手机 Enter 换行、按钮发送，桌面 Enter 发送，中文组合及确认后短时间内不会误发。建议只在空对话出现，用量收成小入口，附件横向滚动；长用户消息及多项已完成查询轨迹可展开，待确认操作和回答始终直接显示。

## 影响文件

- `assets/app/features/assistant/`：会话 generation、拖放和输入事件、手机布局、消息与轨迹视图及样式。
- `assets/app/ui/image-viewer.*`、`assets/app/styles/ui.css`、`assets/app/gallery-*`：共享预览组件、样式和组件陈列。
- `assets/app/features/create/drafts-preview.js`、`drafts-view.js`、`drafts.js`、`drafts.css`、`index.js`：来源图接入共享预览。
- `tests/app/`、`tests/e2e/`：组件、视图、草稿审核与助手专项浏览器回归。
- `AI/frontend/assistant.md`、`AI/frontend/components.md`、`AI/frontend/create.md`、根 `README.md`、本计划 `progress.md`：同步当前行为和阶段结果。

## 验证

已实际执行：

- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：384/384。
- `node --test tests/app/*.test.mjs`：380/380。
- `python3 tests/app/run_browser.py`：33/33。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant.py`：58/58。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant_p3.py`：23/23，含聊天主区拖放、迟到附件、延迟会话详情、预览返回、桌面/手机输入法事件与 360/390/430px 可视区域。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant_race.py`：2/2。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/drafts.py`：55/55，含来源图站内预览、切图、焦点恢复及原审核流程。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/shell_router.py`：23/23。
- `python3 tests/check_ui.py`：0 处；`python3 tests/check_contrast.py`：58 组达标。
- `python3 tests/check_docs.py --write-log-index` 与 `python3 tests/check_docs.py --diff 46d41c8`：文档检查 0 处问题；3 条既有文件大小提醒。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref 46d41c8 --pages assistant,create --out /tmp/omrs-v2-p3-visual-final`：8 张前后截图，无脚本错误、无页面横向溢出、无运行时行内样式、小于 28px 的可点目标为 0。4 张 create 图无差异；4 张 assistant 图有预期差异：手机浅/深约 7.03%/7.32%，来自去掉重复顶栏与底部输入区位置；桌面浅/深约 0.13%，来自输入区高度。报告在 `/tmp/omrs-v2-p3-visual-final/report.html`。

未执行：Android Chromium 与 iOS Safari 真机软键盘、候选词、横竖屏和浏览器地址栏变化验收。用户确认本轮没有真机或远程接入；桌面 Chromium 的手机环境与模拟 VisualViewport 只证明代码路径，不记为真机通过。真实模型与生产部署未获授权，亦未执行。

## 遗留与下一步

P3 代码与隔离门禁完成，真机项待设备可用后按计划 §8、§9 验收。由主代理按 P3→P4 顺序集成，合并 `assistant/index.js` 等共享文件时逐 hunk 审核并重跑门禁；继续 P4–P7，不以 P3 阶段提交宣称 v2.0.0 完成。
