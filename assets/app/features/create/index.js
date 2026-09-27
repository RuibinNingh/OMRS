/** 录入题目页外壳：旧工作区保留在 #create-app，逐块迁入本目录。 */
import { morph } from '../../core/dom.js';
import { flowView } from './view.js';

export const page = {
  id: 'create', title: '录入题目', workbench: true,
  mount(root) {
    const flow = root.querySelector('#create-flow');
    morph(flow, flowView());
    // 旧收件箱控制器仍负责工作区内容和上传，直到相应子模块迁移完成。
    window.inboxInit?.();
    return () => {};
  },
};
