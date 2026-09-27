# 路由总表（自动生成）

> 由 `python3 tests/check_docs.py --write-routes` 从 `omrs/server.py` 生成，勿手改。
> 请求体、响应字段与错误语义见「说明」列的文档；`AI/api.md` 为主。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/ai-recognize` | `AI/api.md`、`AI/frontend/create.md`、`AI/inbox.md`等 |
| GET | `/api/analytics` | `AI/api.md`、`AI/algorithm.md`、`AI/changelog.md`等 |
| POST | `/api/auth/activity` | `AI/api.md`、`AI/security.md` |
| POST | `/api/auth/disable` | `AI/api.md` |
| POST | `/api/auth/login` | `AI/api.md` |
| POST | `/api/auth/logout` | `AI/api.md` |
| POST | `/api/auth/pin` | `AI/api.md` |
| GET | `/api/auth/session` | `AI/api.md`、`AI/frontend/settings.md`、`AI/security.md` |
| POST | `/api/auth/warning-ack` | `AI/api.md` |
| POST | `/api/backup/export` | `AI/api.md`、`AI/frontend/settings.md` |
| POST | `/api/backup/import` | `AI/api.md`、`AI/frontend/settings.md` |
| POST | `/api/backup/restore` | `AI/api.md`、`AI/frontend/settings.md` |
| GET | `/api/board` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/create` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/delete` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/duplicate` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/folder/create` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/folder/delete` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/folder/update` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/items/add` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/items/remove` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/move` | `AI/api.md`、`AI/board.md`、`AI/changelog.md` |
| POST | `/api/board/printed` | `AI/api.md`、`AI/board.md`、`AI/data.md`等 |
| POST | `/api/board/printed/reset` | `AI/api.md`、`AI/board.md` |
| POST | `/api/board/update` | `AI/api.md`、`AI/board.md`、`AI/frontend/board-ui.md` |
| GET | `/api/boards` | `AI/api.md`、`AI/board.md`、`AI/changelog.md` |
| GET/POST | `/api/config` | `AI/api.md`、`AI/algorithm.md`、`AI/data.md`等 |
| POST | `/api/confirm-schedule` | `AI/api.md`、`AI/algorithm.md`、`AI/data.md`等 |
| POST | `/api/create` | `AI/api.md`、`AI/data.md`、`AI/frontend/create.md` |
| POST | `/api/export` | `AI/api.md`、`AI/board.md`、`AI/changelog.md`等 |
| GET | `/api/export-review` | `AI/api.md`、`AI/frontend/records.md` |
| POST | `/api/feedback` | `AI/api.md`、`AI/algorithm.md`、`AI/changelog.md`等 |
| GET | `/api/history` | `AI/api.md`、`AI/frontend/dashboard.md`、`AI/frontend/records.md`等 |
| POST | `/api/history/review/replace` | `AI/api.md`、`AI/ledger.md` |
| POST | `/api/history/review/restore` | `AI/api.md`、`AI/ledger.md` |
| POST | `/api/history/review/retract` | `AI/api.md`、`AI/ledger.md` |
| POST | `/api/history/session/restore` | `AI/api.md`、`AI/ledger.md` |
| POST | `/api/history/session/retract` | `AI/api.md`、`AI/ledger.md` |
| POST | `/api/history/state/restore` | `AI/api.md`、`AI/ledger.md` |
| GET | `/api/image` | `AI/api.md`、`AI/data.md`、`AI/frontend/library.md`等 |
| POST | `/api/inbox/cleanup` | `AI/inbox.md` |
| POST | `/api/inbox/commit` | `AI/inbox.md` |
| POST | `/api/inbox/crops` | `AI/inbox.md` |
| GET | `/api/inbox/dataset/export` | `AI/inbox.md` |
| GET | `/api/inbox/dataset/stats` | `AI/inbox.md` |
| POST | `/api/inbox/discard` | `AI/inbox.md` |
| GET | `/api/inbox/item` | `AI/inbox.md` |
| POST | `/api/inbox/item/update` | `AI/inbox.md` |
| GET | `/api/inbox/items` | `AI/inbox.md` |
| GET | `/api/inbox/job` | `AI/inbox.md` |
| POST | `/api/inbox/jobs` | `AI/inbox.md` |
| GET | `/api/inbox/raw` | `AI/inbox.md` |
| GET | `/api/inbox/slice-plan` | `AI/inbox.md` |
| POST | `/api/inbox/upload` | `AI/frontend/create.md`、`AI/inbox.md` |
| POST | `/api/label/delete` | `AI/api.md`、`AI/labels.md` |
| POST | `/api/label/merge` | `AI/api.md`、`AI/labels.md` |
| POST | `/api/label/save` | `AI/api.md`、`AI/labels.md` |
| GET | `/api/labels` | `AI/api.md`、`AI/labels.md` |
| GET | `/api/ledger/verify` | `AI/api.md`、`AI/ledger.md` |
| POST | `/api/optimize/compress` | `AI/api.md` |
| GET | `/api/optimize/job` | `AI/api.md`、`AI/frontend/settings.md` |
| POST | `/api/optimize/scan` | `AI/api.md` |
| GET | `/api/optimize/summary` | `AI/api.md`、`AI/frontend/settings.md` |
| GET | `/api/question` | `AI/api.md`、`AI/changelog.md`、`AI/data.md`等 |
| POST | `/api/question/delete` | `AI/api.md`、`AI/frontend/library.md` |
| POST | `/api/question/labels` | `AI/api.md`、`AI/labels.md` |
| POST | `/api/question/markdown` | `AI/api.md`、`AI/frontend/library.md`、`AI/frontend/qview.md` |
| POST | `/api/question/move` | `AI/api.md`、`AI/frontend/library.md` |
| GET | `/api/question/raw` | `AI/api.md`、`AI/frontend/library.md`、`AI/frontend/qview.md` |
| POST | `/api/question/resume` | `AI/api.md`、`AI/frontend/library.md` |
| POST | `/api/question/suspend` | `AI/api.md`、`AI/frontend/library.md` |
| POST | `/api/questions/labels` | `AI/api.md`、`AI/labels.md` |
| GET | `/api/recommend` | `AI/api.md`、`AI/algorithm.md`、`AI/changelog.md`等 |
| POST | `/api/report/create` | `AI/api.md`、`AI/frontend/records.md` |
| POST | `/api/report/delete` | `AI/api.md`、`AI/frontend/records.md` |
| GET | `/api/report/view` | `AI/api.md`、`AI/data.md`、`AI/frontend/records.md` |
| GET | `/api/reports` | `AI/api.md`、`AI/frontend/records.md` |
| POST | `/api/restart` | `AI/api.md`、`AI/environment.md`、`AI/frontend/settings.md` |
| GET/POST | `/api/scan` | `AI/api.md`、`AI/security.md` |
| POST | `/api/schedule` | `AI/api.md` |
| GET | `/api/session` | `AI/api.md`、`AI/changelog.md`、`AI/frontend/review.md` |
| POST | `/api/session/delete` | `AI/api.md`、`AI/ledger.md` |
| GET | `/api/sessions` | `AI/api.md`、`AI/changelog.md` |
| GET | `/api/source/export` | `AI/api.md`、`AI/changelog.md`、`AI/frontend/settings.md` |
| GET | `/api/stats` | `AI/api.md`、`AI/algorithm.md`、`AI/changelog.md`等 |
| GET | `/api/status` | `AI/api.md`、`AI/frontend/settings.md`、`AI/security.md` |
| GET | `/api/tree` | `AI/api.md`、`AI/changelog.md`、`AI/frontend/architecture.md`等 |
| POST | `/api/workspace/scan` | `AI/api.md`、`AI/ledger.md` |
| GET | `/login` | `AI/inbox.md`、`AI/security.md` |
| GET | `/m` | `AI/api.md`、`AI/inbox.md`、`AI/security.md` |

按前缀分派（具体子路由见上表或对应文档）：

- POST `/api/auth/…`
- GET/POST `/api/inbox/…`
- GET `/assets/…`
