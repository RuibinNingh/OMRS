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

首轮未执行（后续已完成，见下节）：发布目录切换、生产重启、生产浏览器验收。开工前实测生产服务仍从 `/root/workspace/releases/omrs-f863761` 运行，`/api/status` 为 `ok`、v1.28.1、217 题，真实 Vault 路径不变。

## 发布准备与暂缓

当时准备将 `/etc/systemd/system/omrs.service.d/10-release.conf` 中的发布路径从 `omrs-f863761` 换成 `omrs-63adade`，保留 `--vault /root/workspace/apps/OMRS` 和端口 8471；`daemon-reload`、重启服务后核对 `/api/status`、`/annotate`、训练页入口、数据文件哈希与日志。旧发布目录保留用于代码回退，不以旧数据覆盖真实 Vault。生产 systemd 与重启按根 `AGENTS.md` 要求另待用户明确授权。

用户确认：「暂不切换，保留已验证的发布目录」。因此本轮不修改 systemd、不重启生产、不做生产页验收；`omrs-63adade` 作为已验证但未启用的发布目录保留，生产仍运行 `omrs-f863761`。

## 合入 main

用户补充：「我的意思是这个要合并main的」。复核 `main=31b59f4` 是 `ai-draft=554a8ec` 的祖先，差集只有本任务的 `63adade`、`a33ac13`、`554a8ec` 三个提交；执行 `git switch main`、`git merge --ff-only ai-draft` 后，本地 `main` 到 `554a8ec`。当时没有推送 `origin/main`，也没有切换或重启生产服务。

## 生产切换

用户随后明确要求：「切换」。完整模式按此授权，将 systemd drop-in 的发布路径从 `omrs-f863761` 改为 `omrs-63adade`，保留真实 Vault `/root/workspace/apps/OMRS` 和 TCP 8471；执行 `systemctl daemon-reload` 与 `systemctl restart omrs.service`。旧发布目录保留作代码回退。配置与 `config.json`、`boards.json`、`mastery_data.csv`、`labels.json`、`auth.json` 备份在 `/root/workspace/backups/recycle/annotate-deploy-20260928T215735`，备份目录权限为 0700；生产验收时这五个数据文件与备份哈希一致。

已实际执行的生产验收：`systemctl show omrs.service` 为 active，主进程从 `/root/workspace/releases/omrs-63adade/omrs_engine.py` 运行；`GET /api/status` 返回 200、`ok`、v1.28.1、217 题，Vault 路径不变；`GET /annotate`、`GET /api/annotate/stats` 与标注页 JS 均返回 200，空标注集统计为 0，JS 内容哈希与发布目录一致。真实浏览器从「录入题目 → AI 训练 → 打开标注页」进入新标签页，空态、文件和文件夹上传入口可见，页面脚本错误为 0。用可信本机代理头模拟未登录远端：`/annotate` 返回 302 到 `/login?next=%2Fannotate`，统计接口返回 401。重启后的错误级 journal 无记录。

未执行：真实远端设备登录与真实训练流程；浏览器生产验收只走只读入口，没有向真实 Vault 上传测试图片。`origin/main` 未推送。若需回退代码，将 drop-in 发布路径改回 `omrs-f863761`，重新加载 systemd 并重启；不以旧备份覆盖可能已新增的标注数据。
