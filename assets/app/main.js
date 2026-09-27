/**
 * 前端唯一启动入口（type=module，浏览器在全部经典脚本之后才执行）。顺序：
 * 1. 安装过渡桥：旧 uiToast / uiDialog 等转调新组件，排队的旧调用补发；
 * 2. 启动外壳：登记页面，按地址先显示对应页面的外壳（刷新时不先闪一下仪表盘）；
 * 3. 接上数据发布通道（domain/data.js 的快照经 bus 发 'data'，外壳同步进 store）；await 旧 init()（app.js 不再自调用）；
 * 4. router.start()：进入当前页（执行该页的进入钩子），开始响应前进 / 后退。
 * 页面登记 = 旧页面登记表 + 已迁到 features/ 的页面契约（P6、P7 合入后所有页面都是页面契约，旧登记表为空，P8 删除）。
 * 页面契约、依赖方向与过渡桥规则见 AI/frontend/architecture.md。
 */
import { installLegacyBridge } from './legacy-bridge.js';
import { startShell, applyChrome } from './shell.js';
import { LEGACY_PAGES } from './legacy-pages.js';
import { page as instantPage } from './features/instant/index.js';
import { page as feedbackPage } from './features/feedback/index.js';
import { page as questionsPage } from './features/questions/index.js';
import { page as dashboardPage } from './features/dashboard/index.js';
import { page as dataPage } from './features/data/index.js';
import { page as schedulePage } from './features/schedule/index.js';
import { page as historyPage } from './features/history/index.js';
import { page as catalogPage } from './features/catalog/index.js';
import { page as reportsPage } from './features/reports/index.js';
import { page as settingsPage } from './features/settings/index.js';
import { page as createPage } from './features/create/index.js';
import { page as boardPage } from './features/board/index.js';
import { connectSessions } from './domain/sessions.js';
import { connectData } from './domain/data.js';
import { connectHistory } from './domain/history.js';

installLegacyBridge(window);
const { router, bus } = startShell(window, [dashboardPage, dataPage, schedulePage, historyPage, catalogPage, reportsPage, settingsPage, createPage, boardPage, ...LEGACY_PAGES, questionsPage, instantPage, feedbackPage]);
connectData({ emit: (type, payload) => bus.emit(type, payload) });
connectSessions({ emit: (type, payload) => bus.emit(type, payload) });
connectHistory({ emit: (type, payload) => bus.emit(type, payload) });
applyChrome(router.page(router.resolve(window.location.hash)), document);
try {
  if (typeof window.init === 'function') await window.init();
} catch (error) {
  console.error('[omrs] init() 出错', error);
}
router.start();
