# 前端：问题中心

> **速查**
> - 职责：独立问题页、Markdown预览、附件、多题关联和记录时间线
> - 入口：`assets/app/features/problems/index.js`、`assets/app/features/problems/view.js`、`assets/app/domain/problems.js`
> - 不变量：原生ES Module与共享UI组件；手机分层；关联只传稳定question_id
> - 必跑测试：`tests/app/problems.test.mjs`、`tests/app/reflections.test.mjs`、`tests/e2e/problems.py`、`tests/e2e/reflection_layout.py`
> - 相关：`AI/problems.md`、`AI/frontend/qview.md`、`AI/frontend/design-system.md`

## 页面与内容

侧栏「问题」进入#/problems，桌面左列表右详情，760px以下先列表、进入详情后可返回。列表按最近更新排序，提供标题/描述搜索、状态筛选与分页。标题必填，正文支持安全Markdown、公式、表格、标题、列表、引用、代码与受限链接；普通HTML转义。附件可选择文件或粘贴图片，持久化引用PA内容摘要，不保存blob地址。页面浅深主题使用现有token。

排版由`assets/app/domain/rich-markdown.js`提供，与题目备注共用；`domain/problem-markdown.js`继续将PA附件映射到`/api/problem-asset`，不改变题目备注的图片读取入口。代码保留Markdown与公式源码，多行展示公式作为完整块渲染；问题说明默认保留普通换行。格式与附件边界回归见`tests/app/rich-markdown.test.mjs`。

详情显示用户确认或AI假设、五状态、变更理由、题目关联和时间线。题目选择器按稳定身份关联，可预览和移除材料；移除材料不删除题目或既有错因。保存失败保留当前编辑内容，重试沿用同请求编号，CAS冲突明确提示重新读取。

## 题目弹窗

`domain/question/reflections.js`提供原位录因：弹窗足够宽时放右侧，不足时放在题目后面，头部「＋错因」直接定位录入框。「记录本次」与「历史记录」按页签切换，详情见`AI/frontend/qview.md`。旧Markdown错因继续在原题答案区展示。问题页不把记录条数命名为复发次数，也不自动解决问题。

描述支持粘贴完整SVG源码及拖入文件，服务端验证后转换为同一受管附件引用。关联题预览沿用该问题的可用题目列表，可在弹窗翻题。AI假设可由用户填写依据后明确确认，状态变化本身不确认假设。

请求编号统一复用`core/request-id.js`的128位安全随机字节，不依赖安全上下文专属API。`tests/e2e/problems_http.py`通过真实普通HTTP源与PIN会话验证新建、关联、连续错因及刷新读回；代理保留Host、Origin和Cookie。
