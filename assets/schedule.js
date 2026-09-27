// === assets/schedule.js — 全局扫描 doScan 与两个旧入口 ===
// 复习调度页已迁到 assets/app/features/schedule（P6 第 3 轮）；Session 列表归 assets/app/domain/sessions.js，
// 旧的 refreshSessions / schOpenPlan 等由过渡桥 installScheduleBridge 挂成同名全局。
// 反馈录入已迁到 assets/app/features/feedback：跳转与选中都交给页面契约，经过渡桥的 bus 事件（P8 删除本函数）。
async function feedbackSession(sessionId) { window.__omrs?.router.go('feedback'); window.__omrs?.emit('feedback:session', sessionId); }
// 旧「填充反馈页 Session 下拉」入口：下拉现由新反馈页自己渲染，这里只通知它 Session 数据已变（P8 删除）。
function refreshFbSessionPicker(){ window.__omrs?.emit('sessions'); }
async function doScan(){try{const result=await api('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(result.status==='ok'){uiToast(`扫描完成，共 ${result.count} 道题目`,{kind:'ok'});await reloadData();await refreshSessions();return true}else{uiToast(`扫描失败: ${result.msg||'未知错误'}`,{kind:'error'})}}catch(error){uiToast(`无法连接后端: ${error.message}`,{kind:'error'})}return false}
