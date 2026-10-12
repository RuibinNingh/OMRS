# 可复用的独立网关验收流程

- 冻结跨项目 v1 响应字段，先测原字节/真实 HTTP/SQLite，再封装协议，不让客户端偷走内置直连。
- 先为一条可见主路径留 RED 日志，再实现、完整 GREEN，下一条主路径接着做；新审查缺陷必须先变失败见证。
- 把官方网络作为唯一合成边界；设备/账号样本必须显式 SYNTHETIC，服务默认不能制造身份。
- 分离管理员 Cookie/CSRF 与调用 Bearer Key，本机同样鉴权；外部拒绝看 socket，绝不看不可信 XFF。
- 用 random port + 临时私有目录进行写入验收；每次接口写后 GET 读回；真实 Key/密码绝不进入证据。
- 复用 shared Chrome CDP 时只 new_context/close context，不 browser.close；CSP 禁 eval 时 wait_for_function 传 `() => ...` 函数，不能削弱 CSP 迁就测试。
- 390px 验收同时检查 document.scrollWidth、真实控件、无脚本错误；XSS fixture 被 textContent 原样显示是转义成功，不应根据截图把它误判成脚本执行。
- 本项目写域以外的全局 Skills/生产服务不可为了记录工作而修改；经验留在本文件，交由父会话按授权再入技能库。
