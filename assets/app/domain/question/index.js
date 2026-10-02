/**
 * 题目领域：共享题目视图 qview、Markdown / KaTeX 渲染（内容哈希缓存）、练习记录、题目详情缓存、题目弹窗与 Markdown 编辑器。
 * 新页面只从这里取；旧脚本经 legacy-bridge.js 的 installQuestionBridge 拿到同名全局（renderMdContent、qvRender、viewQ…）。
 * 文档：AI/frontend/qview.md。
 */
import { qvRender, qvInvalidateMany } from './mount.js';

export { editQuestion, suspendQuestion, resumeQuestion, deleteQuestion, moveQuestion, batchSuspend, exportA4 } from './ops.js';

export { renderMd, renderMdInline, renderMdUncached, mdLineBreakMode, setMdLineBreakMode, mdCacheStats, clearMdCache, hashText } from './markdown.js';
export { parseQHistory, qRecordsFromDetail, qHistoryStats, qStreakHtml } from './records.js';
export { QV_DEFAULTS, QV_CARD_OPTS, qvHtml, qvChips, qvToolsHtml, qvRecordHtml, qvCreationHtml, qvGalleryCard, qvGalleryIdHtml } from './view.js';
export {
  cachedDetail, dropDetail, ensureDetail, qvSetContext, qvContext, qvRender, qvUnmount, qvInvalidate, qvInvalidateMany, qvRerenderAll,
  bindQuestionDom, detailCacheObject, pendingDetailsObject,
} from './mount.js';
export { viewQ, closeModal, modalOpen, modalUid } from './modal.js';
export { openEditor, closeEditor, editorOpen } from './editor.js';


/** 即时练习的题面：题面 | 答案双栏；reveal=false 时只给「显示答案」按钮，点它回调 onReveal。题头由页面自己显示。 */
export function mountQuestion(el, uid, { reveal = false, onReveal, question_id } = {}) {
  if (!el) return Promise.resolve(null);
  return qvRender(el, uid, { layout: 'split', reveal, showMeta: false, showHistory: false, actions: ['edit', 'board', 'labels'], onReveal, question_id });
}

/** 反馈录入的题面：完整题头，工具按钮多给「停用」「打开」。 */
export function mountQuestionStage(el, uid, question_id) {
  if (!el) return Promise.resolve(null);
  return qvRender(el, uid, { layout: 'split', actions: ['edit', 'board', 'labels', 'suspend', 'open'], question_id });
}

/** 反馈 / 练习提交后题目的记录变了：清缓存并重绘挂着它们的视图。 */
export function invalidateQuestions(uids) {
  return Promise.resolve(qvInvalidateMany(uids)).catch(error => console.error('[domain/question] 失效重绘出错', error));
}
