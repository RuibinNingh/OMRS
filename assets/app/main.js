import { page as reviewPage } from './features/ai-review/index.js';
import { connectReview, connectReviewPanel } from './domain/ai-review.js';
import { createReviewPanel } from './features/ai-review/detail-panel.js';
/** Browser entry: install shared services, load snapshots, then enter the hash route. */
import { startShell, applyChrome } from './shell.js';
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
import { page as assistantPage, syncAssistantNav } from './features/assistant/index.js';
import { connectSessions, refreshSessions } from './domain/sessions.js';
import { connectData, reloadData } from './domain/data.js';
import { connectHistory } from './domain/history.js';
import { connectLabels, bindLabelEvents, loadLabels, pickerOpen, closePicker, managerOpen, closeManager } from './domain/labels/index.js';
import { bindQuestionDom } from './domain/question/index.js';
import { installBoardWindow } from './features/board/runtime.js';
import { installIcons } from './ui/icon.js';
import { bindTooltips } from './ui/tooltip.js';
import { registerKeys } from './core/keys.js';
import { startActivityTracking } from './core/activity.js';
import { connectDrafts } from './domain/drafts.js';

installIcons(document);
bindTooltips(document);
bindQuestionDom(document);
installBoardWindow(window);
void startActivityTracking(document);
const pages = [dashboardPage, dataPage, schedulePage, historyPage, catalogPage, reportsPage,
  reviewPage, settingsPage, createPage, boardPage, questionsPage, instantPage, feedbackPage, assistantPage];
const { router, bus } = startShell(window, pages);
connectDrafts({ bus, router, document, window });
connectReview({ bus, router, document, window });
connectReviewPanel(createReviewPanel);
connectData({ emit: (type, payload) => bus.emit(type, payload) });
connectSessions({ emit: (type, payload) => bus.emit(type, payload) });
connectHistory({ emit: (type, payload) => bus.emit(type, payload) });
connectLabels(bus);
bindLabelEvents(document);
registerKeys('global', { escape: { inInput: true, inDialog: true, handler: () => {
  if (pickerOpen()) { closePicker(); return true; }
  if (managerOpen()) { closeManager(); return true; }
  return false;
} } });
applyChrome(router.page(router.resolve(window.location.hash)), document);
router.start();
try { await Promise.all([loadLabels(), reloadData(), refreshSessions()]); }
catch (error) { console.error('[omrs] 初始数据加载出错', error); }
syncAssistantNav(document).catch(() => {});
bus.on('agent:config', () => syncAssistantNav(document).catch(() => {}));
