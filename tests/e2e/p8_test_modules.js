// E2E-only adapter: historical browser assertions read named globals. Import the
// actual ES modules without restoring these names to production code.
if (location.protocol === 'http:' || location.protocol === 'https:') {
const m = p => import(new URL(p, location.origin).href);
window.__p8TestReady = Promise.all([
  m('/assets/app/domain/data.js'),
  m('/assets/app/domain/items.js'),
  m('/assets/app/domain/sessions.js'),
  m('/assets/app/domain/question/index.js'),
  m('/assets/app/domain/board/index.js'),
  m('/assets/app/domain/board/boards.js'),
  m('/assets/app/features/questions/index.js'),
  m('/assets/app/features/schedule/state.js'),
  m('/assets/app/features/schedule/arrange.js'),
  m('/assets/app/features/instant/state.js'),
  m('/assets/app/features/board/runtime.js'),
  m('/assets/app/features/board/preview.js'),
  m('/assets/app/features/board/index.js'),
  m('/assets/app/domain/labels/index.js'),
]).then(([data, items, sessions, question, board, boards, questions, schedule, arrange, instant, boardRuntime, preview, boardPage, labels]) => {
  const getter = (name, read) => Object.defineProperty(window, name, { configurable: true, get: read });
  getter('DATA', data.currentData);
  getter('SESSIONS', sessions.listSessions);
  getter('ACTIVE_FB_SESSION', sessions.activeSessionId);
  getter('SCH_VIEW', () => schedule.state.view);
  getter('SCH_EXPORT_RETURN', () => schedule.state.exportReturn);
  getter('REC_DATA_V2', () => arrange.arrange.data);
  getter('REC_LOADING', () => arrange.arrange.loading);
  getter('REC_ERROR', () => arrange.arrange.error);
  getter('INSTANT_QUEUE', () => instant.state.queue);
  getter('QUESTION_CACHE', question.detailCacheObject);
  getter('LABELS', labels.allLabels);
  window.reloadData = data.reloadData;
  window.getDueDays = items.dueDays;
  window.viewQ = question.viewQ;
  window.closeModal = question.closeModal;
  window.questionsLoadPreset = preset => { questions.loadPreset(preset); window.__omrs.router.go('questions'); window.__omrs.emit('questions:render'); };
  window.instLoadPractice = preset => { window.__omrs.router.go('instant'); window.__omrs.emit('instant:load', preset); };
  window.renderFb = () => window.__omrs.emit('feedback:render');
  window.resetFeedbackForm = () => window.__omrs.emit('feedback:reset');
  window.fbClearResults = () => window.__omrs.emit('feedback:clear-results');
  window.fbSessionProgress = sessions.sessionProgress;
  const d = boardRuntime.boardDetail();
  Object.assign(window, preview, {
    boardReloadData: () => d.reloadData(), boardLoad: (id, render = true) => d.load(id, render),
    boardAddToBoard: (id, uids, options) => d.addToBoard(id, uids, options || {}),
    boardFlushSave: options => d.flush(options || {}),
    boardApplyPrintField: (field, value) => d.applyPrintField(field, value),
    boardSetItemGap: (uid, value, options) => d.setItemGap(uid, value, options || {}),
    boardSetView: value => d.setView(value), boardSetPrintMode: value => d.setMode(value),
    boardPrintPreview: () => d.printPreview(),
    boardExportCurrent: open => open ? d.printPreview() : d.exportCurrent(),
    boardSaveQueue: () => d.saveQueue(), boardPrint: () => d.print(),
    boardMarkAwaiting: (mode, job) => d.markAwaiting(mode, job),
    boardClearAwaiting: id => d.clearAwaiting(id),
    boardRender: () => { d.render(); boardPage.repaintBoardPage(); },
    configureBoardDetail: patch => d.configure(patch || {}),
    boardQuickAdd: board.boardQuickAdd, boardChooseAndAdd: board.boardChooseAndAdd,
    boardPickerOpen: board.boardPickerOpen, boardPickerClose: board.boardPickerClose,
    boardCurrentId: boards.boardCurrentId,
  });
  getter('BOARD_DETAIL', () => d.detail());
});
}
