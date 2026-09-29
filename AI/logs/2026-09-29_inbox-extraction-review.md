# 2026-09-29 收件箱一键提取与人工审核

## 背景

执行者：Codex，完整模式。用户要求取消框选前的保存方式选择，默认交给 AI 一次返回文本或不能提取的结果；保留图片由程序处理，人工审核后可改保存方式，入口降级；「转换文本」改为「一键提取」。用户已授权完成后提交 main 并部署生产。基线 75ed848，生产旧发布 6437525。

原工作区已有 AI/logs/log.md 的改动、两份 2026-09-28 未跟踪日志和 .playwright-mcp/，保留且不纳入本任务提交。

## 行为变化

提取前不显示保存方式；一键提取处理当前图未完成区域，单次模型调用同时判断和转录。可转写文本，否则保留裁图；人工可编辑正文、改存图片、切回保留的文字或补录。重新提取重置 AI 判断，自动策略不再自动就绪。失败与不能提取区分，空正文／无效判断需重试。更改框位后旧结果失效；后台写回校验区域快照，不覆盖新修改。

保持现有存储结构与配置键名，旧数据不迁移；模型调用只在临时 Vault 的确定性替身中验证，实际模型识别质量另计。

## 影响文件

录入页 process 系列、inbox-ops/store、train-view；后端 inbox 与 ai_assist；对应单测和录入 E2E；README、AI/inbox、api、data、前端 create/architecture 文档及版本文件。版本 v1.33.0。最终以 git diff --name-status 复核。

## 验证

已实际执行：

- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：343 项通过。
- `node --test tests/app/*.test.mjs`：365 项通过；浏览器组件 `tests/app/run_browser.py`：32 项通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/create.py`：96/96。真实隔离服务、Chromium、临时 Vault、随机端口；仅外部模型使用确定性替身，覆盖一次调用、部分失败重试、不能提取、人工补录、文本与图片来回切换、人工就绪与创建。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/drafts.py`：44/44，共用框选画布的草稿回归通过。
- `tests/check_ui.py`：0 问题；`tests/check_contrast.py`：58 组全部通过；`tests/check_docs.py --diff HEAD`：0 问题（两项既有文件大小提醒）；`git diff --check` 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref 75ed848 --pages create --create-stage process --out /tmp/omrs-extract-visual-final`：4/4 对比、无页面脚本错误。桌面浅/深差异 1.374%/1.349%，手机浅/深 7.417%/7.707%；逐档差异均为删除三选一与每区域提取按钮、增加一键提取说明、底部按钮和快捷键文案及版本号，手机内容高度随控件减少而缩短。已目视桌面/手机浅色截图，提取结果态另由 E2E 四档审计覆盖，无溢出或小点击目标。

首轮 E2E 因测试按「删除」寻找带完整 aria-label 的按钮失败，后续计数随未清理测试图片连带失败；修正测试为选中区域后 Delete，重跑 96/96。最后两处文案调整后再次运行视觉浏览器验证通过。

未执行：真实外部模型识别质量与真实远端设备登录；不把替身测试当作模型质量验收。

## 部署

待门禁完成后，从 main 提交生成独立发布目录，备份生产 Vault 和原 drop-in，再切换主服务并验证。检测服务及模型不变。
