# 设置页图片优化与备份恢复

## 背景

错题附件图片已成为主要占用来源。设置页需要直接展示数据占用，并提供无损压缩、备份导出与备份导入恢复，避免用户为了清理图片手动操作 `错题/附件/`。

## 实现

- 新增 `omrs/optimization.py`：
  - `storage_summary()` 统计“数据链 / 题目文件 / 题目图片”三类大小。
  - `scan_compression()` 启动图片快扫 job，只枚举格式、体积和可深扫范围，不生成优化副本。
  - `start_compression()` 启动深扫压缩后台任务，`get_job()` 供前端轮询进度；深扫阶段才逐张生成优化副本、校验无损并替换更小文件。
  - `create_backup_export()` 打包整个 `错题/` 为下载 zip，并发放本次会话 `backup_token`。
  - `prepare_backup_import()` 校验用户上传 zip，`restore_backup()` 先在临时目录重建索引，验证通过后才替换当前 `错题/`。
- `omrs/cli.py` 的 `serve` 启动阶段检测 Pillow；Windows 下缺失时用弹窗询问是否自动 `pip install --upgrade Pillow`，失败则提示图片优化不可用但继续启动。
- `omrs/server.py` 新增：
  - `GET /api/optimize/summary`
  - `GET /api/optimize/job?id=`
  - `POST /api/optimize/scan`
  - `POST /api/optimize/compress`
  - `POST /api/backup/export`
  - `POST /api/backup/import`
  - `POST /api/backup/restore`
- 设置页新增“优化”卡片：环状图默认显示三类体积；快扫后第三类切换为“待深扫图片”；深扫压缩任务运行时显示进度条、当前文件、已检查体积和已节省体积。

## 安全边界

- 压缩前必须已通过设置页导出备份并获得 `backup_token`，否则后端拒绝启动压缩。
- 压缩前端有二次确认；恢复备份也先预览 zip，再二次确认。
- 备份 zip 不保存到 `错题` 数据目录，由浏览器下载给用户保存。
- 恢复 zip 必须以 `错题/` 为顶层目录，禁止路径穿越；恢复前先在临时目录重建索引，坏备份不会覆盖现有数据。
- PNG 替换前校验尺寸、模式和像素完全一致；JPG/JPEG 不用 Pillow 重编码冒充无损。

## 验证

- `python -m compileall omrs omrs_engine.py`
- `node --check assets/app.js`
- 临时 vault 冒烟：统计三类大小、快扫 PNG 深扫范围、导出 zip、导入预览、启动深扫压缩 job 并确认节省体积。
- 临时 vault 恢复：用合法 Ledger 备份覆盖被改坏的题目文件，恢复后内容与备份一致。

## UI 调整

- “关于”卡片上移到设置页首行右侧，与“服务设置”对齐，避免被优化块压到页面下方。
- 环状图增加外侧分类标签和引线，默认显示“数据链 / 题目文件 / 题目图片”，快扫后第三类同步切换为“待深扫图片”。
- `scanOptimizeImages()` 点击后立即显示快扫进度条并轮询 scan job；确认压缩后复用进度条显示深扫压缩的逐文件进度。
