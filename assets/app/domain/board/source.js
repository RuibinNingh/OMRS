/**
 * 选板浮层的数据来源与写入口（P7 第 4 轮起；第 5 轮起板列表部分换成新实现，第 6 轮起板详情部分经端口）：
 * - 板列表、文件夹、上次用的板、文件夹折叠状态 —— domain/board/boards.js（数据所有者，展示板页与浮层共用同一份）；
 * - 加题（含保存队列冲刷、撤销 toast）、整页重读、打开某块板 —— 板详情的所有者 features/board/detail.js，经 detail-port.js 转调。
 * 浮层只经这个对象碰数据；测试经 picker.js 的 configureBoardPicker({ source }) 换成替身。
 */
import { boardList, boardFolders, adoptBoards, boardLastId, boardRemember, boardFolderCollapsed, boardFolderToggle } from './boards.js';
import { boardDetailPort } from './detail-port.js';

export const boardSource = Object.freeze({
  boards: () => boardList(),
  folders: () => boardFolders(),
  /** 采纳 /api/boards 的结果（展示板页与浮层共用同一份缓存，采纳后展示板页随之重绘）。 */
  adopt: ({ boards = [], folders = [] } = {}) => adoptBoards({ boards, folders }),
  lastId: () => boardLastId(),
  remember: id => boardRemember(id),
  collapsed: () => boardFolderCollapsed(),
  toggleFolder: (id, force) => boardFolderToggle(id, force),
  /** 加题：返回服务端的板（含 added_uids）或 null；失败时 detail.js 自己弹错误 toast。 */
  add: (id, uids, options) => boardDetailPort.add(id, uids, options || {}),
  reload: () => boardDetailPort.reload(),
  open: id => boardDetailPort.open(id),
  /** 新建板之后把它设为展示板页的当前板。 */
  adoptDetail: board => boardDetailPort.adopt(board),
});
