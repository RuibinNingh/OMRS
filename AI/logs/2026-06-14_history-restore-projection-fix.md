# 历史恢复投影修复

## 背景

历史页支持 `review.retract/restore`、`session.retract/restore` 后，投影器原先只从当前活跃 `history` 行重算 mastery。问题是撤销动作会先把反馈行从活跃历史里移除，后续 restore 已经没有原始反馈可重放，导致恢复按钮追加了 commit 但 mastery/history 不能真正恢复。

## 改动

- `omrs/projections.py`：在投影 state 中保留原始 `review.batch_submit` commit 与 legacy history；修正重算时从 mastery/tag baseline 出发，重放原始反馈提交并按当前撤销/替换集合生成活跃历史。
- `omrs/projections.py`：新增 `ledger_retraction_state()`，由后端基于完整 Ledger 返回当前撤销集合，避免前端只加载最近节点时误判撤销状态。
- `omrs/server.py`：历史修正 API 追加前校验 payload，拒绝不存在的反馈提交、越界 index、未知 Session、非法分数/布尔值和不存在的 restore seq。
- `assets/schedule.js`：历史页优先使用后端 `retraction_state`，旧响应回退到前端本地推导。
- `tests/test_history_projection.py`：新增投影回放测试，覆盖单条反馈恢复、Session 恢复、撤销后题目标签回到基线、反馈替换重放。

## 验证

- `python -m unittest tests.test_history_projection`
- `python -m compileall -q omrs tests`
- `node --check assets/schedule.js`
- 对当前 vault 执行 `rebuild_projection()` 后，`verify_ledger()` 仍为 `valid=true`，新反馈活跃行与 Ledger 推导一致。
