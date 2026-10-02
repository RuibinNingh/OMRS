/** 助手引用芯片与侧栏状态，用业务日期判断到期。 */
import { escape } from '../../core/html.js';
import { get } from '../../core/api.js';
import { businessToday, dayKey } from '../../core/date.js';
import { itemsNow } from '../../domain/data.js';

const today = () => dayKey(businessToday());
export function refRenderer(code) {
  const item = itemsNow().find(i => i.uid === code);
  if (item) {
    const tone = item.suspended ? 'off' : item.is_leech ? 'leech' : item.due_date && item.due_date <= today() ? 'due' : 'ok';
    return `<button type="button" class="ast-ref" data-action="assistant.openQ" data-arg="${escape(code)}"><i class="ast-ref__dot is-${tone}"></i>${escape(code)}</button>`;
  }
  if (/^(EXP|SES|FIXTURE)-[\w-]+$/.test(code)) return `<button type="button" class="ast-ref" data-action="assistant.openSession" data-arg="${escape(code)}">${escape(code)}</button>`;
  if (/^CMT-\d{6}$/.test(code)) return `<span class="ast-ref ast-ref--commit">${escape(code)}</span>`;
  return `<code>${escape(code)}</code>`;
}
/** 侧栏入口：未启用时隐藏；运行中显示活动点，等确认时显示角标。main.js 启动时调用一次。 */
export async function syncAssistantNav(doc = document, status) {
  const st = status || (await get('/api/agent/status')).data;
  const tab = doc.querySelector('.tab[data-tab="assistant"]');
  if (!tab || !st) return;
  tab.hidden = !st.enabled;
  const active = (st.active || [])[0];
  tab.classList.toggle('is-live', !!active);
  tab.classList.toggle('is-waiting', active?.status === 'waiting');
}
