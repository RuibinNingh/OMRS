/**
 * gallery 的真实交互演示：按钮 data-action="demo.<名字>" 触发。只服务陈列页。
 */
import { html } from './core/html.js';
import { toast } from './ui/toast.js';
import { dialog, confirm, prompt } from './ui/dialog.js';
import { openDrawer } from './ui/drawer.js';
import { openMenu } from './ui/menu.js';
import { field, input } from './ui/field.js';
import { select } from './ui/select.js';
import { switchControl } from './ui/switch.js';
import { button } from './ui/button.js';
import { LONG } from './gallery-sections.js';
import { MENU_ITEMS } from './gallery-sections-2.js';

const done = (ok, text) => toast(ok ? text : '已取消', { kind: ok ? 'ok' : 'info' });

export const DEMOS = {
  dialog: () => dialog({
    title: '重命名分组', hint: '只影响展示板里的显示名称。', okText: '保存',
    body: field({ label: '分组名称', id: 'gdd-name', control: input({ id: 'gdd-name', value: '第三章 电磁学' }) }),
  }).then(r => done(r.ok, `已保存：${r.values['gdd-name']}`)),
  confirm: () => confirm('删除这个展示板？', { hint: '板上的 12 道题不会被删除，只是从板上移走。', danger: true, okText: '删除' })
    .then(ok => done(ok, '已删除展示板')),
  prompt: () => prompt('新建视图', '我的视图', { placeholder: '视图名称' }).then(v => done(v != null, `已新建：${v}`)),
  long: () => dialog({
    title: LONG, hint: LONG, size: 'md', hideCancel: true, okText: '知道了',
    body: html`${Array.from({ length: 20 }, (_, i) => html`<p>第 ${i + 1} 段：${LONG}</p>`)}`,
  }),
  drawer: () => openDrawer({
    title: '筛选条件',
    body: html`<div class="gl-stack">${field({ label: '科目', id: 'gdd-s', control: select({ id: 'gdd-s', options: ['全部科目', '数学', '物理', '化学'] }) })}${field({ label: '关键词', id: 'gdd-k', control: input({ id: 'gdd-k', placeholder: 'UID / 知识点' }) })}${switchControl({ id: 'gdd-sw', label: '只看逾期', checked: true })}</div>`,
    footer: html`${button({ label: '重置' })}${button({ label: '应用', variant: 'primary' })}`,
  }),
  menu: anchor => openMenu(anchor, MENU_ITEMS, { label: '题目操作' }).then(v => { if (v != null) toast(`选择了：${v}`); }),
  'toast-info': () => toast('已同步 3 个展示板', { kind: 'info' }),
  'toast-ok': () => toast('已复制题目 UID', { kind: 'ok' }),
  'toast-warn': () => toast('这些题已经在「考前冲刺」里了', { kind: 'warn' }),
  'toast-error': () => toast('保存失败：服务暂时不可用', { kind: 'error' }),
  'toast-action': () => toast('已移出展示板', { kind: 'ok', actions: [{ label: '撤销', onClick: () => toast('已撤销', { kind: 'ok' }) }] }),
  'toast-long': () => toast(`${LONG}。${LONG}`, { kind: 'warn' }),
  'toast-many': () => { for (let i = 1; i <= 5; i += 1) toast(`第 ${i} 条通知`, { kind: 'info' }); },
};
