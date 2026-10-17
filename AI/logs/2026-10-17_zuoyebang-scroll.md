# 2026-10-17 作业帮工作区滚动修复

## 背景

用户截图反馈「这个页面不能滑动?」。执行者Codex，完整模式；本次为独立缺陷修复，基线1844c8c。开工已有 `AI/plans/omrs-maintenance/validation.json` 修改，保持不动，不纳入本任务。未执行提交、推送或生产部署。

## 行为变化

桌面外壳在大于1160px时固定视口高度并隐藏溢出；作业帮已登记workbench，却没有对应滚动容器。真实浏览器在1440px用滚轮无法下移，新增断言在修改样式前失败，截图保存在 `/tmp/omrs-zyb-scroll-before/`。

在作业帮工作区补齐flex剩余高度、min-height:0及纵向自动滚动，使用align-content:start避免短内容网格拉伸。左右栏统一滚动，可到达原图下方记录和核对表单；窄屏仍使用文档滚动，长图内框保持独立滚动。

## 影响文件

- `assets/app/features/zuoyebang/zyb.css`：仅新增桌面滚动规则。
- `tests/e2e/zuoyebang.py`：增加1440、1161、1160、390px真实滚轮及底部录入按钮可达性，共8项；独立标签页恢复同一合成搜题会话，避免自动点击滚入掩盖问题。
- `AI/frontend/zuoyebang.md`、`AI/frontend/shell.md`、`AI/frontend/architecture.md`、`README.md`：同步页面滚动与验收约定。
- 本日志及自动生成的 `AI/logs/log.md`：记录行为、证据与验证范围。

已通过git diff --name-status复核；既有validation.json差异不属于本次修复。

## 验证

测试使用临时Vault和随机端口，清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL；摄像头测试另清除OMRS_TEST_CDP_URL。默认python3缺少segno，使用已有 `/tmp/omrs-zuoyebang-venv/bin/python`（下称测试Python），未安装依赖。

- `env -u OMRS_TEST_CDP_URL -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL OMRS_ZYB_SHOTS=/tmp/omrs-zyb-scroll-result /tmp/omrs-zuoyebang-venv/bin/python tests/e2e/zuoyebang.py`：86/86通过，退出0；包括真实滚轮、原图与题框、完整长图、刷新、人工编辑及正式合成题目入库。
- 中间回归版本在同一标签连续调整宽度并重置滚动时，390px断言失败；诊断显示浏览器滚动恢复／平滑回顶干扰滚轮。最终各尺寸使用独立标签页加载相同sessionStorage快照，删除诊断代码后完整86项通过，不以中间结果计成功。
- `python3 tests/check_ui.py`：0问题；`python3 tests/check_contrast.py`：58组、0不达标，均退出0。
- `node --test tests/app/*.test.mjs`：529通过、0失败、0跳过，退出0。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL /tmp/omrs-zuoyebang-venv/bin/python tests/app/run_browser.py`：34通过、0失败，退出0。
- `env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL /tmp/omrs-zuoyebang-venv/bin/python tests/visual/run.py --ref HEAD --pages zuoyebang --out /tmp/omrs-zyb-scroll-visual`：浅／深主题、桌面／手机共4对，0像素差异，无页面脚本错误，退出0。

视觉对照的默认夹具为空态，内容未超过一屏，4对均无差异符合预期。满内容滚动前失败截图和修复后四档底部截图分别位于 `/tmp/omrs-zyb-scroll-before/`、`/tmp/omrs-zyb-scroll-result/`；人工检查1440px底部截图，侧栏和顶栏固定，右栏核对表单与录入按钮在视口内。文档门禁与日志索引按仓库要求生成，git diff --check通过。

未执行：生产服务、真实账号网络、付费模型及实体手机触摸验证；本次仅调整前端布局，使用合成上游和实际Chromium，不访问真实错题库。全量后端单测未运行，后端代码与接口无变更。

## 下一步

本地修复与隔离验证完成；生产发布需另行授权。版本号保持v2.8.1。
