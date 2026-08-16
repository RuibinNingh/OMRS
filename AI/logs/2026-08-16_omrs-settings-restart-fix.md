# OMRS 设置页重启修复

- 日期：2026-08-16
- 范围：`POST /api/restart`、systemd 服务生命周期

## 现象

从设置页点击“立即重启”后，前端显示“重启指令已发出”，但页面刷新后无法连接 OMRS。

## 根因

旧实现通过后台线程关闭 HTTP server，再 `Popen` 当前启动命令。OMRS 实际由 `omrs.service` 管理，unit 使用 `Restart=on-failure`；主进程正常退出时 systemd 认为这是成功停止，不会自动拉起，后台子进程也不会成为可靠的服务实例。

## 修复

- `omrs/server.py`：检测 `OMRS_SYSTEMD_SERVICE`，由 `systemctl restart --no-block` 交给 systemd 执行重启。
- `/etc/systemd/system/omrs.service`：增加 `OMRS_SYSTEMD_SERVICE=omrs.service` 环境变量。
- 手工启动 OMRS 时保留原来的自重启回退路径。
- 修改前的本地回滚备份已留存。

## 验收

- `systemd-analyze verify /etc/systemd/system/omrs.service`：通过。
- Python 编译检查、Node 语法检查：通过。
- OMRS 单元测试：15/15 通过。
- 通过真实 `POST /api/restart` 回归：旧 PID 退出，新 PID 拉起，服务恢复 `active`，`/api/status` 返回 `status=ok`。
- Hermes `browser_exec` 打开 OMRS 设置页：运行状态显示“运行中”。
