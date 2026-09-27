/**
 * 旧页面登记表（过渡期）：原 app.js 里 switchTab 的标题表、工作台页列表和进入页面时的初始化 if 链原样搬到这里。
 * 每项 { id, title, workbench, enter(win) }：enter 在每次进入该页时调用（与原 switchTab 相同，不等待其完成）。
 * 某页迁到 assets/app/features/ 后，用它的页面契约（mount / unmount）替换对应一项；P8 时本文件删除。
 */
const call = (win, name) => (typeof win[name] === 'function' ? win[name]() : undefined);

export const LEGACY_PAGES = [
  { id: 'board', title: '展示板', workbench: true, enter: win => call(win, 'boardInit') },
];
