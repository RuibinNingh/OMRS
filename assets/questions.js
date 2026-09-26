// === assets/questions.js — 题库页迁到 assets/app/features/questions 之后的残留（P5）===
// 题库表格 / 画廊 / 筛选 / 批量在 features/questions；题目操作（迁移、停用、恢复、删除）在 domain/question/ops.js。
// 这里只留：
// - masteryBarHtml()：调用方 board.js（展示板列表），P7 随展示板迁走；
// Markdown 编辑器 P5 第 3 轮起在 assets/app/domain/question/editor.js（ui/dialog）。
function masteryBarHtml(item,width){const m=asNumber(item.mastery,0);const color=m>.8?'var(--green)':m>.4?'var(--yellow)':'var(--red)';return`<span class="m-bar"${width?` style="width:${width}px"`:''}><span class="m-bar-fill" style="width:${m*100}%;background:${color}"></span></span>${(m*100).toFixed(0)}%`}
