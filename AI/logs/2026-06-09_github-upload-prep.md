# GitHub Upload Prep

## 背景

准备把 OMRS 上传到 GitHub，需要清理发布边界：保留程序代码、前端资源、AI 项目文档和技能说明；屏蔽个人错题、学习记录、报告、临时文件与运行缓存。

## 变更

- 新增根目录 `.gitignore`。
- 屏蔽 `错题/`、`临时/`、根目录运行日志 `/logs/`、`__pycache__/`、Python 字节码、临时/备份文件。
- 屏蔽 `AI/omrs_work/`，避免上传 AI 处理过程中截取的题目/答案图片。
- 预留 `.git-history-backup*/` 忽略规则，用于本地隔离旧 Git 历史后重新初始化仓库。

## 上传边界

建议上传：

- `omrs/`
- `assets/`
- `AI/`
- `Skills/`
- `omrs_dashboard.html`
- `omrs_engine.py`
- `run.bat`
- `.gitignore`

不上传：

- `错题/` 个人题库、附件、`.omrs` 学习数据和报告
- `临时/`
- 根目录运行日志 `/logs/`
- `__pycache__/`
- `AI/omrs_work/`
