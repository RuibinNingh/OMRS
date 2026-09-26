# 2026-09-24 脱敏源码导出脱离 Git

## 变更摘要

设置页的脱敏源码 ZIP 现在直接从当前工作区收集项目源码、测试和文档；不调用 `git ls-files`，也不要求目录含 `.git`。允许的根目录项目文件和源码目录按固定规则扫描，未提交的新源码会进入导出包。仍排除题库、临时工作目录、运行日志、`AI/logs/`、缓存、构建产物、生成导出文件及符号链接。ZIP 内清单列出实际包含文件，并提示分享前核对源码内容。

## 行为与兼容性

`GET /api/source/export` 和下载文件名形式不变。无源码文件时返回 400。文件选择改为源码目录加类型允许列表；新建其他顶层目录或未允许类型的源码，需要先更新 `omrs/source_export.py` 的规则。既有的 `AI/logs/` 排除规则保留。

## 修改文件

- `omrs/source_export.py`：改为文件系统扫描、允许列表和符号链接过滤。
- `tests/test_source_export.py`：验证无 Git 的未提交文件、私有文件、缓存与符号链接边界。
- `omrs_dashboard.html`：说明下载范围与分享前核对要求。
- `AI/api.md`、`AI/export.md`、`AI/frontend.md`、`AI/README.md`、`README.md`：同步当前导出行为与文档索引。
- `AI/logs/log.md`：加入本记录索引。

## 验证

- `python3 -m unittest tests/test_source_export.py`：3 例通过。
- `python3 -m py_compile omrs/source_export.py`：通过。
- 当前工作区实际生成 ZIP：300 个文件；检查包含未跟踪的 `omrs/security.py`、`tests/test_security.py`、`AI/security.md`，未出现题库、日志或缓存路径。
- 临时本机 HTTP 服务的 `GET /api/source/export` 返回 200，ZIP 包含清单和未跟踪测试。
- 用本机 Chromium 进入设置页，点击“下载脱敏源码”：浏览器成功下载 ZIP，状态显示“已下载”，包内包含 `SOURCE_EXPORT_MANIFEST.txt` 与未跟踪测试文件。
- `python3 tests/check_docs.py`：通过。
