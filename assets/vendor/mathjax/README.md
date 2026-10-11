# MathJax 3.2.2

作业帮传统题库正文的后端渲染使用MathJax3，与附件原App的公式引擎版本一致。这里采用官方npm发布的 `mathjax@3.2.2`，下载时核对npm SHA512完整性；逐文件SHA256见 `manifest.json`，Apache-2.0许可见 `LICENSE`。

仅包含 `tex-chtml-full.js`、`ui/safe.js` 和全部23份CHTML WOFF字体。后端可信配置禁用菜单、外部公式链接/样式及动态加载，只经受限本地路由读取。作业帮页面本身不加载这个引擎；OMRS其它Markdown页面继续使用原有KaTeX。
