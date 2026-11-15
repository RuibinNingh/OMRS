# 2026-11-15 问题中心浏览与批量管理

> **任务**
> - 标识：problem-workspace
> - 状态：已交付

## 背景

用户原话：「OMRS问题页面不成熟啊」「我不能有效查看大量问题」「而且不支持删除之类的」「重新打磨UI,给我一版」。执行者为Codex，完整模式，基线为f2b9d33；开工工作区干净。旧问题中心计划已交付，本次为新的页面打磨任务。

## 行为变化

默认宽列表集中展示问题与说明摘要、五状态、关联题数和日期，按搜索范围显示各状态计数；支持防抖搜索、四种排序及每页25／50／100条分页。超过1160px并排展示可独立滚动的详情，窄屏逐层返回；紧凑密度显示更多行。

支持本页全选、跨页累计勾选、填写依据批量改状态、单项或批量删除至回收站及恢复。每批最多100项，版本冲突整批回滚；删除保留原题、材料、错因、附件和审计。管理动作只开放给网页用户，不扩展AI或MCP工具。既有错因修订和引用原记录的再次发生不受回收站阻断。

新建表单取消不产生占位问题，草稿与正式内容分离，状态变化立即提示未保存，关闭／切换／离页有保护。保存失败保留输入并复用幂等编号，写回执先确认正式身份，后续详情刷新失败也不重复新建；上传完成前禁用保存。时间线按时间倒序折叠展示，关联题排除已有材料。

## 影响文件

已用git diff --name-status、git diff --numstat和git status --short复核本任务变化，初始工作区干净：

- `assets/app/features/problems/index.js`、`view.js`、`problems.css`：工作台控制、列表与响应式外观；新增`store.js`及`view-detail.js`分离状态与详情。
- `omrs/problems.py`、`omrs/http/problems.py`：搜索排序计数、网页批量管理、回收站和历史错因边界。
- `tests/test_problems.py`、`tests/app/problems.test.mjs`：整批事务、幂等、权限、旧对象兼容、历史记录、请求竞争和草稿回归；新增`tests/e2e/problems_workspace.py`。
- `tests/visual/run.py`：问题页共用137条合成夹具；`AI/environment.md`及`AI/frontend/architecture.md`同步验证入口与状态所有者。
- `AI/frontend/problems.md`、`AI/problems.md`、`AI/api.md`、`AI/data.md`、`AI/security.md`、根`README.md`：同步当前页面、接口、存储及权限；`AI/routes.md`与`AI/logs/log.md`均由脚本生成。

## 已执行验证

证据根目录：`/root/workspace/artifacts/omrs-problem-workspace-20261115/`。服务均使用临时Vault和随机回环端口，启动清除OMRS_SYSTEMD_SERVICE与OMRS_BOXDETECT_CONTROL；没有连接真实题库或生产端口。

| 实际命令 | 结果与证据 |
|---|---|
| `python3 -m unittest discover -s tests -p 'test*problems*.py' -q` | 22项通过，含MCP真实适配；见problems-unit-final.log |
| `node --test tests/app/*.test.mjs` | 594项通过、0跳过；见node-final.log |
| `python3 tests/app/run_browser.py` | 共享组件35项通过、0失败 |
| `python3 tests/e2e/problems_workspace.py --out <证据根>/final-5` | 53项全部通过；137条问题、滚轮与固定分页、跨页选择、状态、删除恢复、失败重试及CAS、双主题320／390／760／1024／1440px；见final-5/report.json |
| `OMRS_PROBLEM_EVIDENCE=<证据根>/legacy-final python3 tests/e2e/problems.py` | 32项通过；题目关联、图片／SVG、错因、AI审核、导出与学习状态保持 |
| `OMRS_PROBLEM_EVIDENCE=<证据根>/http python3 tests/e2e/problems_http.py` | 14项通过，普通HTTP真实PIN、Cookie、Origin与保存刷新 |
| `OMRS_REFLECTION_EVIDENCE=<证据根>/reflection python3 tests/e2e/reflection_layout.py` | 43项通过，原错因侧栏／底部、输入保留及六档宽度双主题 |
| `python3 tests/check_ui.py`、`python3 tests/check_contrast.py` | UI零违规，58组对比度全部通过 |
| `python3 tests/visual/run.py --ref HEAD --pages problems --out <证据根>/visual-final` | 4组前后对比，当前与基线均无脚本错误、横向溢出和小操作目标；已实际查看截图 |
| `python3 tests/check_docs.py --write-routes`、`--write-log-index`、`--diff HEAD`及`git diff --check` | 路由、日志索引已生成，文档165份零问题；空白检查通过。篇幅提醒涉及既有大文档与计划 |

视觉差异逐项解释：浅色桌面87.206%、深色桌面87.323%，来自窄列表／空详情改为宽表格、状态导航、排序与固定分页；浅色手机88.706%、深色手机89.053%，来自同一工作台改为单列紧凑列表、可横滚状态导航和固定分页。基线会把50个卡片纵向排成长页，新版使用内部滚动，因此截图高度与大部分像素均变化；不是字体或颜色失控。详情、批量栏与回收站截图在final-5中。

初轮失败如实保留：workspace、workspace-2及workspace-3因模板忽略布尔插值，aria-busy未输出合法字符串而等待超时，改为显式true／false字符串后通过；final-2补充真实滚轮时未等确认框退场，改为等待dialog.is-closing消失；final-3的刷新失败提示包含附加错误文字，精确全文定位超时，改为定位完整状态区域。final-4的52项与最终final-5的53项均通过，不把旧失败计入通过数。首次文档门禁因新增接口引用未重生成路由索引失败，生成后通过。

## 未执行验证

未运行全仓Python及全部跨模块E2E：本轮后端变化限问题域，已运行相关22项与四组真实页面／HTTP回归，不将历史全仓结果充作本次验证。未在实体手机上测试，移动验证使用Chromium视口；未访问真实业务数据、付费模型或生产服务。

本轮交付开发工作区与截图，没有升级版本、提交、推送或部署生产；生产变更须用户另行授权。无已知阻塞本次页面交付的遗留问题。
