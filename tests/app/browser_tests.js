// ui 组件的浏览器单测（依赖真实 DOM：对话框焦点、toast 队列、菜单键盘、拖放……）。
// tests/app/run_browser.py 用 playwright 打开 tests/app/browser.html 执行；结果写到 window.__results。
import { html, raw } from '/assets/app/core/html.js';
import { render } from '/assets/app/core/dom.js';
import { icon, installIcons, ICON_NAMES } from '/assets/app/ui/icon.js';
import { button } from '/assets/app/ui/button.js';
import { input } from '/assets/app/ui/field.js';
import { select } from '/assets/app/ui/select.js';
import { dialog, confirm, prompt } from '/assets/app/ui/dialog.js';
import { openImageViewer } from '/assets/app/ui/image-viewer.js';
import { openDrawer } from '/assets/app/ui/drawer.js';
import { openCount, hostGuest, releaseGuest, guestOpen } from '/assets/app/ui/overlay.js';
import { toast } from '/assets/app/ui/toast.js';
import { openMenu } from '/assets/app/ui/menu.js';
import { tabs, bindTabs } from '/assets/app/ui/tabs.js';
import { showTooltip, hideTooltip } from '/assets/app/ui/tooltip.js';
import { filedrop, bindFileDrop, acceptsFile } from '/assets/app/ui/filedrop.js';
import { segmented } from '/assets/app/ui/segmented.js';
import { switchControl } from '/assets/app/ui/switch.js';
import { table } from '/assets/app/ui/table.js';
import { badge } from '/assets/app/ui/badge.js';
import { skeleton, showAfter } from '/assets/app/ui/skeleton.js';
import { empty } from '/assets/app/ui/empty.js';
import { status } from '/assets/app/ui/status.js';
import { progress } from '/assets/app/ui/progress.js';
import { kbd } from '/assets/app/ui/kbd.js';
import { stat } from '/assets/app/ui/stat.js';
import { card } from '/assets/app/ui/card.js';
import { tag } from '/assets/app/ui/tag.js';
import { registerCoreTests } from '/tests/app/core_tests.js';

const tests = [];
const test = (name, fn) => tests.push({ name, fn });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const assert = (cond, msg) => { if (!cond) throw new Error(msg || '断言失败'); };
const eq = (actual, expected, msg) => {
  if (actual !== expected) throw new Error(`${msg || '不相等'}：期望 ${JSON.stringify(expected)}，实际 ${JSON.stringify(actual)}`);
};
const stage = document.getElementById('stage');
const mount = result => { render(stage, result); return stage.firstElementChild; };
const key = (target, k) => target.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, cancelable: true }));
const height = el => Math.round(el.getBoundingClientRect().height);
const px = name => Math.round(parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name)));
const topDialog = () => [...document.querySelectorAll('dialog.ui-dialog:not(.is-closing)')].pop();

test('html：插值默认转义，raw 显式放行，写入后不产生元素', () => {
  const evil = '<img src=x onerror="window.__xss=1">';
  const el = mount(html`<p title="${evil}">${evil}${raw('<b>ok</b>')}</p>`);
  eq(el.querySelector('img'), null, '不应解析出 img');
  eq(el.querySelector('b').textContent, 'ok');
  eq(el.getAttribute('title'), evil);
});

test('dom：render 只接受 html`` 结果', () => {
  let threw = false;
  try { render(stage, '<p>x</p>'); } catch (e) { threw = e instanceof TypeError; }
  assert(threw, '传字符串应抛 TypeError');
});

test('icon：sprite 只注入一次，每个名字都有 symbol，未知名字报错，带 label 时可读', () => {
  installIcons(document);
  installIcons(document);
  eq(document.querySelectorAll('#ui-icon-sprite').length, 1);
  assert(ICON_NAMES.length >= 40, `图标不少于 40 个（现 ${ICON_NAMES.length}）`);
  ICON_NAMES.forEach(n => assert(document.getElementById(`ic-${n}`), `缺少 ic-${n}`));
  let threw = false;
  try { icon('no-such'); } catch (_) { threw = true; }
  assert(threw, '未知图标应报错');
  const labeled = mount(icon('search', { label: '搜索' }));
  eq(labeled.getAttribute('role'), 'img');
  eq(labeled.getAttribute('aria-label'), '搜索');
});

test('button：三档高度跟随 --ctl-sm/md/lg，紧凑密度同步变化', () => {
  const box = mount(html`<div>${button({ label: 'a', size: 'sm' })}${button({ label: 'b' })}${button({ label: 'c', size: 'lg' })}</div>`);
  const check = () => {
    const [s, m, l] = box.children;
    eq(`${height(s)}/${height(m)}/${height(l)}`, `${px('--ctl-sm')}/${px('--ctl-md')}/${px('--ctl-lg')}`);
  };
  check();
  eq(px('--ctl-md'), 32, '舒适密度 md 为 32');
  document.documentElement.dataset.density = 'compact';
  check();
  delete document.documentElement.dataset.density;
});

test('button：加载中禁用并标 aria-busy；仅图标带 aria-label；pressed 输出 aria-pressed', () => {
  const box = mount(html`<div>${button({ label: '保存', loading: true })}${button({ label: '更多', icon: 'more-h', iconOnly: true })}${button({ label: '表格', pressed: true })}</div>`);
  const [loading, only, pressed] = box.children;
  assert(loading.disabled && loading.getAttribute('aria-busy') === 'true', '加载中应禁用');
  eq(only.getAttribute('aria-label'), '更多');
  eq(only.querySelector('.ui-btn__label'), null);
  eq(pressed.getAttribute('aria-pressed'), 'true');
});

test('input / select / button 同一行同一档；select 上下内边距为 0（D3）', () => {
  const box = mount(html`<div>${input({ id: 't-in', label: '搜索' })}${select({ id: 't-sel', options: ['全部科目', '数学'], label: '科目' })}${button({ label: '筛选' })}</div>`);
  const hs = [...box.children].map(height);
  eq(new Set(hs).size, 1, `高度应一致：${hs}`);
  const cs = getComputedStyle(box.children[1]);
  eq(`${cs.paddingTop}/${cs.paddingBottom}`, '0px/0px');
});

test('dialog：模态打开、聚焦首个输入、Enter 确认并按 id 收集值', async () => {
  const pending = dialog({ title: '改名', body: html`<input class="ui-input" id="t-name" value="旧"><input type="checkbox" id="t-chk" checked>` });
  const el = topDialog();
  assert(el && el.open && el.matches(':modal'), '应以模态打开');
  eq(document.activeElement.id, 't-name');
  document.activeElement.value = '新名字';
  key(document.activeElement, 'Enter');
  const result = await pending;
  eq(result.ok, true);
  eq(result.values['t-name'], '新名字');
  eq(result.values['t-chk'], true);
});

test('dialog：长内容限制在视口内并由正文区滚动', async () => {
  const rows = Array.from({ length: 80 }, (_, i) => `<p>第 ${i + 1} 行长内容，用于验证对话框在受限高度下仍保留正文滚动区。</p>`).join('');
  const pending = dialog({ title: '长内容', body: html`<div id="t-long">${raw(rows)}</div>` });
  const el = topDialog();
  const panel = el.querySelector('.ui-dialog__panel');
  const body = el.querySelector('.ui-dialog__body');
  const bounds = panel.getBoundingClientRect();
  assert(bounds.top >= -1 && bounds.bottom <= innerHeight + 1, `面板应在视口内：${bounds.top}–${bounds.bottom}/${innerHeight}`);
  assert(body.scrollHeight > body.clientHeight, `正文应可滚动：${body.scrollHeight}/${body.clientHeight}`);
  body.scrollTop = body.scrollHeight;
  assert(body.scrollTop > 0, '正文滚动位置应改变');
  el.querySelector('[data-dialog-cancel]').click();
  eq((await pending).ok, false);
});

test('image-viewer：切图、缩放、Esc、焦点与背景滚动锁', async () => {
  const opener = mount(html`<button type="button">预览图片</button>`);
  opener.focus();
  openImageViewer([{ src: '/assets/app/omrs-icon.svg', label: '第一张' }, { src: '/assets/app/omrs-favicon.svg', label: '第二张' }]);
  const viewer = document.querySelector('dialog.ui-image-viewer');
  assert(viewer?.open && document.documentElement.classList.contains('ui-scroll-lock'), '应作为模态浮层打开');
  eq(viewer.querySelector('img').getAttribute('alt'), '第一张');
  viewer.querySelector('[data-image-action="next"]').click();
  eq(viewer.querySelector('img').getAttribute('alt'), '第二张');
  viewer.querySelector('[data-image-action="zoom"]').click();
  assert(viewer.classList.contains('is-zoomed'), '可缩放');
  key(document.activeElement, 'Escape');
  await sleep(360);
  eq(document.querySelector('dialog.ui-image-viewer'), null, 'Esc 关闭');
  eq(document.activeElement, opener, '焦点返回触发按钮');
});

test('dialog：Esc 取消且不外泄给 document；点遮罩取消；关闭后焦点回到触发元素', async () => {
  const opener = mount(html`<button type="button">打开</button>`);
  opener.focus();
  let leaked = 0;
  const spy = event => { if (event.key === 'Escape') leaked += 1; };
  document.addEventListener('keydown', spy);
  const pending = confirm('确认？');
  key(document.activeElement, 'Escape');
  eq(await pending, false);
  document.removeEventListener('keydown', spy);
  eq(leaked, 0, 'Esc 不应冒泡到 document 上的旧监听');
  await sleep(360);
  eq(document.activeElement, opener, '焦点应回到触发元素');
  eq(document.querySelector('dialog.ui-dialog'), null, '关闭后元素移除');
  const second = confirm('点遮罩');
  const el = topDialog();
  el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  eq(await second, false);
});

test('dialog：背景不可聚焦（焦点陷阱）、锁定滚动、危险确认默认聚焦「取消」', async () => {
  const outside = mount(html`<button type="button">外面</button>`);
  const pending = confirm('删除？', { danger: true });
  assert(document.documentElement.classList.contains('ui-scroll-lock'), '应锁定背景滚动');
  assert(document.activeElement.matches('.ui-dialog__foot [data-dialog-cancel]'), '危险确认默认聚焦取消');
  outside.focus();
  assert(document.activeElement !== outside, '背景元素不应拿到焦点');
  topDialog().querySelector('.ui-dialog__foot [data-dialog-cancel]').click();
  eq(await pending, false);
  assert(!document.documentElement.classList.contains('ui-scroll-lock'), '关闭后解除锁定');
});

test('dialog：嵌套时 Esc 只关最上层', async () => {
  const a = confirm('A');
  const b = confirm('B');
  eq(openCount(), 2);
  key(document.activeElement, 'Escape');
  eq(await b, false);
  eq(openCount(), 1);
  key(document.activeElement, 'Escape');
  eq(await a, false);
  eq(openCount(), 0);
});

const press = (el, keyName, extra = {}) => el.dispatchEvent(new KeyboardEvent('keydown', { key: keyName, bubbles: true, cancelable: true, ...extra }));
const stillOpen = el => el.open && !el.classList.contains('is-closing');

test('overlay：旧浮层作为客人放进最上层对话框；Esc 与点遮罩先让客人；宿主关闭时一并关掉客人', async () => {
  const pending = confirm('宿主');
  const host = topDialog();
  let closed = 0;
  const guest = () => { const node = document.createElement('div'); node.className = 't-guest'; node.tabIndex = -1; return node; };
  const a = guest();
  eq(hostGuest(a, { close: () => { closed += 1; a.remove(); releaseGuest(a); }, escape: true }), host, '应放进最上层对话框');
  assert(guestOpen(), '应登记为客人');
  a.focus();
  eq(document.activeElement, a, '客人在对话框里，能拿到焦点（不被 inert）');
  press(a, 'Escape');
  eq(closed, 1, 'Esc 先关客人');
  assert(stillOpen(host) && !guestOpen(), '宿主仍开着，客人已注销');
  const b = guest();
  hostGuest(b, { close: () => { closed += 1; b.remove(); releaseGuest(b); } });
  host.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  host.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  assert(stillOpen(host), '有客人时点遮罩不关宿主（客人自己处理点外面）');
  host.querySelector('.ui-dialog__foot [data-dialog-cancel]').click();
  eq(await pending, false);
  eq(closed, 2, '宿主关闭时先关客人');
  const loose = document.createElement('div');
  eq(hostGuest(loose), document.body, '没有模态对话框时放进 body');
  loose.remove();
});

test('dialog：onOk 返回 false 时留在对话框、确定按钮忙碌；dismissible 为函数；多行文本里 Enter 不确认、Ctrl+Enter 确认', async () => {
  let calls = 0;
  let settle = null;
  const pending = dialog({ title: '保存', body: html`<textarea class="ui-textarea" id="t-md">x</textarea>`, dismissible: () => false,
    onOk: () => { calls += 1; return new Promise(resolve => { settle = resolve; }); } });
  const el = topDialog();
  const text = el.querySelector('#t-md');
  press(text, 'Enter');
  eq(calls, 0, '多行文本里的 Enter 不确认');
  press(text, 'Escape');
  assert(stillOpen(el), 'dismissible() 为假时 Esc 不关');
  press(text, 'Enter', { ctrlKey: true });
  eq(calls, 1, 'Ctrl+Enter 确认');
  const ok = el.querySelector('.ui-dialog__foot [data-dialog-ok]');
  eq(ok.getAttribute('aria-busy'), 'true');
  settle(false);
  await sleep(0);
  assert(stillOpen(el) && !ok.hasAttribute('aria-busy') && !ok.disabled, 'onOk 返回 false：留在对话框、按钮复原');
  ok.click();
  settle(true);
  eq((await pending).ok, true);
});

test('dialog：returnFocus 返回的元素优先于打开前的焦点', async () => {
  const box = mount(html`<div><button type="button" id="t-a">A</button><button type="button" id="t-b">B</button></div>`);
  box.querySelector('#t-a').focus();
  const pending = dialog({ title: '交回焦点', returnFocus: () => box.querySelector('#t-b') });
  topDialog().querySelector('.ui-dialog__foot [data-dialog-cancel]').click();
  await pending;
  await sleep(360);
  eq(document.activeElement.id, 't-b');
});

test('prompt：返回去掉首尾空格的文字，取消返回 null', async () => {
  const first = prompt('名称', '  旧  ');
  const field = document.activeElement;
  eq(field.value, '  旧  ');
  field.value = '  新  ';
  key(field, 'Enter');
  eq(await first, '新');
  const second = prompt('名称');
  topDialog().querySelector('.ui-dialog__foot [data-dialog-cancel]').click();
  eq(await second, null);
});

test('drawer：以模态打开，关闭按钮关闭并回调', async () => {
  let closed = 'no';
  const drawer = openDrawer({ title: '筛选', body: html`<p>内容</p>`, onClose: r => { closed = r; } });
  assert(drawer.el.open && drawer.el.matches(':modal'));
  drawer.el.querySelector('[data-drawer-close]').click();
  eq(closed, false);
  await sleep(360);
  eq(drawer.el.isConnected, false);
});

test('toast：容器是 aria-live；error 用 role=alert；最多 3 条；同文同类合并', () => {
  document.querySelector('.ui-toaster')?.remove();
  toast('一');
  const host = document.querySelector('.ui-toaster');
  eq(host.getAttribute('aria-live'), 'polite');
  toast('二');
  toast('三');
  toast('四', { kind: 'error' });
  const live = () => [...host.querySelectorAll('.ui-toast:not(.is-leaving)')];
  eq(live().length, 3, '最多同时 3 条');
  eq(live()[2].getAttribute('role'), 'alert');
  toast('四', { kind: 'error' });
  eq(live().filter(t => t.dataset.text === '四').length, 1, '同文同类合并');
});

test('toast：操作按钮回调后关闭；到期自动移除', async () => {
  let hit = 0;
  const t = toast('已移出', { kind: 'ok', actions: [{ label: '撤销', onClick: () => { hit += 1; } }] });
  t.el.querySelector('[data-toast-act]').click();
  eq(hit, 1);
  assert(t.el.classList.contains('is-leaving'));
  const quick = toast('很快消失', { duration: 50 });
  await sleep(520);
  eq(quick.el.isConnected, false, '到期后应移除');
});

test('menu：聚焦首个可用项；↓ 跳过禁用；点击返回 value；Esc 返回 null 并还焦点；点外面关闭', async () => {
  const anchor = mount(html`<button type="button">菜单</button>`);
  anchor.focus();
  const items = [{ value: 'a', label: 'A' }, { value: 'b', label: 'B', disabled: true }, { value: 'c', label: 'C' }];
  const first = openMenu(anchor, items);
  eq(document.activeElement.textContent.trim(), 'A');
  eq(anchor.getAttribute('aria-expanded'), 'true');
  key(document.activeElement, 'ArrowDown');
  eq(document.activeElement.textContent.trim(), 'C', '应跳过禁用项');
  document.activeElement.click();
  eq(await first, 'c');
  const second = openMenu(anchor, items);
  key(document.activeElement, 'Escape');
  eq(await second, null);
  eq(document.activeElement, anchor, 'Esc 后焦点回到触发按钮');
  const third = openMenu(anchor, items);
  document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
  eq(await third, null);
  eq(document.querySelector('.ui-menu'), null);
});

test('tabs：方向键与点击切换 aria-selected / tabindex / 面板，并派发 ui-tabs:change', () => {
  const box = mount(html`<div>${tabs({ label: 't', idPrefix: 'tt', value: 'a', items: [{ id: 'a', label: 'A', panel: 'pa' }, { id: 'b', label: 'B', panel: 'pb' }, { id: 'c', label: 'C', disabled: true }] })}<div id="pa">A</div><div id="pb" hidden>B</div></div>`);
  const list = bindTabs(box.querySelector('[role="tablist"]'));
  let changed = null;
  list.addEventListener('ui-tabs:change', event => { changed = event.detail.id; });
  const [ta, tb] = list.querySelectorAll('[role="tab"]');
  key(ta, 'ArrowRight');
  eq(tb.getAttribute('aria-selected'), 'true');
  eq(`${ta.tabIndex}/${tb.tabIndex}`, '-1/0');
  eq(changed, 'b');
  eq(document.getElementById('pa').hidden, true);
  eq(document.getElementById('pb').hidden, false);
  key(tb, 'ArrowRight');
  eq(ta.getAttribute('aria-selected'), 'true', '跳过禁用项并循环');
  tb.click();
  eq(tb.getAttribute('aria-selected'), 'true');
});

test('tooltip：显示时挂 aria-describedby 并定位，隐藏时撤掉', () => {
  const target = mount(html`<button type="button" data-tooltip="复制 UID">复制</button>`);
  const tip = showTooltip(target);
  eq(tip.textContent, '复制 UID');
  eq(target.getAttribute('aria-describedby'), tip.id);
  assert(tip.classList.contains('is-visible'));
  assert(tip.style.getPropertyValue('--tip-x').endsWith('px'), '应写入位置变量');
  hideTooltip();
  eq(target.hasAttribute('aria-describedby'), false);
  assert(!tip.classList.contains('is-visible'));
});

test('filedrop：accept 过滤、拖入高亮、放下回调、不符合类型标 is-error', () => {
  eq(acceptsFile({ name: 'a.PNG', type: 'image/png' }, 'image/*'), true);
  eq(acceptsFile({ name: 'note.md', type: '' }, '.md'), true);
  eq(acceptsFile({ name: 'a.txt', type: 'text/plain' }, '.md,image/*'), false);
  const zone = mount(filedrop({ id: 't-fd', accept: 'image/*', multiple: true }));
  let got = [];
  bindFileDrop(zone, files => { got = files; });
  zone.dispatchEvent(new DragEvent('dragenter', { bubbles: true, cancelable: true }));
  assert(zone.classList.contains('is-dragover'));
  const dt = new DataTransfer();
  dt.items.add(new File(['x'], 'a.png', { type: 'image/png' }));
  dt.items.add(new File(['y'], 'b.txt', { type: 'text/plain' }));
  zone.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
  eq(got.map(f => f.name).join(','), 'a.png');
  assert(zone.classList.contains('is-error'));
  assert(!zone.classList.contains('is-dragover'));
});

test('switch / segmented：原生控件与角色', () => {
  const sw = mount(switchControl({ id: 't-sw', label: '开', checked: true }));
  eq(sw.querySelector('input').getAttribute('role'), 'switch');
  eq(sw.querySelector('input').checked, true);
  const seg = mount(segmented({ name: 't-seg', label: '视图', value: 'b', options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }] }));
  eq(seg.getAttribute('role'), 'radiogroup');
  eq(seg.querySelector('input:checked').value, 'b');
});

test('table：每格带 data-label；空表 colspan 覆盖全部列；选中行 aria-selected', () => {
  const cols = [{ key: 'id', label: 'UID' }, { key: 'n', label: '次数', num: true }];
  const wrap = mount(table({ columns: cols, rows: [{ id: 'A', n: 1 }, { id: 'B', n: 2 }], selected: ['B'], stack: true }));
  eq(wrap.querySelector('td').dataset.label, 'UID');
  eq(wrap.querySelector('tr[data-key="B"]').getAttribute('aria-selected'), 'true');
  assert(wrap.querySelector('td.is-num'), '数字列带 is-num');
  const emptyWrap = mount(table({ columns: cols, rows: [], empty: '没有数据' }));
  eq(emptyWrap.querySelector('.ui-table__empty td').colSpan, 2);
});

test('badge / status / progress / kbd / empty / tag / card / stat：结构与读屏属性', () => {
  eq(mount(badge(128)).textContent, '99+');
  eq(mount(status({ tone: 'danger', text: '失败' })).getAttribute('role'), 'alert');
  const bar = mount(progress({ value: 3, max: 12, label: '复习' }));
  eq(bar.tagName, 'PROGRESS');
  eq(bar.value, 3);
  assert(mount(progress({ label: '扫描' })).matches(':indeterminate'), '不传 value 为不定进度');
  eq(mount(kbd('Ctrl', 'K')).querySelectorAll('kbd').length, 2);
  assert(mount(empty({ title: '空', hint: '下一步', action: { label: '新建' } })).querySelector('.ui-btn--primary'), '空状态带主操作');
  eq(mount(tag({ label: 'x', removable: true })).querySelector('.ui-tag__remove').getAttribute('aria-label'), '移除 x');
  eq(mount(card({ title: '卡', body: '内容', interactive: true })).tabIndex, 0);
  assert(mount(stat({ label: '待复习', value: 12, delta: '+3', trend: 'up' })).querySelector('.ui-stat__delta--up'));
});

test('skeleton：showAfter 超时前隐藏；取消后保持隐藏', async () => {
  const shown = mount(skeleton({ lines: 2 }));
  showAfter(shown, 30);
  eq(shown.hidden, true);
  await sleep(80);
  eq(shown.hidden, false);
  const hidden = mount(skeleton());
  showAfter(hidden, 30)();
  await sleep(80);
  eq(hidden.hidden, true);
});

async function run() {
  const results = [];
  for (const t of tests) {
    const started = performance.now();
    try {
      await t.fn();
      results.push({ name: t.name, ok: true, ms: Math.round(performance.now() - started) });
    } catch (error) {
      results.push({ name: t.name, ok: false, error: String(error && error.message ? error.message : error) });
    }
    document.querySelectorAll('dialog').forEach(d => { if (d.open) d.close(); d.remove(); });
    document.documentElement.classList.remove('ui-scroll-lock');
    render(stage, html``);
  }
  window.__results = results;
  window.__done = true;
  render(document.getElementById('summary'), html`${results.filter(r => r.ok).length} / ${results.length} 通过`);
}

registerCoreTests({ test, assert, eq, stage });
run();
