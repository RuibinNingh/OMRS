# 2026-10-18 作业帮题图字号与行高调整

## 背景

用户先要求对照作业帮截图判断渲染与DPI是否合适，随后明确「可以,调整一下」。执行者为Codex，运行模式为完整模式；本次为独立的小范围调整，不执行或改写已完成计划。基线为e6c8ab9d42c4cf6a3a2240ceb65ee68e9281c0e7。

开工已有AI/plans/omrs-maintenance/validation.json未提交改动；本次未修改该文件，收尾按SHA256复核保持原样。未读取真实题库、调用官方账号／付费模型或改变生产状态。

## 行为变化

- 保留360 CSS px纸面、16px边距及3倍输出，题目与答案仍各为宽1080px的完整PNG。
- 正文由17px调整为15px，行高由1.65调整为1.5；tk-md2html正文原有1.6行高也统一为1.5。公式、表格的局部适配与资源预算保持。
- 前后端排版版本同步为mobile-360-v2。旧版手机版与无layout预览沿用现有「重新生成手机版」入口；重新生成建立独立记录，保留最新人工编辑、旧图片与旧草稿。原像素裁图及已有创建预留／正式题目不自动改写。

## 影响文件

- 渲染：omrs/zuoyebang/paper.css、omrs/zuoyebang/render.py。
- 页面版本识别：assets/app/features/zuoyebang/zyb-state.js。
- 现有回归适配：tests/test_zuoyebang_render.py、tests/app/create-zyb.test.mjs、tests/e2e/zuoyebang_mobile.py。Node同时验证旧版手机版与无版本记录；浏览器升级专项使用旧版手机版记录。
- 当前行为文档：AI/zuoyebang.md、AI/frontend/zuoyebang.md、AI/data/storage.md、AI/frontend/architecture.md及根README.md。
- 本日志及由脚本生成的AI/logs/log.md。

## 已实际执行的验证

所有服务／浏览器测试均使用临时Vault、随机高端口，并清除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL。浏览器脚本另清除OMRS_TEST_CDP_URL，使用独立Chromium。

1. 后端专项：使用已登记的完整依赖解释器执行以下命令，56项全部通过。覆盖原题库格式、中文笔画像素、长公式／旧公式／宽表格适配、完整长答案、SVG附图、坐标与录入存储。

   ```bash
   env -u OMRS_SYSTEMD_SERVICE -u OMRS_BOXDETECT_CONTROL \
     /root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python \
     -m unittest tests.test_zuoyebang_render tests.test_zuoyebang_svg \
     tests.test_zuoyebang_geometry tests.test_zuoyebang -q
   ```

   首次使用系统python3执行相同56项时，扫码用例因缺少segno依赖报1个错误；随后复用仓库文档登记的依赖环境重跑整组通过，没有安装依赖或修改生产环境。

2. `node --test tests/app/*.test.mjs`：550项通过，0失败、0跳过。
3. `python3 tests/app/run_browser.py`：35项组件浏览器测试通过。
4. `python3 tests/check_ui.py`：全仓违规计数均为0；`python3 tests/check_contrast.py`：58组全部通过。
5. 使用上述完整依赖解释器运行`tests/e2e/zuoyebang.py`：157/157通过。真实Chromium覆盖选题、1080完整渲染、PNG／SVG附图、长图滚动、识别与人工核对、幂等创建、刷新恢复、旧版预览主动重新生成、最新人工内容与原图片保全；覆盖320至2550px及浅深主题，没有未捕获脚本错误。
6. 使用上述完整依赖解释器执行`tests/visual/run.py --ref HEAD --pages zuoyebang --out /root/.codex/artifacts/omrs-zyb-density-20261018-qxy7z08l/visual`：4组浅深主题、桌面／手机前后截图均为0%差异，所有审计无横溢、行内样式或过小目标。该标准fixture为空预览，不能代替题图对比；有图页面另由第5项验收并查看桌面与手机截图。
7. 按基线CSS与当前CSS分别实际渲染相同文字、公式及合成长答案，均保持1080px宽。统一到720px后，普通中文字形约31px→27px、普通文本行高56px→45px；样例位移公式由换行变为同一行。题目高度1173→861px，富文本样例1089→789px；含59个公式的合成长答案12552→10569px，公式数及末尾正文保持。以上只证明样例密度与完整性，不声称与作业帮原App像素完全一致。

证据目录为/root/.codex/artifacts/omrs-zyb-density-20261018-qxy7z08l，包含samples/comparison.png、samples/metrics.json、两版原尺寸PNG、e2e/checks.json及页面截图、visual/report.html与audit.json。样例生成脚本只放在该目录，没有进入仓库。

`git diff --name-status`已复核实际变化，`git diff --check`通过；原有validation.json的SHA256保持。已执行`python3 tests/check_docs.py --write-log-index`生成索引，`python3 tests/check_docs.py --diff HEAD`检查150份文档、0处问题，退出码0；3条提醒为既有大文件，不属于本次调整范围。

## 未执行的验证与下一步

未运行全仓Python测试、真实官方网络／模型、实体手机或生产验收；本次复用相关专项及真实隔离浏览器覆盖变更。未升级产品版本、提交、推送或部署。发布后新生成题图使用调整后的密度；未入库旧预览可主动重新生成。
