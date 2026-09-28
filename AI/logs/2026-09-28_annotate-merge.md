# 2026-09-28 框选标注页合入当前版本

## 背景

用户要求：「更新生产目录,这个版本是落后的,但是添加了数据标记,合并」。输入为 `OMRS-annotate-page-20260928.zip`。完整模式从工作区 `31b59f4` 合入；生产服务开工时运行 `/root/workspace/releases/omrs-f863761`，真实 Vault 在 `/root/workspace/apps/OMRS`。压缩包里的任务日志是受限模式交付记录，按内容核对源码差异，不整包覆盖当前版本。

## 行为变化

- 新增独立 `/annotate` 页，用于上传截图并框选「题目 / 答案」，支持批量上传、快捷键、完成状态与 YOLO / JSONL 导出。数据独立存于 `错题/.omrs/annotate/`。
- 录入题目页「AI 训练」工作区显示标注集进度，并在新标签页打开标注页。
- 当前分支的 AI 草稿 P1-1 至 P1-3、展示板 UI 和计划状态保持当前版本；没有采用压缩包中较旧的同名计划、环境文档和 AI 助手文件。

## 影响文件

- 代码与测试：新增 `omrs/annotate.py`、`assets/app/annotate.html`、`assets/app/features/annotate/`、三层标注测试；修改 `omrs/server.py`、训练页三个文件及 `tests/check_docs.py`。
- 文档：同步 API、数据、前端、访问控制、维护环境、源码到文档映射、根 README 和自动生成的路由表；新增 `AI/frontend/annotate.md`，保留受限模式原任务日志并生成日志索引。

## 验证

已实际执行：

- `env -u OMRS_SYSTEMD_SERVICE python3 -m unittest discover -s tests -p 'test_*.py' -q`：226 例 OK。
- `node --test tests/app/*.test.mjs`：337 通过 / 0 失败。
- `python3 tests/check_ui.py`：0 处问题；`python3 tests/check_contrast.py`：58 组、0 组不达标。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/app/run_browser.py`：32 通过 / 0 失败。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/annotate.py`：34/34 通过；`env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/create.py`：80/80 通过。
- `env -u OMRS_SYSTEMD_SERVICE python3 tests/visual/run.py --ref HEAD --out /tmp/omrs-annotate-visual-20260928`：48 档截图中 0 档有差异，脚本错误无；默认页组不含 AI 训练工作区与独立标注页，这两处由上述 E2E 的主路径与四档审计覆盖。
- `python3 tests/check_docs.py --write-routes` 与 `--write-log-index` 已生成路由表和日志索引；`python3 tests/check_docs.py --diff HEAD`：47 个文档、0 处问题，2 条既有文件体积提醒。
- 从提交 `63adaded4b83065c59f14145eaa1fcb3e5c9ca0c` 归档到 `/root/workspace/releases/omrs-63adade`，与工作区的 `omrs/server.py` 和标注页入口文件哈希一致；在发布目录执行 `env -u OMRS_SYSTEMD_SERVICE python3 tests/e2e/annotate.py`：34/34 通过，使用临时 Vault 与随机高端口。

未执行：发布目录切换、生产重启、生产浏览器验收。开工前实测生产服务仍从 `/root/workspace/releases/omrs-f863761` 运行，`/api/status` 为 `ok`、v1.28.1、217 题，真实 Vault 路径不变。

## 发布待办

将 `/etc/systemd/system/omrs.service.d/10-release.conf` 中的发布路径从 `omrs-f863761` 换成 `omrs-63adade`，保留 `--vault /root/workspace/apps/OMRS` 和端口 8471；`daemon-reload`、重启服务后核对 `/api/status`、`/annotate`、训练页入口、数据文件哈希与日志。旧发布目录保留用于代码回退，不以旧数据覆盖真实 Vault。生产 systemd 与重启按根 `AGENTS.md` 要求另待用户明确授权。

用户确认：「暂不切换，保留已验证的发布目录」。因此本轮不修改 systemd、不重启生产、不做生产页验收；`omrs-63adade` 作为已验证但未启用的发布目录保留，生产仍运行 `omrs-f863761`。
