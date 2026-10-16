/** 独立作业帮页面：来源、题框、候选、保真识别与核对入库。 */
import { createZuoyebang } from './zyb.js';
let workspace = null;
export const page = {
  id: 'zuoyebang', title: '作业帮', workbench: true,
  mount(root, ctx) {
    workspace = createZuoyebang(root, ctx);
    void workspace.enter();
    return () => { workspace?.dispose(); workspace = null; };
  },
  actions: {
    zybRegion: ({ arg }) => workspace?.region(arg),
    zybNext: () => workspace?.next(),
    zybKeep: () => workspace?.keep(),
    zybBoxes: ({ el }) => workspace?.boxes(el.checked),
    zybAdjust: () => workspace?.adjust(),
    zybCamera: () => workspace?.camera(),
    zybCapture: () => workspace?.capture(),
    zybSource: ({ arg }) => workspace?.source(arg),
    zybPaste: () => workspace?.paste(),
    zybMenu: ({ arg }) => workspace?.menu(arg),
    zybLogin: () => workspace?.login(),
    zybAccount: ({ arg }) => workspace?.account(arg),
    zybSettings: () => workspace?.settings(),
    zybSearch: () => workspace?.search(),
    zybSelect: ({ arg }) => workspace?.select(arg),
    zybRender: () => workspace?.render(),
    zybExtract: () => workspace?.extract(),
    zybRole: ({ arg }) => workspace?.role(arg),
    zybZoom: ({ arg }) => workspace?.zoom(arg),
    zybHtml: () => workspace?.html(),
    zybExpand: () => workspace?.expand(),
    zybMode: ({ arg }) => workspace?.mode(arg),
    zybLabels: ({ el }) => workspace?.labels(el),
    zybCommit: () => workspace?.commit(),
    zybHistory: ({ arg }) => workspace?.history(arg),
    zybBoard: ({ el, event }) => workspace?.board(el, event?.shiftKey),
    zybOpen: () => workspace?.open(),
  },
};
