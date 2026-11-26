# 2026-11-26 复习清单服务端 A4 PDF 下载

> **任务**
> - 标识：schedule-a4-pdf
> - 状态：已交付

## 背景

用户说「那统一吧」「直接由服务端提供」，并明确「直接改成下载文件,导出可以选择HTML或者PDF.在菜单里面新增功能就行」。按会话计划执行，完整模式，起点为本地 A4 栏宽修复 `4ecfad6`。网页默认选 A4 PDF，保留先前已保存的格式偏好。

## 行为变化

已有计划和全题库导出可直接下载 A4 PDF、A4 HTML 或屏幕版 HTML。PDF 与 A4 HTML 共用排版、字体与纸面参数。服务端 Chromium 在打印媒体下完成排版、固定纸页并输出 PDF，阅读器缩放只影响显示。API 通过 `format: "pdf"` 请求 PDF，无格式参数时默认 A4 HTML。PDF 渲染单并发、45 秒期限，失败时给出原因并保留选择。

## 影响文件

- `omrs/exporting.py`、`omrs/export_templates/a4.js`、`omrs/export_pdf.py`、`omrs/http/learning.py` 接入 A4 纸面快照、后台渲染和 PDF 附件响应。
- `omrs/render_process.py`、`omrs/question_svg.py` 共用进程树回收。
- `assets/app/features/schedule/`、`assets/app/domain/exporting.js` 调整共用格式菜单、文件名、记忆与下载。
- `tests/` 增加 PDF 回归并更新涉及默认格式、分页引擎符号的断言。README、导出、API、维护环境及前端文档同步当前契约。

## 已执行验证

- `tests/e2e/schedule_export.py` 在工作区和 Git 树 `c63ebe3` 的候选源码归档各通过 39 项。验证两处附件下载、单双栏、HTML 兼容、真实 422 排版失败、模拟服务不可用后重试及旧偏好。归档证据在 `/tmp/omrs-server-pdf-candidate-downloads/`。用临时安装的 pypdf 核对，计划双栏 PDF 与基准 HTML 打印 PDF 的两页正文、题序及逐页绘制指令一致。全库单栏 PDF 为三页。
- 用真实渲染进程验证 260px 窄栏 SVG 返回 422、Chromium 查找目录为空返回 503、恢复后可生成 PDF。渲染忙碌、超时回收和不完整输出另有单测。PDF 专项首次发现夹具导入失败，后续两次定位了离线截图问题，调整测试后复跑通过。
- Python 导出、HTTP 边界、安全、SVG、字体、展示板和提醒组合 85 项通过。A4 与展示板打印 17 项、报告导出 7 项、MCP 导出 7 项通过。报告门禁在基线也有过时的函数名和坐标断言，已同步到实际模板并复跑。
- Node 607 项、浏览器组件 35 项、SVG 端到端 23 项、提醒素材 30 项通过。UI 零问题，58 组对比度达标。调度总回归 51 通过、3 失败，同一基线归档复现相同三项。分别为旧入口生成计划、安排复习生成计划和暂停后反馈按钮。该套件的导出断言均通过。
- 调度主页面 `tests/visual/run.py --ref 4ecfad6 --pages schedule` 四档像素一致，脚本错误为零，报告在 `/tmp/omrs-server-pdf-schedule-visual/report.html`。另对导出面板四档做前后对比，尺寸一致，差异为文件格式控件增加 A4 PDF、HTML 标签、默认选中样式和去掉只适用于 HTML 的提示。截图在 `/tmp/omrs-server-pdf-dialog-visual/`。
- 已刷新任务日志索引。文档差异门禁和 `git diff --check` 通过。

## 未执行验证

未发布生产或推送远端。未测试实体打印机、第三方 PDF 阅读器，未跑全仓所有后端测试。功能验证使用临时 Vault、随机端口和合成题库。
