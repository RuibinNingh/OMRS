/**
 * 录入题目页契约：五个工作区（上传、处理、录入、AI 训练、快速录入）全部在本目录。
 * 收件箱数据归 inbox.js 单例（切页返回后工作区、当前图与勾选保持）；各工作区控制器订阅 'inbox:changed' 重绘。
 * 离开本页或离开处理区时 flush 未到防抖时间的框位与题卡字段。
 */
import { morph } from '../../core/dom.js';
import { flowView } from './view.js';
import { stageOf } from './state.js';
import { inbox, connectInbox } from './inbox.js';
import { createUpload } from './upload.js';
import { createQuick } from './quick.js';
import { createGrid } from './grid.js';
import { processView } from './process-view.js';
import { createProcess } from './process.js';
import { createCards } from './cards.js';
import { createTrain } from './train.js';

const S = inbox.state;
let parts = null;

function mountParts(root, ctx) {
  const flow = root.querySelector('#create-flow');
  let shown = null;
  function paintStage() {
    const stage = stageOf(S.stage);
    morph(flow, flowView(stage, inbox.counts()));
    root.querySelectorAll('.ib-stage').forEach(section => section.classList.toggle('on', section.id === `ib-stage-${stage}`));
    if (shown === stage) return;
    const previous = shown;
    shown = stage;
    if (stage === 'process') parts.process.paint();
    if (stage === 'create') parts.cards.paint();
    if (stage === 'train') parts.train.enter();
    if (previous !== null) root.querySelector(`#ib-stage-${stage}`)?.scrollTo?.(0, 0);
  }
  morph(root.querySelector('#ib-stage-process'), processView());
  parts = {
    upload: createUpload(root, ctx.bus),
    quick: createQuick(root, ctx),
    grid: createGrid(root, ctx.bus),
    process: createProcess(root, ctx.bus),
    cards: createCards(root, ctx),
    train: createTrain(root),
  };
  const stops = [
    ctx.bus.on('inbox:changed', paintStage),
    ctx.bus.on('inbox:reload', () => inbox.load()),
  ];
  paintStage();
  return () => stops.forEach(stop => stop());
}

export const page = {
  id: 'create', title: '录入题目', workbench: true,
  mount(root, ctx) {
    const disconnect = connectInbox(ctx.bus);
    const unbind = mountParts(root, ctx);
    inbox.load();
    return () => {
      inbox.flush();
      unbind();
      Object.values(parts || {}).forEach(part => part?.dispose());
      parts = null;
      disconnect();
    };
  },
  actions: {
    stage: ({ arg }) => { if (parts) inbox.go(stageOf(arg)); },
    clipboard: () => parts?.upload.readClipboard(),
    readImage: ({ arg }) => parts?.quick.readClipboard(arg),
    removeImage: ({ arg }) => parts?.quick.removeImage(arg),
    classify: () => parts?.quick.classify(),
    questionText: () => parts?.quick.questionText(),
    answerText: () => parts?.quick.answerText(),
    openLabels: ({ el }) => parts?.quick.openLabels(el),
    reset: () => parts?.quick.reset(),
    submit: () => parts?.quick.submit(),
    boardAdd: ({ el, event }) => parts?.quick.boardAdd(el, event?.shiftKey),
    gridFilter: ({ arg }) => parts?.grid.filter(arg),
    gridSelect: ({ arg, el }) => parts?.grid.select(arg, el.checked),
    gridAll: ({ el }) => parts?.grid.selectAll(el.checked),
    gridClear: () => parts?.grid.clear(),
    gridOpen: ({ arg }) => parts?.grid.open(arg),
    gridOpenSelected: () => parts?.grid.openSelected(),
    gridDetect: ({ arg }) => parts?.grid.detect(arg),
    gridApplyLast: () => parts?.grid.applyLast(),
    gridWhole: () => parts?.grid.whole(),
    gridDiscard: () => parts?.grid.discard(),
    processOpen: ({ arg, event }) => parts?.process.open(arg, event),
    processSelect: ({ arg, el }) => parts?.process.select(arg, el.checked),
    processQueueAll: ({ el }) => parts?.process.queueAll(el.checked),
    processLayout: ({ el }) => parts?.process.layout(el.value),
    processDetectSelected: ({ arg }) => parts?.process.detectSelected(arg),
    processApplyLastSelected: () => parts?.process.applyLastSelected(),
    processStep: ({ arg }) => parts?.process.step(Number(arg)),
    processRole: ({ arg }) => parts?.process.role(arg),
    processRegion: ({ arg, event }) => parts?.process.region(arg, event),
    processDelete: ({ arg }) => parts?.process.deleteRegion(arg),
    processConvert: ({ arg }) => parts?.process.convert(arg),
    processExtract: ({ arg }) => parts?.process.extract(arg),
    processText: ({ arg, el }) => parts?.process.text(arg, el.value),
    processDrawCard: ({ arg }) => parts?.process.drawCard(arg),
    processDetectCurrent: ({ arg }) => parts?.process.detectCurrent(arg),
    processWholeImage: () => parts?.process.whole(),
    processApplyLast: () => parts?.process.applyLast(),
    processClearBoxes: () => parts?.process.clear(),
    processAddCard: () => parts?.process.addCard(),
    processDiscardCurrent: () => parts?.process.discardCurrent(),
    processExtractAll: () => parts?.process.extractAll(),
    processMarkReady: () => parts?.process.markReady(),
    cardSelect: ({ arg, el }) => parts?.cards.select(arg, el.checked),
    cardAll: ({ el }) => parts?.cards.selectAll(el.checked),
    cardField: ({ arg, el }) => parts?.cards.field(arg, el.value),
    cardLabels: ({ arg, el }) => parts?.cards.openLabels(arg, el),
    cardClassify: ({ arg }) => parts?.cards.classify(arg),
    cardClassifySelected: () => parts?.cards.classifySelected(),
    cardCommit: ({ arg }) => parts?.cards.commit(arg),
    cardCommitSelected: () => parts?.cards.commitSelected(),
    cardBack: ({ arg }) => parts?.cards.back(arg),
    trainRefresh: () => parts?.train.refresh(),
    trainFormat: ({ event }) => parts?.train.format(event),
    trainPolicy: ({ arg, event }) => parts?.train.policy(arg, event),
    trainSave: () => parts?.train.save(),
    trainCleanup: ({ arg }) => parts?.train.cleanup(arg === 'crops'),
  },
  keys: Object.fromEntries(['q', 'a', 'x', 'delete', 'backspace', 'enter', 'mod+enter', 'escape']
    .map(name => [name, () => parts?.process.key(name) ?? false])),
};
