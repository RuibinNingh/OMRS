# 2026-09-29 手机 JPEG 上传保持图像内容

## 背景与实测

用户反馈“感觉不行啊,”，附上原始手机截图和助手把 IMG-2 识别成纯黑的记录。本轮是前次修复上线后的反馈，基线 `7d51c9b`；沿用同一会话中“修复记得合并生产和Git,推送GitHub”的授权，执行者 Codex，完整模式。

只读检查 16:07–16:08 的对话 `c_2cc31dda`：已保存的 IMG-1、IMG-2 的全部 RGB 像素均为 0，模型对纯黑的描述符合它实际收到的内容。用户本次附上的原图为 1080×3366、399454 字节，含可见题目；真正的主图结束标记在 399185 字节位置，后面还有 267 字节手机相册数据。

前次 `endswith(FF D9)` 检查将这种有效 JPEG 误判为缺尾，触发了不必要的 canvas 重编码。桌面 Chromium 对原图重编码能保留内容，未直接复现实体手机的全黑输出；结合上传文件与代码路径，黑图发生在浏览器处理到上传之间，具体手机浏览器原因仍不确定。前次浏览器测试源图本身就是纯黑，且只检查结束标记，无法发现内容丢失；本轮改用带文字和色块的图，并验证编码字节完全相同。

## 行为变化与影响文件

- `assets/app/features/assistant/attachments.js`：沿 JPEG 标记段定位主图结束位置，跳过含缩略图的元数据段；清除主图后的相册数据，扫描数据缺尾时补结束标记。长边未超过 4096 时直接上传整理后的原编码，避免进入 canvas；超限缩放沿用现有路径。
- `omrs/drafts.py`：新图片保存、已有图片生成 data URL 时使用相同标记规则，避免把缩略图结尾当成主图结尾；保留编码像素。旧存储文件不改写。
- `tests/test_drafts.py`、`tests/app/assistant.test.mjs`、`tests/e2e/assistant.py`：覆盖含缩略图标记、转义字节、重启标记、缺尾、尾数据、不完整元数据段，以及从手机页面上传到读取图片接口的字节一致性。
- `AI/agent.md`、`AI/data.md`、`AI/drafts.md`、`AI/frontend/assistant.md`、`AI/frontend/architecture.md`、`README.md`：同步当前行为；本日志及自动生成索引记录验证。

## 已执行验证

- 用户提供的原图在临时 Vault 的 390px 手机 Chromium 中经过实际 `prepareImageFile`：输出 399187 字节，与 Python 端整理结果逐字节相同；Pillow 比较全部像素差异为 0。用户原图与临时产物未纳入 Git。
- 临时 Vault 仅复制当前 AI 识别配置，使用实际 `describe_image` 请求一次已配置的模型：正确返回“题号 9；a+b≤4、ab≤4；标注答案 A”。未对生产对话追加消息或创建题目。
- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：349/349。
- `node --test tests/app/*.test.mjs`：368/368。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/assistant.py`：58/58；合成图含文字和色块，缺尾及尾数据两种输入在浏览器处理后均与完整 JPEG 逐字节相同，保存后图片接口返回同一编码。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/app/run_browser.py`：32/32。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref 7d51c9b --pages assistant --out /tmp/omrs-jpeg-pixels-visual`：4 组均无像素差异，无脚本错误。

## 限制与下一步

实体手机浏览器未远程连接复测；本轮通过原图字节/像素一致性和真实模型识别验证修正后的路径。此前已保存的纯黑图片没有原文字像素，不能靠补标记恢复，用户须刷新页面后重新上传原图。

## 合入、生产与 GitHub

功能提交 `e339183` 从 `codex/assistant-jpeg-pixels` 快进合入 `main`。`git archive` 生成 `/root/workspace/releases/omrs-e339183`，在发布目录用系统 Python 执行 `tests.test_drafts.ImageValidationTests`，3/3 通过。线上助手、草稿和收件箱均无待运行作业后，停止主服务并将真实 Vault 一致性归档到 `/root/workspace/backups/recycle/assistant-jpeg-pixels-e339183-20260929T081938Z/vault-before.tar`（195471360 字节），保留原 drop-in、323 个用户文件哈希、配置哈希与 5 个数据库检查结果。

主服务 drop-in 切到新发布目录，停机到健康检查通过约 0.97 秒；版本仍为 v1.33.1，225 道题。启动后 active、`NRestarts=0`、`ExecMainStatus=0`，错误级 journal 无记录；323 个用户文件和配置哈希一致，5 个数据库 `quick_check` 为 ok 且所有原有表行数不变。未改 Nginx、检测服务或真实对话内容。线上 390px Chromium 实际加载的新模块处理用户本次原图，输出 399187 字节，与已通过真实模型识别的输入逐字节一致；无脚本错误、无生产写请求，线上附件脚本与发布目录一致。

`git push origin main` 已将 GitHub `main` 从 `7d51c9b` 更新到 `e339183`；本次发布记录与 `AI/environment.md` 同步当前发布路径。文档门禁检查 54 份、0 处问题，`git diff --check` 通过。代码回退时恢复备份中的 drop-in 后重启即可，避免用旧 Vault 覆盖上线后新数据。
