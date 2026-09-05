# 2026-09-05 收件箱数据集默认版式

## 变更摘要

收件箱新上传图片的版式默认改为 `zuoyebang`（界面显示“作业帮截图”）。现有数据集中 7 张 `other` 记录已统一改为 `zuoyebang`，这些记录均为同一批已录入的作业帮截图。

## 行为与兼容性

- `layout` 可选值仍为 `zuoyebang | photo | plain | other`。
- 仅改变新上传默认值；处理页仍可手动改选其他版式。
- 本次生产数据更新前已备份 `inbox.db` 与 `annotations.jsonl`。
- 生产数据更新通过追加 `layout.update` 标注事件留痕，不改题库 Markdown、Ledger 或题目索引。

## 修改文件

- `omrs/inbox.py`：新上传默认 `zuoyebang`。
- `assets/inbox.js`：旧记录缺失版式时前端默认显示作业帮。
- `tests/test_inbox.py`：验证新上传默认版式。
- `AI/inbox.md`、`AI/data.md`：同步数据集版式说明。
- `README.md`：同步用户可见的默认版式说明。
- `错题/.omrs/inbox/inbox.db`：7 条 `other` 改为 `zuoyebang`（数据目录不纳入 Git）。

## 验证

- 修改前：`other=7`、`zuoyebang=3`。
- 修改后：通过 `/api/inbox/dataset/stats` 回读确认 `other=0`、`zuoyebang=10`。
- 备份：`/root/workspace/apps/releases/OMRS-inbox-layout-rollback-20260905-234749/`。
- `python3 -m unittest tests.test_inbox`：14 项通过。
- `python3 -m unittest discover -s tests`：59 项通过。
- `node --test tests/*.js`：36 项通过；1 项既有行动推荐日期敏感测试因当前日期跨日失败，未涉及本次改动。
- `node --check assets/inbox.js`：通过。
- `git diff --check`：通过。

## 同步过的文档

- `AI/inbox.md`
- `AI/data.md`