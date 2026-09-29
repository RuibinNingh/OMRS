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

未执行：真实模型联网复测、生产部署与服务重启；本任务只在临时 Vault 和测试模型中验证，外部状态变更须另行授权。
