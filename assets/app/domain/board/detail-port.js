/**
 * 板详情的端口（P7 第 6 轮起；取代第 5 轮的过渡适配器 legacy.js）：板列表（boards.js）与选板浮层（source.js）要在写操作前后
 * 冲刷保存队列、整页重读、加题、打开某块板、读当前详情，这些都归 features/board/detail.js。domain 不 import features，
 * 所以由 detail.js 在创建单例时经 connectBoardDetail() 把实现接进来（依赖倒置）；没接上之前是安全的空实现。
 */
const hooks = {
  flush: async () => true,
  reload: async () => {},
  detail: () => null,
  add: async () => null,
  open: async () => {},
  adopt: () => {},
};

/** features/board/detail.js 调用：{ flush, reload, detail, add, open, adopt } 任意子集。 */
export function connectBoardDetail(patch = {}) {
  Object.entries(patch).forEach(([name, fn]) => { if (name in hooks && typeof fn === 'function') hooks[name] = fn; });
}

/** boards.js 的缺省钩子与选板浮层的数据来源都经这里转调（按调用时的实现，不在 import 时取值）。 */
export const boardDetailPort = Object.freeze({
  /** 写操作之前冲刷保存队列：失败返回 false，操作放弃。 */
  flush: () => hooks.flush(),
  /** 写操作之后整页重读（板列表 + 当前板详情）。 */
  reload: () => hooks.reload(),
  /** 当前板详情（重命名 / 备注找不到列表项时兜底）。 */
  detail: () => hooks.detail(),
  /** 加题：返回服务端的板（含 added_uids）或 null；失败时 detail.js 自己弹错误 toast。 */
  add: (id, uids, options) => hooks.add(id, uids, options || {}),
  /** 切到展示板页并打开某块板。 */
  open: id => hooks.open(id),
  /** 选板浮层新建板后先把它设为当前详情（随后整页重读）。 */
  adopt: board => hooks.adopt(board),
});
