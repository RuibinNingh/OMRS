/** 录入题目页外壳：上传入口已迁，旧工作区其余内容逐块迁入本目录。 */
import { morph } from '../../core/dom.js';
import { flowView } from './view.js';
import { createUpload } from './upload.js';
import { createQuick } from './quick.js';

let upload = null;
let quick = null;

export const page = {
  id: 'create', title: '录入题目', workbench: true,
  mount(root, ctx) {
    const flow = root.querySelector('#create-flow');
    morph(flow, flowView());
    upload = createUpload(root, ctx.bus);
    quick = createQuick(root, ctx);
    // 旧收件箱控制器仍负责列表和其它工作区，直到相应子模块迁移完成。
    window.inboxInit?.();
    return () => { upload?.dispose(); quick?.dispose(); upload = null; quick = null; };
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
  },
};
