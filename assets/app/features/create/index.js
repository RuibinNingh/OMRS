/** 录入题目页外壳：上传入口已迁，旧工作区其余内容逐块迁入本目录。 */
import { morph } from '../../core/dom.js';
import { flowView } from './view.js';
import { createUpload } from './upload.js';

let upload = null;

export const page = {
  id: 'create', title: '录入题目', workbench: true,
  mount(root, ctx) {
    const flow = root.querySelector('#create-flow');
    morph(flow, flowView());
    upload = createUpload(root, ctx.bus);
    // 旧收件箱控制器仍负责列表和其它工作区，直到相应子模块迁移完成。
    window.inboxInit?.();
    return () => { upload?.dispose(); upload = null; };
  },
  actions: {
    clipboard: () => upload?.readClipboard(),
  },
};
