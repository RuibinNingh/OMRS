# 2026-10-18 作业帮静态SVG附图兼容

## 背景

用户先提供zuoyebang.zip与「附图无法解码，原内容已保留」截图要求排查，定位后要求「补一下吧,完成提交GitHub」。执行者Codex，完整模式；本任务从GitHub main的19b31cf建立独立工作区与codex/zuoyebang-svg-images分支。开工时原工作区的识别中提示等未提交改动及未推送的cfd2727设置页提交保留，本次提交仅纳入SVG修复。版本保持v2.8.2。

## 原因与行为变化

附件内失败候选的D选项含三张SVG温度公式。原链接均可下载并由Chromium解码，Pillow因不支持SVG抛出UnidentifiedImageError，导致整个候选失败。既有成功记录使用其它候选，不能证明这个带SVG的候选已成功。

附图现在按真实内容识别静态SVG，支持远程下载与base64内联；经过独立XML、元素／属性／样式与内部引用校验后保留原字节，以图片上下文交给既有Chromium输出完整PNG。现有PNG／JPEG／GIF／WebP验证和来源保留规则继续使用，不增加依赖或HTTP字段。正式题目仍保存PNG，不把外部SVG作为可执行文档提供。

拒绝脚本、事件、动画、外部资源、外来命名空间、未知元素／样式、DTD／实体声明、处理指令、循环与缺失引用；限制根尺寸、1万个节点、64层与5万个引用展开节点。沿用单图12MiB、总图80MiB和4000万输入像素预算。未知或不安全内容整体失败，不静默删图；正文直接嵌入SVG仍返回render_unsupported。

## 影响文件

- omrs/zuoyebang/svg.py：静态SVG验证和资源预算；omrs/zuoyebang/html.py：解码分流、原字节内联与单图字节复核。
- tests/test_zuoyebang_svg.py：13项格式、安全、资源及真实Chromium像素回归；tests/zuoyebang_fixtures.py：纯合成SVG路径公式。
- tests/e2e/zuoyebang.py：答案附图改用合成SVG，核对受鉴权PNG中实际绘入的着色路径，继续执行既有核对、创建和恢复流程。
- AI/zuoyebang.md、AI/security.md、AI/api.md、AI/frontend/architecture.md和根README.md：同步支持范围、安全边界、错误语义与验证路径；本日志及自动生成的索引记录实际交付。

## 已实际执行的验证

以下Python命令均使用 `/root/workspace/apps/releases/omrs-zyb-deps-20261011/.venv/bin/python`，启动前清除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL。所有服务使用临时Vault和随机高端口；不访问生产题库、官方搜题或付费模型。

1. `python -m unittest tests.test_zuoyebang_svg tests.test_zuoyebang tests.test_zuoyebang_render tests.test_zuoyebang_geometry -v`：56项通过，退出0；日志 `/tmp/omrs-svg-backend.log`。包含13项新增SVG测试与真实Chromium图片绘制。初次单跑13项时，结构超限异常被ValueError分支误转为image_invalid，随后显式保留ZybError，完整56项重新运行通过。
2. `OMRS_ZYB_SHOTS=/tmp/omrs-svg-e2e python -u tests/e2e/zuoyebang.py`：157/157项通过，退出0；日志 `/tmp/omrs-svg-e2e.log`。实际上传、附图验证、Chromium长图、鉴权图片读取、识别部分失败重试、人工核对、幂等创建、刷新恢复、旧预览升级以及浅深主题与320–2550px路径通过，浏览器无脚本错误。
3. `node --test tests/app/create-zyb.test.mjs tests/app/zyb-text.test.mjs`：26项通过，退出0；日志 `/tmp/omrs-svg-node.log`。
4. 原失败候选的原文与三份已下载SVG在隔离目录通过正式candidate_html和render_documents执行，未替换解码器：题干1080×2286、3张附图，答案1080×183。输出SHA256逐字节等于此前仅绕过解码器的诊断对照，说明校验没有删改公式；人工查看题干PNG确认-183℃、-196℃、-269℃完整。产物 `/tmp/omrs-zyb-svg-investigation-6a_krstt/fixed/`；真实原题与第三方SVG不进入Git。
5. `python tests/visual/run.py --ref 19b31cf --pages create --create-stage zuoyebang --out /tmp/omrs-svg-visual`：浅深主题、桌面／手机共4对截图，0对差异，无页面脚本错误，退出0；报告 `/tmp/omrs-svg-visual/report.html`。该对照确认工作台布局保持，SVG修复效果由原题实际输出及上述像素断言验证。
6. `python3 tests/check_docs.py --write-log-index`已生成索引；`python3 tests/check_docs.py --diff HEAD`通过，146份文档、0问题、3条既有体积提醒。`git diff --check`通过，已复核本任务变化范围。

## 最新主分支集成验证

收尾时GitHub main新增5d2abb8识别中提示提交，已将本修复rebase到该提交。唯一冲突为日志索引，按规范重新生成，保留双方日志；业务代码和模块文档自动合并。复核12个本任务文件，并确认原工作区9份开工文件哈希与仓库外副本一致。

合入最新主分支后重新执行同一主E2E，157/157通过、退出0，日志 `/tmp/omrs-svg-e2e-final.log`，产物 `/tmp/omrs-svg-e2e-final/`。视觉命令改为 `--ref 5d2abb8 --out /tmp/omrs-svg-visual-final`，4对均无差异且无页面脚本错误、退出0。文档门禁以 `--diff 5d2abb8` 再验通过：146份、0问题、3条既有体积提醒。后端及Node源码未被主分支更新触及，保留上述56项与26项已执行结果，不将它们重复计数。

## 未执行与边界

未执行全仓后端／Node、网关全套、实体手机、真实账号与付费模型验证：本次仅扩展OMRS附图解码，网关与AI调用契约保持。前端源码和样式没有变化；浏览器验收使用真实页面及长图像素断言。没有升级版本、修改生产配置或重启生产服务；本次授权范围为修复并提交GitHub。
