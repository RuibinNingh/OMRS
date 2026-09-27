// === assets/app.js — 旧页面的数据刷新链 / init()：最后一个经典脚本；init() 由 assets/app/main.js 在全部脚本就绪后调用 ===
// 切页（v1.21.0 起）：hash 路由 assets/app/core/router.js 接管，标题、工作台布局与进入各页的初始化登记在 assets/app/legacy-pages.js
function switchTab(name){window.__omrs?.router.go(name)}
// 数据加载与快照归 assets/app/domain/data.js（P6 起）；它写好旧 DATA 镜像后调本函数刷新旧页面，再经 bus 发 'data'。
// 全局 reloadData() 由过渡桥 installDataBridge 挂上。
async function legacyDataRefresh(){updateUidList();populateFilterOptions();populateCreateLists();renderQ();if(typeof loadLabels==='function')await loadLabels();if(typeof boardReloadData==='function')await boardReloadData()}
async function setSidebarVersion(){try{const s=await api('/api/status');const el=document.getElementById('sidebar-foot');if(el&&s&&s.version)el.textContent=`${s.version} · 本地服务`}catch(e){}}
function toggleSidebar(){const c=localStorage.getItem('omrs-sidebar-collapsed')==='1';localStorage.setItem('omrs-sidebar-collapsed',c?'0':'1');document.documentElement.setAttribute('data-sidebar',c?'':'collapsed')}
function openDrawer(){document.body.classList.add('drawer-open')}
function closeDrawer(){document.body.classList.remove('drawer-open')}
function toggleDrawer(){document.body.classList.toggle('drawer-open')}
document.addEventListener('click',function(e){if(e.target.closest('.sidebar-nav .tab')&&window.matchMedia('(max-width:860px)').matches)closeDrawer()});
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeDrawer()});
async function init(){setSidebarVersion();await loadLabels();await reloadData();await refreshSessions();if(typeof boardInit==='function')boardInit()}
// Esc 关题目弹窗：由过渡桥登记到 core/keys.js（assets/app/legacy-bridge.js 的 installEscapeBridge；P5 起），不再在 document 上另挂
// 不再自调用 init()：模块入口 assets/app/main.js 装好过渡桥与路由后调用它（v1.21.0 起）
