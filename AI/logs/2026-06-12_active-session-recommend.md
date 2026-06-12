# active-session-recommend

## 背景

排查项目 Bug 时发现：旧版 `POST /api/schedule` 创建 Session 会排除仍处于 `active` 状态的旧 Session 题目，但新的常规复习推荐入口 `GET /api/recommend` 没有传入同样的排除集。当前运行数据中，推荐结果与活动 Session 出现大量 UID 重叠，可能让同一题进入多个进行中 Session。

## 修改

- `omrs/sessions.py`
  - 新增 `active_session_uids(vault)`，公开复用 active Session UID 排除集。
  - `create_session_from_selection()` 在确认生成前检查所选 UID 是否已存在于 active Session；若存在，返回明确错误而不是创建重复 Session。
- `omrs/server.py`
  - `/api/recommend` 调用 `generate_recommendations()` 时传入 `exclude_uids=active_session_uids(...)`。
- `AI/algorithm.md` / `AI/api.md`
  - 同步说明推荐接口和确认接口的 active Session 防重复行为。

## 验证

- 修复前：当前 1 个 active Session 含 42 个 UID；推荐 65 个 UID 中有 36 个与 active Session 重叠。
- 修复后：直接以 `exclude_uids=active_session_uids('.')` 调用推荐，重叠数为 0。
- `python -m compileall -q omrs omrs_engine.py`
