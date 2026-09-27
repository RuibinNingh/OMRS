/**
 * 展示板板详情的浏览器接线（P7 第 6 轮起）：缺省 I/O、模块单例 boardDetail()、接到 domain 端口、窗口级监听。
 * 控制器本身（状态与操作）在 detail.js，只经 deps 碰外界，node 单测直接用 createBoardDetail 注入替身；这里是唯一给它
 * 接上真实 I/O 的地方。展示板页（index.js）、过渡桥（legacy-bridge.js 的 installBoardBridge）都拿这个单例。
 */
import { post as apiPost, get as apiGet } from '../../core/api.js';
import { toast as uiToast } from '../../ui/toast.js';
import { dialog as uiDialog, confirm as uiConfirm } from '../../ui/dialog.js';
import { allItems } from '../../domain/items.js';
import { listLabels } from '../../domain/labels/index.js';
import { viewQ } from '../../domain/question/index.js';
import { boardHintText } from '../../domain/board/boards.js';
import { connectBoardDetail } from '../../domain/board/detail-port.js';
import { createBoardDetail } from './detail.js';
import * as preview from './preview.js';

/** 旧 api() 语义：成功返回 data，失败抛 Error（打印协调、保存队列都按它写）。 */
async function legacyCall(promise) {
  const res = await promise;
  if (!res?.ok) throw new Error(res?.error?.message || '请求失败');
  return res.data || {};
}

/** 缺省 I/O；rejected（锁定确认被拒时让页面放掉焦点）由展示板页挂载时经 configure 接上。 */
export function defaultBoardDetailDeps() {
  const g = globalThis;
  return {
    get: path => legacyCall(apiGet(path)),
    post: (path, body) => legacyCall(apiPost(path, body || {})),
    toast: (text, options) => uiToast(text, options),
    confirm: (title, options) => uiConfirm(title, options),
    dialog: spec => uiDialog(spec),
    items: () => allItems(),
    labels: () => listLabels(),
    storage: () => g.localStorage,
    preview,
    /** 展示板页当前是否显示（常驻预览只在显示时同步；加题 toast 决定要不要给「打开展示板」）。 */
    pageActive: () => !!g.document?.getElementById('panel-board')?.classList.contains('active'),
    gotoBoard: () => { g.__omrs?.router.go('board'); },
    openQuestion: (uid, list) => viewQ(uid, list),
    setTimer: (fn, ms) => setTimeout(fn, ms),
    clearTimer: id => clearTimeout(id),
    beacon: (url, blob) => !!g.navigator?.sendBeacon?.(url, blob),
    rejected: null,
  };
}

let single = null;
/** 页面、过渡桥与 domain 端口共用的单例；第一次取时把实现接进 detail-port（板列表写操作、选板浮层经它冲刷 / 重读 / 加题）。 */
export function boardDetail() {
  if (!single) {
    single = createBoardDetail(defaultBoardDetailDeps());
    const d = single;
    connectBoardDetail({
      flush: async () => (await d.flush()) !== false,
      reload: () => d.reloadData(),
      detail: () => d.detail(),
      add: (id, uids, options) => d.addToBoard(id, uids, options || {}),
      open: id => { d.gotoBoard(); return d.load(id); },
      adopt: board => d.adoptDetail(board),
    });
  }
  return single;
}

/**
 * 窗口级监听，只装一次（经过渡桥 installBoardBridge 调用）：关页落盘、独立打印窗口回传，以及各页「加入展示板」按钮
 * （[data-board-hint]）悬停 / 聚焦时现算说明文字——默认目标是上次用的板，随时会变。
 */
let windowBound = false;
export function installBoardWindow(win) {
  if (windowBound || !win?.addEventListener) return;
  windowBound = true;
  const d = boardDetail();
  win.addEventListener('beforeunload', () => d.beforeUnload());
  win.addEventListener('message', event => d.handleMessage(event));
  const stamp = event => {
    const button = event.target?.closest?.('[data-board-hint]');
    if (button) button.title = boardHintText();
  };
  win.document?.addEventListener('pointerover', stamp, true);
  win.document?.addEventListener('focusin', stamp, true);
}
