# 2026-09-29 助手手机 JPEG 上传修复

## 背景

用户反馈手机上传 IMG-1 后，`deepseek-flash` 返回 `messages[1].image[0]` 图片格式错误，并要求加补丁。完整模式本地任务，基线 `5f5a23b`。只读核对真实记录：14:24 的运行 `run_af50e4d2` 在首轮模型请求收到 HTTP 400，未调用任何工具；已保存 JPEG 为 1080×2627、218788 字节，保存文件与请求中的 data URL 的 sha256 相同。文件缺少 JPEG 结束标记，Pillow 严格解码报告截断；在内存中补 `FF D9` 后可解码。无法仅凭记录确定缺尾发生在手机生成文件还是浏览器读取阶段。

## 行为变化

- 助手页面遇到浏览器可读但缺少结束标记的 JPEG 时，经 canvas 重新编码再上传；正常尺寸、正常结尾的图片仍用原数据，长边超过 4096 的缩放路径不变。
- 草稿区收到缺尾 JPEG 时先补结束标记，再计算 sha256、去重并保存；已有缺尾图片在生成供模型或图片接口使用的 data URL 时临时补标记，不改写旧文件。
- 仅补结束标记的行为不能修复其他损坏的图像数据；旧失败运行不会自动重试。

## 影响文件

- `assets/app/features/assistant/attachments.js`：浏览器端检测并重新编码缺尾 JPEG。
- `omrs/drafts.py`：新图保存与旧图读取时补全结束标记。
- `tests/test_drafts.py`、`tests/e2e/assistant.py`：覆盖新旧图补尾、去重，以及真实浏览器上传并保存完整 JPEG。
- `AI/frontend/assistant.md`、`AI/frontend/architecture.md`、`AI/agent.md`、`AI/drafts.md`、`AI/data.md`、`README.md`：同步当前行为与存储契约。

## 验证

已执行：

- `python3 -m unittest tests.test_drafts.ImageValidationTests tests.test_agent_images -q`：14 个通过；测试文件关闭方式已修正。
- `python3 -m unittest discover -s tests -p 'test_*.py' -q`：349 个通过。测试期间服务替身打印过预期的断连日志，不影响结果。
- `node --test tests/app/*.test.mjs`：367/367 通过。
- `python3 tests/e2e/assistant.py`：57/57 通过，含 390px 手机浏览器中缺尾 JPEG 的重新编码、上传与图片接口读取。
- `python3 tests/app/run_browser.py`：32/32 通过。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组通过。
- `python3 tests/visual/run.py --ref HEAD --pages assistant --out /tmp/omrs-jpeg-visual`：4 组截图，0 组像素差异，0 个页面脚本错误；本次没有布局或文案变化。
- `git diff --check`：通过。

首次本地交付时未执行真实模型联网复测、生产部署与服务重启；当时只在临时 Vault 和测试模型中验证，等待用户单独授权外部状态变更。

## 后续合入、部署与推送

用户随后明确要求“修复记得合并生产和Git,推送GitHub”，授权本地 `main` 合入、生产切换、服务重启及 GitHub 推送。先确认 `origin/main` 是本地 `main` 的祖先，修复分支可快进；`main` 快进到 `25f3c3f`。原有未跟踪 `.playwright-mcp/` 未纳入提交。远端原本落后本地 42 个已有提交；核对提交清单和改动路径后，`git push origin main` 成功，将远端 `main` 从 `52d9152` 推进到 `25f3c3f`。

发布目录 `/root/workspace/releases/omrs-25f3c3f` 由 `git archive 25f3c3f` 生成，`omrs/drafts.py` 哈希与提交内容一致；在发布目录用 `/usr/bin/python3` 执行 `tests.test_drafts.ImageValidationTests`，3/3 通过。停机前生产 v1.33.1、224 道题，助手活动运行与草稿排队任务均为 0，`omrs.service` 正常运行且 `NRestarts=0`。

停止主服务后，将完整真实 Vault 归档至 `/root/workspace/backups/recycle/assistant-jpeg-25f3c3f-20260929T070258Z/vault-before.tar`（190474240 字节，权限 0600），保存原 drop-in、322 个用户文件哈希、配置哈希及 5 个 SQLite 数据库的 `quick_check` 和逐表行数。仅将主服务 drop-in 的发布路径从 `omrs-f803f2d` 改为 `omrs-25f3c3f`，再 `daemon-reload` 与启动；停机到健康检查通过约 0.95 秒。未改 Nginx、Vault 路径、端口或检测服务。

生产验收：`omrs.service` active/running，实际进程从新发布目录启动，`ExecMainStatus=0`、`NRestarts=0`；`/api/status` 返回 ok、v1.33.1、224 道题。线上原 IMG-1 的只读图片接口返回 218790 字节、带 `FF D9` 结束标记；线上 `attachments.js` 与发布目录哈希相同。390px 手机 Chromium 只读打开生产页面，并用合成缺尾 JPEG 调用线上模块，输出为完整 JPEG；没有页面脚本错误或生产写请求。切换后 322 个用户文件和配置哈希保持一致，5 个数据库 `quick_check` 均为 ok，逐表行数无变化，错误级 journal 无记录；检测服务 PID 未变。

仍未执行真实模型付费请求或生产写入试验。旧失败运行不会自动重试；用户需在手机上重新发消息，若原图还有其他损坏则重新上传。代码回退只需把备份中的 `10-release.conf.before` 恢复到原 drop-in、`daemon-reload` 并重启主服务；不要用旧 Vault 覆盖上线后的新数据。
