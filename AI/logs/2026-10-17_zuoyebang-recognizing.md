# 2026-10-17 作业帮识别中的居中提示

## 背景

用户原话：“建议在没有识别完成后加一个提示 识别中”“中间,醒目”。执行者Codex，完整模式；基线cfd272740c0021ba7aa443f96276e8007412ef44，沿用v2.8.2。本次是上一轮交付后的新交互调整，不重写之前的草稿与发布记录。

开工git status仅有AI/plans/omrs-maintenance/validation.json的既有修改，保持原样。当前工作区包含另一个任务已提交的设置日志导出，生产仍固定c312872；本次仅在开发工作区实现和验证，没有修改生产。

## 行为与影响文件

- zyb-dialog.js：识别请求发出到任务结束期间，在工作窗中央显示「识别中」和辅助说明。恢复在途任务也显示；完成、部分失败或任务失败后移除，仍使用既有结果与错误反馈，不重复显示顶部等待说明。
- zyb.css：状态卡使用既有字号、语义色、圆角与阴影token，中央定位且不超出窄屏。转圈复用ui-spin，减少动效时停转；pointer-events:none保留表单、暂存、关闭和键盘操作。状态以role=status礼貌播报。
- README.md、AI/zuoyebang.md、AI/frontend/zuoyebang.md、AI/frontend/design-system.md：同步当前可见交互；本日志和自动索引记录验证。

没有改变模型调用、后端接口、入库或草稿契约。未为可逆的小范围样式调整新增持久化测试，复用现有页面回归，并以仓库外的真实浏览器专项核对等待生命周期。

## 已实际执行的验证

浏览器与图片相关命令使用既有完整依赖解释器omrs-zyb-deps-20261011/.venv/bin/python，清除OMRS_SYSTEMD_SERVICE、OMRS_BOXDETECT_CONTROL和OMRS_TEST_CDP_URL；全部使用临时Vault、随机端口、独立Chromium和合成网络边界，没有访问真实题库。

| 检查 | 实际结果 |
|---|---|
| node --test tests/app/*.test.mjs | 542通过，0失败／跳过 |
| python tests/app/run_browser.py | 35通过，0失败／脚本错误 |
| python tests/e2e/zuoyebang.py | 156/156通过；原有识别、在途人工编辑、刷新、失败重试和入库路径保持 |
| 临时浏览器专项check.py | 12/12通过；首次显示、正中定位、320／390／1920px浅深主题、减少动效、填写、暂存重开、刷新恢复、失败消失和重试完成消失 |
| python3 tests/check_ui.py | 全仓五项计数均0，0处问题 |
| python3 tests/check_contrast.py | 58组通过，0组不达标 |
| python tests/visual/run.py --ref cfd2727 --pages zuoyebang --out /tmp/omrs-zyb-loading-visual | 前后4组完成，0组差异，无脚本错误、页面横溢、小目标或行内样式 |
| git diff --check | 通过 |
| python3 tests/check_docs.py --diff HEAD | 146份文档，0处问题；3条既有文件大小提醒 |

标准视觉对比为未开始识别的空态，4组均0差异符合预期。识别在途另拍浅／深桌面和窄屏截图，新增状态卡居于模态中央，原正文、信息字段和固定底部操作保持。截图关闭有限入场动画后复核，避免把入场过渡误认作半透明样式。

专项脚本和截图位于/tmp/omrs-zyb-loading-check；完整页面回归产物位于/tmp/omrs-zyb-loading-e2e，标准视觉报告位于/tmp/omrs-zyb-loading-visual/report.html。专项通过临时文件控制合成AI的完成时机，真实服务和浏览器仍照常运行，不依赖固定等待猜测状态。

已用git diff --name-status与git status复核本任务范围；通过python3 tests/check_docs.py --write-log-index生成索引，再运行文档差异门禁。既有validation.json的SHA256仍为3d3cdbd203731931981a4db6d940cae48878e1069d55c1c2008c361aa58be9f9。截图与检查日志整理到/root/.codex/artifacts/omrs-zuoyebang-recognizing-20261017。

## 未执行与边界

未调用真实作业帮账号、付费模型或生产业务接口，未验证实体手机／Safari／Edge；窄屏使用真实Chromium视口模拟。未重跑无关后端和网关全量回归，本次仅影响前端等待提示。未提交、推送或部署本次增量。
