/** 反馈录入页面挂载、事件与快捷键。 */
import { createFeedbackController } from './controller.js';

export { createFeedbackController };

let ctl = null;
const onButton = event => !!event.target?.closest?.('button, a[href], [role="button"], summary');
const active = fn => (...args) => (ctl ? fn(...args) : false);

export const page = {
  id: 'feedback',
  title: '反馈录入',
  workbench: true,
  mount(root, ctx) {
    ctl = createFeedbackController(root, ctx);
    const onPaste = event => ctl?.onPaste(event);
    document.addEventListener('paste', onPaste);
    const offs = [
      ctx.bus.on('labels', () => ctl?.paint()),
      ctx.bus.on('sessions', () => ctl?.paint()),
      ctx.bus.on('history:changed', ({ source }) => { if (source === 'question') ctl?.syncAfterQuestion(); }),
      ctx.bus.on('feedback:render', () => ctl?.paint()),
      ctx.bus.on('feedback:session', id => ctl?.openSession(id)),
      ctx.bus.on('feedback:reset', () => ctl?.resetForm()),
      ctx.bus.on('feedback:clear-results', () => ctl?.clearResults()),
      () => document.removeEventListener('paste', onPaste),
    ];
    ctl.paint();
    ctl.refresh(); // 进入即拉最新 Session 进度（取代旧 enter 钩子 refreshSessions）
    return () => { offs.forEach(off => off()); ctl?.dispose(); ctl = null; };
  },
  actions: {
    // data-change 挂在 select 的外层（ui/select 不收 action），值从事件目标读
    session: ({ event }) => ctl?.selectSession(event.target.value),
    refresh: () => ctl?.refresh(),
    addRow: () => ctl?.addRow(),
    go: ({ arg }) => ctl?.go(arg),
    verdict: ({ arg }) => ctl?.verdict(arg === '1'),
    score: ({ value }) => ctl?.score(value),
    note: ({ value }) => ctl?.note(value),
    uid: ({ value }) => ctl?.setUid(value),
    drop: () => ctl?.drop(),
    label: ({ arg }) => ctl?.toggleLabel(arg),
    labels: ({ el }) => ctl?.openLabels(el),
    board: ({ el, event }) => ctl?.board(el, event.shiftKey),
    submit: () => ctl?.submit(),
    skip: ({ arg }) => ctl?.skip(arg === '1'),
    finish: () => ctl?.finish(),
    openPlan: () => ctl?.openPlan(),
    toggleImport: () => ctl?.toggleImport(),
    readClipboard: () => ctl?.readClipboard(),
    draft: ({ value }) => ctl?.draft(value),
    importBox: () => ctl?.importBox(document.getElementById('fb-json')?.value || ''),
    copyPrompt: () => ctl?.copyPrompt(),
    reopenResults: () => ctl?.reopenResults(),
  },
  keys: {
    j: active(() => ctl.step(1)),
    arrowdown: active(() => ctl.step(1)),
    k: active(() => ctl.step(-1)),
    arrowup: active(() => ctl.step(-1)),
    1: active(() => ctl.verdict(true)),
    2: active(() => ctl.verdict(false)),
    ...Object.fromEntries([0, 3, 4, 5, 6, 7, 8, 9].map(n => [String(n), active(() => ctl.scoreKey(n))])),
    enter: active(event => (onButton(event) ? false : ctl.nextOpen())),
    e: active(() => ctl.edit()),
    'mod+enter': active(() => ctl.submit()),
  },
};
