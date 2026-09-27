/** 收件箱分步迁移时的旧控制器适配：网格与处理区共用选择和当前图片。 */
const source = () => globalThis.__omrsInbox;

export const snapshot = () => source()?.snapshot() || { items: [], selected: new Set(), stage: 'upload' };
export const refreshLegacy = () => source()?.refresh();
export const openLegacy = id => source()?.open(id);
export const reloadLegacy = () => source()?.reload();
export const detectLegacy = provider => source()?.detect(provider);
export const applyLastLegacy = () => source()?.applyLast();
export const wholeLegacy = () => source()?.whole();
