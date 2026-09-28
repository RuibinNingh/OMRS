// core/ 里依赖真实 DOM 的模块：dom.js 的 morph、events.js 的委托、keys.js 的按页快捷键；外加外壳的页面契约生命周期。
// 由 tests/app/browser_tests.js 调用 registerCoreTests() 登记，与组件单测一起跑。
import { html, each } from '/assets/app/core/html.js';
import { morph } from '/assets/app/core/dom.js';
import { defineActions, bindEvents } from '/assets/app/core/events.js';
import { registerKeys, setScope, bindKeys } from '/assets/app/core/keys.js';
import { startShell } from '/assets/app/shell.js';

export function registerCoreTests({ test, assert, eq, stage }) {
  const list = items => html`<ul>${each(items, it => it.id, it => html`<li data-key="${it.id}" class="${it.cls || ''}">${it.text}</li>`)}</ul>`;

  test('morph：按 data-key 重排时复用原节点，文本与属性差量更新，多余节点删除', () => {
    morph(stage, list([{ id: 'a', text: 'A' }, { id: 'b', text: 'B' }, { id: 'c', text: 'C' }]));
    const ul = stage.firstElementChild;
    const [a, b, c] = ul.children;
    a.__mark = 'kept';
    morph(stage, list([{ id: 'c', text: 'C2', cls: 'on' }, { id: 'a', text: 'A' }, { id: 'd', text: 'D' }]));
    eq(stage.firstElementChild, ul, '根下的 ul 应被复用');
    eq([...ul.children].map(li => li.dataset.key).join(''), 'cad');
    eq(ul.children[0], c, 'c 节点被移动而不是重建');
    eq(ul.children[1], a, 'a 节点被复用');
    eq(ul.children[1].__mark, 'kept');
    eq(ul.children[0].textContent, 'C2');
    eq(ul.children[0].className, 'on');
    assert(!b.isConnected, 'b 节点应被删除');
  });

  test('morph：聚焦的输入框保留值与选区；未聚焦的按新模板同步值', () => {
    const view = v => html`<div><input id="m-focus" value="${v}"><input id="m-other" value="${v}"></div>`;
    morph(stage, view('旧值'));
    const focused = document.getElementById('m-focus');
    focused.focus();
    focused.value = '正在输入';
    focused.setSelectionRange(2, 4);
    morph(stage, view('新值'));
    eq(document.getElementById('m-focus'), focused, '同一个输入框');
    eq(document.activeElement, focused, '焦点仍在');
    eq(focused.value, '正在输入', '聚焦的值不被覆盖');
    eq(`${focused.selectionStart},${focused.selectionEnd}`, '2,4', '选区保留');
    eq(document.getElementById('m-other').value, '新值');
    focused.blur();
  });

  test('morph：data-morph="skip" 整棵不动；data-hash 相同跳过、不同则更新', () => {
    morph(stage, html`<div><div id="m-skip" data-morph="skip">第三方</div><p id="m-hash" data-hash="h1">公式 1</p></div>`);
    const skip = document.getElementById('m-skip');
    skip.textContent = '第三方改过的内容';
    const hashed = document.getElementById('m-hash');
    hashed.textContent = 'KaTeX 渲染结果';
    morph(stage, html`<div><div id="m-skip" data-morph="skip">模板内容</div><p id="m-hash" data-hash="h1">公式 1</p></div>`);
    eq(skip.textContent, '第三方改过的内容');
    eq(hashed.textContent, 'KaTeX 渲染结果', 'hash 相同时不重算');
    morph(stage, html`<div><div id="m-skip" data-morph="skip">模板内容</div><p id="m-hash" data-hash="h2">公式 2</p></div>`);
    eq(document.getElementById('m-hash').textContent, '公式 2', 'hash 变了就更新');
  });

  test('morph：标签不同时替换节点；复选框与下拉同步选中态', () => {
    morph(stage, html`<div><span>x</span><input type="checkbox" id="m-chk"><select id="m-sel"><option value="1">1</option><option value="2">2</option></select></div>`);
    const span = stage.querySelector('span');
    morph(stage, html`<div><b>x</b><input type="checkbox" id="m-chk" checked><select id="m-sel"><option value="1">1</option><option value="2" selected>2</option></select></div>`);
    assert(!span.isConnected && stage.querySelector('b'), 'span 应被 b 替换');
    eq(document.getElementById('m-chk').checked, true);
    eq(document.getElementById('m-sel').value, '2');
  });

  test('events：data-action 委托（点在子元素上也生效）、带 data-arg；禁用元素与无命名空间的名字不触发', () => {
    const calls = [];
    const off = defineActions('t', {
      hit: ({ el, arg }) => calls.push(`hit:${arg}:${el.tagName}`),
      pick: ({ value }) => calls.push(`pick:${value}`),
    });
    bindEvents(document);
    bindEvents(document);
    stage.replaceChildren();
    morph(stage, html`<div><button type="button" data-action="t.hit" data-arg="7"><span id="ev-inner">点我</span></button><button type="button" data-action="t.hit" data-arg="8" disabled>禁用</button><button type="button" data-action="plain">无命名空间</button><select data-change="t.pick"><option value="a">a</option><option value="b">b</option></select></div>`);
    document.getElementById('ev-inner').click();
    stage.querySelector('[disabled]').click();
    stage.querySelector('[data-action="plain"]').click();
    const sel = stage.querySelector('select');
    sel.value = 'b';
    sel.dispatchEvent(new Event('change', { bubbles: true }));
    eq(calls.join('|'), 'hit:7:BUTTON|pick:b', '只触发一次（重复 bind 不重复监听）');
    off();
  });

  test('keys：只有当前页与 global 的快捷键生效；输入框里与弹层打开时默认不触发', () => {
    bindKeys(document);
    const hits = [];
    const offA = registerKeys('page-a', { j: () => hits.push('a:j'), 'mod+k': { handler: () => hits.push('a:mod+k'), inInput: true } });
    const offB = registerKeys('page-b', { j: () => hits.push('b:j') });
    const offG = registerKeys('global', { '?': () => hits.push('g:?') });
    const press = (target, key, extra = {}) => target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...extra }));
    setScope('page-a');
    press(document.body, 'j');
    press(document.body, '?', { shiftKey: true });
    setScope('page-b');
    press(document.body, 'J', { shiftKey: false });
    morph(stage, html`<div><input id="k-in"></div>`);
    const input = document.getElementById('k-in');
    setScope('page-a');
    press(input, 'j');
    press(input, 'k', { ctrlKey: true });
    const dlg = document.createElement('dialog');
    document.body.append(dlg);
    dlg.show();
    press(document.body, 'j');
    dlg.close();
    dlg.remove();
    eq(hits.join('|'), 'a:j|g:?|b:j|a:mod+k');
    offA(); offB(); offG();
    setScope(null);
  });

  test('shell：新页面契约登记 actions / keys；进入调 mount(root, ctx)，离开执行卸载函数；切到另一页只挂载那一页', async () => {
    // 外壳要改地址与 history，iframe 必须是同源文档（about:blank 不行）：随便载一个同源静态文件当空白页
    const frame = document.createElement('iframe');
    const loaded = new Promise(resolve => frame.addEventListener('load', resolve, { once: true }));
    frame.src = '/tests/app/core_tests.js';
    document.body.append(frame);
    await loaded;
    const w = frame.contentWindow;
    w.document.body.innerHTML = '<h1 id="topbar-title"></h1><div class="content"><div class="panel" id="panel-dashboard"></div><div class="panel" id="panel-old"></div></div>';
    const log = [];
    const fresh = {
      id: 'dashboard', title: '新页', workbench: true,
      mount(root, ctx) { log.push(`mount:${root.id}:${typeof ctx.bus.emit}:${typeof ctx.store.get}`); return () => log.push('unmount'); },
      actions: { hit({ arg }) { log.push(`act:${arg}`); } },
      keys: { x: () => { log.push('key:x'); } },
    };
    const old = { id: 'old', title: '第二页', mount(root) { log.push(`mount:${root.id}`); } };
    const { router } = startShell(w, [fresh, old]);
    router.start();
    const btn = w.document.createElement('button');
    btn.dataset.action = 'dashboard.hit';
    btn.dataset.arg = '7';
    w.document.getElementById('panel-dashboard').append(btn);
    btn.click();
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', bubbles: true }));
    const workbench = w.document.querySelector('.content').classList.contains('is-workbench');
    router.go('old');
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'x', bubbles: true }));
    eq(log.join('|'), 'mount:panel-dashboard:function:function|act:7|key:x|unmount|mount:panel-old');
    assert(workbench, '新页面的 workbench 标志生效');
    eq(w.document.title, '第二页 · OMRS');
    frame.remove();
    setScope(null);
  });
}
