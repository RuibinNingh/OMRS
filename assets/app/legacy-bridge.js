/**
 * 过渡桥：把新 ui 组件挂到旧代码仍在调用的入口上。每一条注明旧调用方与删除期；P8 时本文件必须为空。
 *
 * 旧 assets/core.js 的 uiToast / uiDialog / uiPrompt / uiConfirm 已改成转调 window.__omrsUi；
 * 模块脚本晚于经典脚本执行，桥装好之前的调用先进 window.__omrsUiPending 队列，这里装好后按顺序补发。
 */
import { toast } from './ui/toast.js';
import { dialog, confirm, prompt } from './ui/dialog.js';
import { hostGuest, releaseGuest } from './ui/overlay.js';
import { installIcons } from './ui/icon.js';
import { bindTooltips } from './ui/tooltip.js';
import { state as instantState } from './features/instant/state.js';
import { fbSessionProgress } from './features/feedback/state.js';
import * as question from './domain/question/index.js';
import { loadPreset as questionsPreset } from './features/questions/index.js';
import { registerKeys } from './core/keys.js';
import * as labels from './domain/labels/index.js';
import { reloadData, setLegacyRefresh } from './domain/data.js';
import { refreshSessions, sessionsState } from './domain/sessions.js';
import { state as scheduleState } from './features/schedule/state.js';
import { arrange as arrangeState } from './features/schedule/arrange.js';
import { arrangeApi } from './features/schedule/index.js';
import { downloadResponse } from './core/download.js';

// 旧 uiToast 不传 kind 时是绿色成功样式；新组件的默认是 info，这里按旧语义映射。
const LEGACY_KIND = { ok: 'ok', warn: 'warn', error: 'error', info: 'info' };

export function installLegacyBridge(win) {
  const doc = win.document;
  installIcons(doc);
  bindTooltips(doc);
  const ui = Object.freeze({
    // uiToast(text, {kind, actions, duration}) —— 调用方：assets/*.js 全部 toast、inbox.js 的 ibToast；P8 删除
    toast: (text, options = {}) => toast(text, { ...options, kind: LEGACY_KIND[options.kind] || 'ok' }),
    // uiDialog(spec) → {ok, values} —— 调用方：board.js、labels.js、questions.js 等；P8 删除
    dialog: spec => dialog(spec || {}),
    // uiConfirm(title, {hint, danger, okText}) → boolean —— 调用方同上；P8 删除
    confirm: (title, options) => confirm(title, options || {}),
    // uiPrompt(title, value, {hint, placeholder, maxLength}) → string|null —— 调用方同上；P8 删除
    prompt: (title, value, options) => prompt(title, value, options || {}),
    // host(node, {close, escape}) / release(node) —— 旧浮层叠在模态对话框（题目弹窗）上时放进对话框，否则被 inert（ui/overlay 的 hostGuest）。
    // 调用方：labels.js（标记选择器、标记管理）、board_picker.js（选板浮层）；各自迁走时删除（labels P6 起、board_picker P7）
    host: (node, options) => hostGuest(node, options || {}),
    release: node => releaseGuest(node),
  });
  win.__omrsUi = ui;
  const pending = Array.isArray(win.__omrsUiPending) ? win.__omrsUiPending : [];
  win.__omrsUiPending = null;
  pending.forEach(run => run(ui));
  installDataBridge(win);
  installScheduleBridge(win);
  installLabelsBridge(win);
  installInstantBridge(win);
  installFeedbackBridge(win);
  installQuestionBridge(win);
  installQuestionsPageBridge(win);
  installEscapeBridge(win);
  return ui;
}

/**
 * 全局数据所有权反转到 domain/data.js 之后留给旧代码的入口（P6 起；P8 清空）。
 * - reloadData() —— 调用方：app.js init()、history.js、inbox.js、labels.js、schedule.js（建题、扫描、删计划）等写操作之后。
 *   旧 app.js 里的同名函数已删；这里挂的是 domain 的实现（并发合并、失败保留旧快照）。
 * - 旧页面的刷新链 legacyDataRefresh()（app.js：下拉选项、导出选题、题库重绘、标记、展示板、推荐、目录）
 *   登记为 domain 的旧代码钩子，在快照写好之后、发 'data' 之前执行。各页迁完逐项删，P8 时钩子为空。
 * - QUESTION_CACHE / QUESTION_PENDING（只读）—— 调用方：board.js、export.js 读题目详情缓存；缓存对象归 domain/question/mount.js。
 */
function installDataBridge(win) {
  win.reloadData = reloadData;
  setLegacyRefresh(() => (typeof win.legacyDataRefresh === 'function' ? win.legacyDataRefresh() : undefined));
  Object.defineProperty(win, 'QUESTION_CACHE', { configurable: true, get: question.detailCacheObject });
  Object.defineProperty(win, 'QUESTION_PENDING', { configurable: true, get: question.pendingDetailsObject });
}

/**
 * 复习调度迁到 features/schedule、Session 列表归 domain/sessions 之后留给旧代码的入口（P6 第 3 轮起；P8 清空）。
 * - refreshSessions() —— 调用方：app.js init()、history.js（历史修正后）、schedule.js 的 doScan。
 * - schOpenPlan(id) —— 调用方：tests/e2e/schedule.py（旧入口回归）。「安排复习」已原生，生成计划后直接打开新计划。
 * - confirmScheduleV2() / loadRecommendationsV2() —— 调用方：tests/smoke_schedule_workbench.py（重复调用只生成一次）。
 * - renderUnifiedListV2() —— 调用方：labels.js（标记定义变化后）；转成页面重绘。
 * - REC_DATA_V2 / REC_LOADING / REC_ERROR（只读）—— 调用方：tests/e2e/schedule.py、tests/smoke_schedule_workbench.py 等待条件。
 * - SCH_VIEW / SCH_EXPORT_RETURN / SCH_SESSIONS_LOADING（只读）—— 调用方：tests/e2e/dashboard.py、tests/smoke_schedule_workbench.py 等待条件。
 * - renderExportPicker() —— 调用方：labels.js（标记定义变化后）；转成页面重绘。全题库导出已原生（v1.25.4），旧 export.js 已删。
 * - downloadExportResponse(response, name, statusId) —— 调用方：app.js（备份导出）、domain/question/ops.js（批量 A4）；
 *   实现是 core/download.js，传了 statusId 时在该元素里写「✓ 文件名」。
 * 不在复习调度页时，schOpenPlan 先切页再发事件（页面挂载后才在听）。
 */
function installScheduleBridge(win) {
  const go = () => { if (win.__omrs?.router.current() !== 'schedule') win.__omrs?.router.go('schedule'); };
  win.refreshSessions = refreshSessions;
  win.schOpenPlan = id => { go(); win.__omrs?.emit('schedule:open-plan', id); };
  Object.defineProperty(win, 'SCH_VIEW', { configurable: true, get: () => scheduleState.view });
  Object.defineProperty(win, 'SCH_EXPORT_RETURN', { configurable: true, get: () => scheduleState.exportReturn });
  Object.defineProperty(win, 'SCH_SESSIONS_LOADING', { configurable: true, get: () => sessionsState().loading });
  win.confirmScheduleV2 = () => arrangeApi.confirm();
  win.loadRecommendationsV2 = () => arrangeApi.load();
  win.renderUnifiedListV2 = () => win.__omrs?.emit('schedule:render');
  win.renderExportPicker = () => win.__omrs?.emit('schedule:render');
  win.downloadExportResponse = async (response, fallbackName, statusId) => {
    const name = await downloadResponse(response, fallbackName);
    const box = statusId ? win.document.getElementById(statusId) : null;
    if (box) box.textContent = `✓ ${name}`;
    return name;
  };
  Object.defineProperty(win, 'REC_DATA_V2', { configurable: true, get: () => arrangeState.data });
  Object.defineProperty(win, 'REC_LOADING', { configurable: true, get: () => arrangeState.loading });
  Object.defineProperty(win, 'REC_ERROR', { configurable: true, get: () => arrangeState.error });
}

/**
 * 标记芯片、颜色与选择器数据迁到 domain/labels/ 之后留给旧代码的同名全局（P5 第 4 轮起；各调用方迁完逐条删，P8 清空）。
 * 旧 labels.js 里这些函数的定义已删除；它们只在函数体里被调用（init() 之后），装在这里来得及。
 */
function installLabelsBridge(win) {
  const storage = () => { try { return win.localStorage; } catch (error) { return null; } };
  const recent = () => labels.readRecent(storage(), labels.allLabels());
  const names = {
    // 芯片 —— 调用方：labels.js、board.js、data.js、export.js、inbox.js、recommend_v2.js
    lblChip: labels.chipHtml,
    lblChips: labels.chipsHtml,
    // 颜色 —— 调用方：labels.js（色板、管理行的颜色圆点、新建与改名表单）
    lblColorKey: labels.ensureColor,
    labelHex: labels.normalizeColor,
    labelPresetColors: labels.presetColors,
    nextLabelColor: () => labels.nextColor(labels.allLabels(), labels.presetColors()),
    // 定义列表、选择器与管理的数据部分 —— 调用方：labels.js（loadLabels、选择器、保存、批量、管理表单）
    labelSort: labels.sortLabels,
    labelUpsert: labels.upsertLabel,
    labelPickerOptions: labels.pickerOptions,
    labelRecent: recent,
    labelTouchRecent: list => labels.touchRecent(storage(), list, labels.allLabels()),
    labelQuickList: (limit = 4) => labels.quickList(labels.allLabels(), recent(), limit),
    labelApplyBatch: labels.applyBatch,
    labelFormValues: labels.formValues,
  };
  Object.entries(names).forEach(([name, value]) => { win[name] = value; });
}

/** 即时练习迁到 features/instant 之后留给旧代码的入口（P8 删除）。 */
function installInstantBridge(win) {
  // instLoadPractice(preset) —— 调用方：tests/e2e/instant.py（旧入口回归）。仪表盘已迁到 features/dashboard，直接经 bus 发 'instant:load'。
  // 预设键沿用旧元素 id，如 {'inst-subject': '数学'}，由新页面翻成筛选字段
  win.instLoadPractice = (preset = {}) => {
    win.__omrs?.router.go('instant');
    win.__omrs?.emit('instant:load', preset || {});
  };
  // INSTANT_QUEUE（只读）—— 调用方：tests/smoke_schedule_workbench.py 等待队列非空
  Object.defineProperty(win, 'INSTANT_QUEUE', { configurable: true, get: () => instantState.queue });
}

/** 反馈录入迁到 features/feedback 之后留给旧代码的入口（P8 删除）。 */
function installFeedbackBridge(win) {
  // fbSessionProgress(session) —— 纯函数，调用方：schedule.js（计划详情进度、下拉标签）。定义随旧 feedback.js 删除，这里从新页面 state 再导出。
  win.fbSessionProgress = fbSessionProgress;
  // renderFb() —— 调用方：labels.js（标记定义变化后，若反馈页可见则重绘）。转成让已挂载的反馈页重绘。
  win.renderFb = () => win.__omrs?.emit('feedback:render');
  // resetFeedbackForm() / fbClearResults() —— 调用方：schedule.js（删除计划时清空正在录入的表单与上次结果）。
  win.resetFeedbackForm = () => win.__omrs?.emit('feedback:reset');
  win.fbClearResults = () => win.__omrs?.emit('feedback:clear-results');
}

/**
 * 共享题目视图迁到 domain/question 之后留给旧代码的同名全局（P5 起；题库页、展示板、导出、数据复盘迁完后逐条删，P8 清空）。
 * 模块晚于经典脚本执行，但这些名字只在函数体里被调用（init() 之后），所以装在这里来得及。
 */
function installQuestionBridge(win) {
  question.bindQuestionDom(win.document);
  const names = {
    // 题面渲染 —— 调用方：questions.js（画廊、表格悬停预览）、qtable.js、inbox.js（收件箱题卡预览）
    renderMdContent: question.renderMd,
    renderMdInline: question.renderMdInline,
    // 详情缓存 —— 调用方：board.js、export.js、recommend_v2.js、questions.js 画廊
    ensureQuestionDetail: question.ensureDetail,
    // qview —— 调用方：board.js、export.js（选题卡）、questions.js 画廊、recommend_v2.js（推荐预览）
    qvHtml: question.qvHtml,
    qvRecordHtml: question.qvRecordHtml,
    qvGalleryCard: question.qvGalleryCard,
    qvGalleryIdHtml: question.qvGalleryIdHtml,
    qvRender: question.qvRender,
    qvSetContext: question.qvSetContext,
    qvContext: question.qvContext,
    // 失效重绘 —— 调用方：history.js（历史修正）、schedule.js、labels.js
    qvInvalidate: question.qvInvalidate,
    qvInvalidateMany: question.qvInvalidateMany,
    qvRerenderAll: question.qvRerenderAll,
    // 题目弹窗（domain/question/modal.js，ui/dialog 外壳）—— 调用方：board.js、catalog.js、data.js、export.js、inbox.js、recommend_v2.js、schedule.js
    viewQ: question.viewQ,
    closeModal: question.closeModal,
    // Markdown 编辑器（domain/question/editor.js）—— 调用方：tests/e2e 的 instant.py、feedback.py 用 closeMarkdownEditor() 收尾；打开一律经 editQuestion()
    closeMarkdownEditor: question.closeEditor,
    // 练习记录 —— 调用方：questions.js 画廊战绩带、board.js
    parseQHistory: question.parseQHistory,
    qRecordsFromDetail: question.qRecordsFromDetail,
    qHistoryStats: question.qHistoryStats,
    qStreakHtml: question.qStreakHtml,
  };
  Object.entries(names).forEach(([name, value]) => { win[name] = value; });
}

/** 题库页迁到 features/questions 之后留给旧代码的入口（P8 删除）。 */
function installQuestionsPageBridge(win) {
  // renderQ() / filterQ() —— 调用方：app.js（legacyDataRefresh）、labels.js（标记保存后 labelRefreshViews）。转成让已挂载的题库页重绘。
  win.renderQ = () => win.__omrs?.emit('questions:render');
  win.filterQ = win.renderQ;
  // questionsLoadPreset({'q-filter-due': 'overdue', 'q-sort': 'due-asc'}) —— 调用方：domain/question/mount.js 的「在题目库打开」、
  // tests/e2e/questions.py（旧入口回归）。仪表盘直接经 bus 发 'questions:preset'。键沿用旧元素 id；先清空全部条件再套用，然后切到题库页。
  win.questionsLoadPreset = (preset = {}) => {
    questionsPreset(preset || {});
    win.__omrs?.router.go('questions');
    win.__omrs?.emit('questions:render');
  };
}

/**
 * 旧浮层的 Esc 统一登记到 core/keys.js 的全局作用域（同一个键在一个作用域里只能有一个处理函数，所以合在一起）：
 * 1. 标记选择器（旧 labels.js 浮层）打开时先关它——原来是 labels.js 自己在 document 上挂的 keydown；
 * 2. 标记管理（旧 labels.js 的 .modal-overlay#label-manager）打开时关它（P5 第 3 轮起；原来 Esc 关不掉）。
 * 页面作用域先于全局：题库页的 Esc 在选择器打开时让位（返回 false）。题目弹窗、Markdown 编辑器是 ui/dialog，Esc 由 ui/overlay
 * 在捕获阶段处理，到不了这里；它们上面叠着的旧浮层登记为客人（legacy host），Esc 也由 ui/overlay 代为关闭。
 */
function installEscapeBridge(win) {
  registerKeys('global', {
    escape: {
      inInput: true,
      inDialog: true,
      handler: () => {
        if (labels.pickerOpen()) { labels.closePicker(); return true; }
        if (labels.managerOpen()) { labels.closeManager(); return true; }
        return false;
      },
    },
  });
}
