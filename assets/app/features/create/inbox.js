/** 收件箱单例：真实 I/O 接到 core/api 与 ui/toast；页面挂载时 connectInbox(bus) 接上通知通道。模块级，切页返回后状态保留。 */
import { get, post } from '../../core/api.js';
import { toast } from '../../ui/toast.js';
import { createInboxStore } from './inbox-store.js';

let bus = null;

/** 收件箱提示：带操作按钮的停留 8 秒，其余 3.2 秒。 */
export function notify(text, kind, action) {
  const actions = action && action.label && typeof action.onClick === 'function' ? [{ label: action.label, onClick: action.onClick }] : [];
  toast(text, { kind: kind === 'warn' ? 'warn' : 'ok', actions, duration: actions.length ? 8000 : 3200 });
}

export const inbox = createInboxStore({
  api: { get, post },
  emit: type => bus?.emit(type),
  notify,
});

export function connectInbox(next) {
  bus = next;
  return () => { if (bus === next) bus = null; };
}
