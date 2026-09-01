# 2026-09-01 下载脱敏源码

## 变更摘要
在 OMRS「设置 → 服务设置」新增“下载脱敏源码”按钮。点击后从后端下载源码 ZIP，便于提交问题或请求协助。

## 行为与兼容性
- 新增 `GET /api/source/export`。
- 导出内容只读取 Git 已跟踪文件，放在 ZIP 的 `OMRS/` 目录下。
- 排除 `错题/`、`临时/`、`AI/logs/`、`AI/omrs_work/`、`logs/`、`DEPLOYMENT_SOURCE.json` 和 `OMRS-EXP-*` 生成文件；不读取未跟踪文件。
- ZIP 附带 `SOURCE_EXPORT_MANIFEST.txt`，列出包含文件和排除范围。
- 不影响现有完整题库备份和复盘材料导出。

## 修改文件
- `omrs/source_export.py`
- `omrs/server.py`
- `omrs_dashboard.html`
- `assets/app.js`
- `tests/test_source_export.py`
- `AI/api.md`
- `AI/frontend.md`
- `README.md`

## 验证
- 单元测试覆盖源码包生成、个人目录/生成文件排除和清单。
- 部署后通过生产 HTTP 接口下载 ZIP，并检查 ZIP 清单不含个人目录。

## 同步过的文档
已同步 `AI/api.md`、`AI/frontend.md` 和根 `README.md`。
