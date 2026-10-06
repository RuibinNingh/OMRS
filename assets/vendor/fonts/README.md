# 本地字体

主工作台使用 Noto Sans SC（可变字重 100–900）与 JetBrains Mono（100–800）。`fonts.css` 保留上游 Unicode 分片，没有远程地址或 `local()` 覆盖。资源于 2026-09-20 从 Google Fonts 下载；`SOURCES.json` 记录请求、来源 URL、字节数和 SHA256，许可见 `notosanssc-OFL.txt`、`jetbrainsmono-OFL.txt`。

A4 打印正文新增 Noto Serif SC（400–700），元信息复用 Noto Sans SC。`noto-serif-sc.css` 与 101 份原样 WOFF2 分片于 2026-10-06 下载；`PRINT_SOURCES.json` 记录上游地址、字节数与 SHA256，许可见 `notoserifsc-OFL.txt`。打印 CSS 使用独立的 `OMRS Print Serif` / `OMRS Print Sans` 别名，由 `omrs/export_fonts.py` 按文字覆盖选择分片并内嵌 data URI 与许可；只输出当前导出需要的分片，不带 JetBrains Mono。A4 离线打开不依赖平台中文字体，工作台字体入口不变。

更新时从 manifest 所记请求取得现代浏览器的字体 CSS，原样下载 WOFF2，将地址换成本地文件名并更新来源清单与许可。保留全部 Unicode 范围，不能只保留今天的界面文字。导出只选择完整的上游分片，不改写字体二进制。
