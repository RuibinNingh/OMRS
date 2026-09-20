# 2026-09-13 脱敏源码打包不再基于 Git

## 起因

`AI/changelog.md` 的 v1.18.1 段落写着「新增 `tests/smoke_feedback_result_modal.js`（20 项）」，
但工作区里没有这个文件，`python3 tests/check_docs.py` 因此一直报「引用了不存在的文件」。

原因是打包方式：`omrs/source_export.py` 用 `git ls-files` 取文件清单，
**没提交的文件一律不会进包**。那个测试是上一轮会话新写的，还没 commit，
于是打出来的包里就没有它——包看起来完整，实际缺东西，拿包的人根本无从察觉。
`AI/logs/log.md` 顶上那句「本文件在脱敏源码包里不存在」也是同一个机制的产物。

## 变更摘要

打包口径从「白名单（Git 跟踪的才带）」翻成**「黑名单（默认全带，只剔三类）」**：

1. **个人数据与运行数据**：`错题/`、`临时/`、根目录的 `logs/` 与 `Task/` 与 `tool/`、
   `AI/omrs_work/`、`DEPLOYMENT_SOURCE.json`、`OMRS-EXP-*`；
2. **Git**：`.git/`、`.git-history-backup*/`。源码本身照带，
   `.gitignore` 与 `.gitattributes` 属于源码配置，留着；
3. **缓存与打包产物**：`__pycache__/`、`.pytest_cache/`、`.mypy_cache/`、`.ruff_cache/`、
   `node_modules/`、`.vite/`、`_ai_packages/`、`.playwright-mcp/`、`*.pyc`、`*.pyo`、`*.pyd`、
   `*.log`、`*.tmp`、`*.bak*`、`.DS_Store`、`Thumbs.db`、`desktop.ini`。

几个要点：

- **`AI/logs/` 现在包含在内。** 它是协作上下文不是个人数据，`pack_for_ai.bat` 一直在带它，
  两边口径统一。`logs/` 只在仓库根被剔（对应 `.gitignore` 里 `/logs/` 前面那个斜杠），
  不会误伤 `AI/logs/`。
- **没有 `.git` 也能导出。** 旧实现在非 Git 目录直接抛 400。
- **符号链接一律跳过**，既不跟进目录（会绕出源码树甚至成环）也不打包链接本身。
- **清单同时列出两侧**：`SOURCE_EXPORT_MANIFEST.txt` 里既有「包含文件」也有
  「剔除条目」，分享前可以逐条核对，不用猜。

## 行为与兼容性

- `create_source_export(vault)` 签名与返回结构不变；`meta` 新增 `bytes`（原始体积）。
- 端点 `/api/source/export` 与设置页入口不变。
- 对外分享的风险边界变了一处：**`AI/logs/` 会进包**。这些日志里可能有本地路径或业务细节，
  清单里专门写了一句提醒。若不愿意带，改 `omrs/source_export.py` 的
  `_EXCLUDED_PATH_PREFIXES` 加 `"AI/logs/"` 即可。

## 修改文件

| 文件 | 改动 |
|---|---|
| `omrs/source_export.py` | 重写：`os.walk` 遍历 + 三类黑名单 + 双向清单；新增 `collect_source_files()` |
| `tests/test_source_export.py` | 重写：5 例，重点守「未提交的文件也要进包」 |
| `AI/api.md` | `/api/source/export` 一节按新口径改写 |
| `README.md` | 功能表里「源码协助」一行改写 |
| `AI/logs/log.md` | 顶部那句「本文件在脱敏包里不存在」已不成立，改成说明何时起包含 |

## 验证

- `python3 tests/test_source_export.py` → 5 例全绿：未提交文件进包、
  个人数据 / Git / 缓存被剔、无 `.git` 也能导出、符号链接跳过、清单两侧都在。
- 对当前仓库真跑一次导出：204 个文件、压缩后约 1.6MB；抽查确认
  `tests/check_globals.js`、`web/src/ReportsPanel.vue`、`assets/tokens.css`、
  `AI/logs/log.md`、`assets/dist/README.md` 都在包里，`__pycache__` 与 `.git/` 都不在。

## 遗留

`check_docs.py` 对 `tests/smoke_feedback_result_modal.js` 的报错**本次没有改动**：
那个文件应当在你本地工作区里，只是上一次打包没带出来。等下一次用新实现打包，
它会跟着进来，这条报错自然消失。若届时仍然缺失，那说明文件确实丢了，
再决定是补测试还是改 changelog 的措辞。

## 同步过的文档

`AI/api.md`、根 `README.md`、`AI/logs/log.md`。
