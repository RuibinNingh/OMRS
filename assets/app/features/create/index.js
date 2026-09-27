/** 录入题目页外壳：上传入口已迁，旧工作区其余内容逐块迁入本目录。 */
import { morph } from '../../core/dom.js';
import { flowView } from './view.js';
import { createUpload } from './upload.js';
import { createQuick } from './quick.js';
import { createGrid } from './grid.js';
import { processView } from './process-view.js';
import { processLegacy } from './legacy-inbox.js';
import { createProcess } from './process.js';

let upload = null;
let quick = null;
let grid = null;
let process = null;

export const page = {
  id: 'create', title: '录入题目', workbench: true,
  mount(root, ctx) {
    const flow = root.querySelector('#create-flow');
    morph(flow, flowView());
    morph(root.querySelector('#ib-stage-process'), processView());
    upload = createUpload(root, ctx.bus);
    quick = createQuick(root, ctx);
    grid = createGrid(root, ctx.bus);
    process = createProcess(root, ctx.bus);
    // 旧收件箱控制器仍负责列表和其它工作区，直到相应子模块迁移完成。
    window.inboxInit?.();
    return () => { window.__omrsInbox?.flush(); upload?.dispose(); quick?.dispose(); grid?.dispose(); process?.dispose(); upload = null; quick = null; grid = null; process = null; };
  },
  actions: {
    clipboard: () => upload?.readClipboard(),
    readImage: ({ arg }) => quick?.readClipboard(arg),
    removeImage: ({ arg }) => quick?.removeImage(arg),
    classify: () => quick?.classify(),
    questionText: () => quick?.questionText(),
    answerText: () => quick?.answerText(),
    openLabels: ({ el }) => quick?.openLabels(el),
    reset: () => quick?.reset(),
    submit: () => quick?.submit(),
    boardAdd: ({ el, event }) => quick?.boardAdd(el, event?.shiftKey),
    gridFilter: ({ arg }) => grid?.filter(arg),
    gridSelect: ({ arg, value, el }) => grid?.select(arg, el.checked),
    gridAll: ({ el }) => grid?.selectAll(el.checked),
    gridClear: () => grid?.clear(),
    gridOpen: ({ arg }) => grid?.open(arg),
    gridOpenSelected: () => grid?.openSelected(),
    gridDetect: ({ arg }) => grid?.detect(arg),
    gridApplyLast: () => grid?.applyLast(),
    gridWhole: () => grid?.whole(),
    gridDiscard: () => grid?.discard(),
    processQueueAll: ({ el }) => processLegacy('queueAll', el.checked),
    processLayout: ({ el }) => processLegacy('layout', el.value),
    processDetectSelected: ({ arg }) => processLegacy('detectSelected', arg),
    processApplyLastSelected: () => processLegacy('applyLastSelected'),
    processStep: ({ arg }) => processLegacy('step', Number(arg)),
    processRole: ({ arg }) => processLegacy('role', arg),
    processDetectCurrent: ({ arg }) => processLegacy('detectCurrent', arg),
    processWholeImage: () => processLegacy('wholeImage'),
    processApplyLast: () => processLegacy('applyLast'),
    processClearBoxes: () => processLegacy('clearBoxes'),
    processAddCard: () => processLegacy('addCard'),
    processDiscardCurrent: () => processLegacy('discardCurrent'),
    processExtractAll: () => processLegacy('extractAll'),
    processMarkReady: () => processLegacy('markReady'),
  },
  keys: Object.fromEntries(['q', 'a', 'x', 'delete', 'backspace', 'enter', 'mod+enter', 'escape']
    .map(name => [name, () => process?.key(name) ?? false])),
};
