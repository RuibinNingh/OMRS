# 2026-09-23 收件箱提取完成打断框选修复

## 变更摘要

文本提取任务完成时不再调用整页 `ibLoad()` 重画处理画布。前端只获取发起提取的图片，将提取结果同步到对应区域；正在画另一张图的框对象与指针交互保持不变。若仍在原图编辑，提取字段合并到对应区域，拖动期间推迟右栏刷新。

## 行为与兼容性

右下角完成提示仍正常显示。提取期间切换图片并框选，完成提示出现后可继续拖动和保存。HTTP 接口及存储格式未变。

## 修改文件

- `assets/inbox.js`：限定提取完成后的同步范围，记录拖动状态，等待异步回调完成。
- `AI/inbox.md`、`AI/frontend.md`、`README.md`：同步当前交互说明。
- `AI/logs/log.md`：增加本记录索引。

## 验证

- `node --check assets/inbox.js`：通过。
- 临时 Playwright 脚本：启动隔离 HTTP 服务与 Chromium，模拟 A 图提取完成时继续在 B 图拖动，确认 B 图区域仍显示并写入收件箱，且页面无 JS 异常：通过。
- `python3 -m unittest tests.test_inbox`：14 例通过。
- `python3 tests/check_docs.py`：检查 14 个文档，0 处问题。

## 同步过的文档

`AI/inbox.md`、`AI/frontend.md`、`README.md`、`AI/logs/log.md`。
