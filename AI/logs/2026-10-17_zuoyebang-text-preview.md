# 2026-10-17 作业帮正文预览与源码切换

## 背景

用户原话：“提供一个按钮可以切换预览和源码”“如果是含图片那么缩写占位符”。附图指向独立作业帮工作台的核对正文输入框。本次由Codex按完整模式执行，基线fa50f62，版本保持v2.8.1；不属于进行中计划。已有 `AI/plans/omrs-maintenance/validation.json` 修改保留，未纳入本次提交。

## 行为变化

- 题目与答案选择使用文本后默认预览，单按钮切换源码，各区独立；预览复用共享Markdown／KaTeX，不请求正文图片。
- Markdown图片、Obsidian图片、HTML图片与内嵌data:image缩写成编号占位符，编号避开原文已有的同名文本；源码编辑以可逆映射还原完整正文。删除占位符代表删除对应图片引用，正常编辑、切题、刷新与提交均保留其它原图引用。
- 显示方式随逐题草稿保存，不改变保存方式、脏状态或识别版本。正式提交仍只含mode/text；已入库题卡草稿只恢复显示偏好，不能覆盖首次提交内容。提交中和已入库的源码只读可复制，两种视图均可继续切换。
- 预览和源码使用全站语义token，宽公式局部滚动，适配浅深主题及窄屏。

## 影响文件

- `assets/app/features/zuoyebang/zyb-text.js`：正文视图、可逆图片缩写与内存映射。
- 同目录 `zyb.js`、`zyb-view.js`、`index.js`、`zyb-state.js`、`zyb.css`：接入按钮、编辑回写、逐题显示偏好及样式。
- `tests/app/zyb-text.test.mjs`、`tests/e2e/zuoyebang_text.py`：图片映射与真实浏览器主路径回归；`tests/e2e/zuoyebang.py`、`zuoyebang_mobile.py` 更新显式源码编辑路径，运行时审计排除共享KaTeX生成的公式布局样式。
- `AI/frontend/zuoyebang.md`、`AI/zuoyebang.md`、`AI/frontend/architecture.md`、`AI/frontend/design-system.md`、根 `README.md` 同步当前行为；日志索引自动生成。

## 验证

完整依赖解释器为 `/root/workspace/apps/releases/omrs-4aff445/.venv/bin/python`，下列Python浏览器命令均使用该解释器。

| 实际命令 | 结果 |
|---|---|
| `node --test tests/app/zyb-text.test.mjs tests/app/create-zyb.test.mjs` | 26项通过，其中正文新增8项 |
| `node --test tests/app/*.test.mjs` | 539项通过、0失败 |
| `python3 tests/check_ui.py` | 全仓0问题 |
| `python3 tests/check_contrast.py` | 58组通过 |
| `python tests/app/run_browser.py` | 34项通过、0失败 |
| `python tests/e2e/zuoyebang.py` | 126项通过，含题框、手机排版升级及新增正文30项；无浏览器脚本错误 |
| `python tests/visual/run.py --ref fa50f62 --pages create --create-stage zuoyebang --out /tmp/omrs-zyb-text-LzhOm4/visual` | 浅深主题×桌面／手机共4组，0差异，0脚本错误、横溢、行内样式或过小目标 |
| `python3 tests/check_docs.py --write-log-index`、`python3 tests/check_docs.py --diff fa50f62` | 索引已生成；146份文档、0问题，3条既有体积提醒 |
| `git diff --check` | 通过 |

标准前后对比截图为无候选的空工作台，本次变化只作用于已有文本正文，因此4组均无像素差异。填充正文的真实主路径另外生成16张截图，位于 `/tmp/omrs-zyb-text-LzhOm4/e2e/text-preview-*.png`、`text-source-*.png`，覆盖浅深主题及320/390/1024/1440px；实际查看了390px深色预览及1440px浅色源码。

填充状态的可见变化逐项如下：正文标题旁新增切换按钮；文本默认展示排版公式，源码保持可编辑等宽字体；图片及长data URL显示为短编号占位符；预览限制高度，长公式局部滚动；已入库源码只读仍可复制。16档均无页面横溢，源码与预览往返及最终请求均保持完整图片原文。安全用例中的script文本按原文转义展示，无执行或图片请求。

运行记录保存在 `/tmp/omrs-zyb-text-LzhOm4/`。交付前复核 `git diff --name-status` 及未跟踪文件清单，仅纳入本任务文件；已有validation.json的SHA256仍为3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9。

## 未执行与边界

未执行真实官方搜题、付费模型、实体手机和生产部署；本次修改位于前端，使用合成外部响应、临时Vault与随机端口验证。生产仍使用此前已发布版本。本地浏览器使用独立Chromium，启动前清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL及OMRS_TEST_CDP_URL。
