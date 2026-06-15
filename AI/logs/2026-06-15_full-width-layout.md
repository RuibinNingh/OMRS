# 2026-06-15 布局改为全宽自适应

> 纯 CSS,版本不变(`v1.5.0`)。

## 问题
窗口最大化后内容被限制宽度、左右留白。根因:`.shell` 上的 `max-width:1500px;margin:0 auto`——超过 1500px 的屏幕会把整个应用居中、两侧空出。

## 改动(`assets/styles.css`)
- 活动的 `.shell` 去掉 `max-width:1500px`,`margin:0 auto` 改 `margin:0`,改为占满视口宽度;`.content{flex:1}` 自然填满侧边栏右侧的剩余空间。1920px 实测:shell=1920、content 右沿=1920,无留白。
- 顺手删掉一条**已废弃**的旧 `.shell`(旧 header 版,`max-width:1360px`,早被下方 v1.4.0 shell 完全覆盖)——对应 optimization.md「CSS 叠加债」里的一例。

## 注
现在完全自适应,无上限;若将来在超宽屏(如 3440px+)觉得正文行太长,可再给 `.content` 加一个较大的 `max-width` 作上限。
