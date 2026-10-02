/**
 * 框选标注页入口（/annotate，独立于主页外壳）：挂骨架、接数据所有者 store、画布、快捷键、粘贴与拖放上传。
 * 只标两种框：题目、答案。保存走 /api/annotate/*，与收件箱和题库互不影响。
 */
import { html } from '../../core/html.js';
import { render, morph } from '../../core/dom.js';
import { uploadFiles as uploadImageFiles } from '../../core/uploads.js';
import { get, post, request } from '../../core/api.js';
import { bindKeys, registerKeys, setScope } from '../../core/keys.js';
import { startActivityTracking } from '../../core/activity.js';
import { installIcons } from '../../ui/icon.js';
import { toast } from '../../ui/toast.js';
import { confirm, dialog } from '../../ui/dialog.js';
import { createAnnotateStore } from './store.js';
import { createCanvas } from './canvas.js';
import { filesFromDrop, imageFiles } from './folder.js';
import { emptyView, footView, headerView, helpView, listView, numbering, rowSignature, rowView, sideTopView } from './view.js';

const KIND = { ok: 'ok', warn: 'warn', error: 'error', info: 'info' };

const uploadFiles = files => uploadImageFiles(files, 'annotate', '/api/annotate/upload-refs');

function skeleton() {
  return html`<header class="an-head" id="an-head"></header>
  <div class="an-body">
    <aside class="an-side" id="an-side" aria-label="上传与图片队列">
      <div class="an-side__top" id="an-side-top"></div>
      <ol class="an-list" id="an-list" aria-label="图片队列"></ol>
    </aside>
    <main class="an-main">
      <div class="an-scroll" id="an-scroll">
        <div class="an-canvas" id="an-canvas" data-morph="skip"></div>
        <div class="an-empty" id="an-empty"></div>
      </div>
      <footer class="an-foot" id="an-foot"></footer>
    </main>
  </div>`;
}

export function mountAnnotate(root, doc = document) {
  render(root, skeleton());
  const parts = { head: root.querySelector('#an-head'), side: root.querySelector('#an-side'), top: root.querySelector('#an-side-top'), list: root.querySelector('#an-list'),
    foot: root.querySelector('#an-foot'), empty: root.querySelector('#an-empty') };
  const store = createAnnotateStore({ api: { get, post, upload: uploadFiles }, notify: (text, kind) => toast(text, { kind: KIND[kind] || 'info' }) });
  const canvas = createCanvas(root, store);
  let format = 'yolo';
  const last = { head: '', top: '', foot: '', empty: '' };
  let listIds = null;
  const rows = new Map();   // id → 行签名

  /** 队列：可见图片的 id 序列不变时只重画签名变了的行；否则整表 morph。 */
  function paintList(state) {
    const list = store.visible();
    const numbers = numbering(state.images);
    const ids = list.map(image => image.id).join('|') + (list.length ? '' : `#${state.images.length}`);
    if (ids !== listIds) {
      listIds = ids;
      rows.clear();
      list.forEach(image => rows.set(image.id, rowSignature(image, numbers.get(image.id), state.cur)));
      morph(parts.list, listView(state, list, numbers));
      return;
    }
    for (const image of list) {
      const sig = rowSignature(image, numbers.get(image.id), state.cur);
      if (rows.get(image.id) === sig) continue;
      rows.set(image.id, sig);
      const li = parts.list.querySelector(`li[data-key="${CSS.escape(image.id)}"]`);
      if (li) morph(li, rowView(image, numbers.get(image.id), state.cur));
    }
  }
  let lastCur = null;

  function preload() {
    const list = store.visible();
    const index = list.findIndex(image => image.id === store.state.cur);
    [list[index + 1], list[index - 1]].filter(Boolean).forEach(image => { new Image().src = `/api/annotate/raw?id=${encodeURIComponent(image.id)}`; });
  }

  function paint() {
    const { state } = store;
    const current = store.current();
    // 大批量时队列有几千行：模板文本没变就不做 morph
    const put = (key, result) => { if (result.text !== last[key]) { last[key] = result.text; morph(parts[key], result); } };
    put('head', headerView(state, format));
    put('top', sideTopView(state));
    paintList(state);
    canvas.paint();
    parts.empty.hidden = !!current;
    if (!current) put('empty', emptyView(state));
    put('foot', footView(state, current, canvas.zoomPct()));
    parts.foot.hidden = !current;
    doc.title = current ? `${state.images.indexOf(current) + 1}/${state.images.length} · 框选标注 · OMRS` : '框选标注 · OMRS';
    if (state.cur !== lastCur) {
      lastCur = state.cur;
      parts.side.querySelector('.an-item.is-current')?.scrollIntoView({ block: 'nearest' });
      preload();
    }
  }

  async function removeImage() {
    const current = store.current();
    if (!current) return;
    if (await confirm(`删除「${current.file || current.id}」？`, { hint: '原图和这张图的框都会删掉，不能撤销。', okText: '删除', danger: true })) store.removeImage();
  }

  function help() { dialog({ title: '快捷键', body: helpView(), okText: '知道了', hideCancel: true, size: 'lg' }); }

  const actions = {
    role: arg => store.setRole(arg), filter: arg => store.setFilter(arg), open: arg => store.open(arg),
    finish: () => store.finish(), reopen: () => store.reopen(), clear: () => store.clearBoxes(),
    remove: removeImage, help, reload: () => store.load(),
  };
  root.addEventListener('click', event => {
    const target = event.target.closest('[data-action]');
    if (!target || !root.contains(target) || target.disabled) return;
    actions[target.dataset.action]?.(target.dataset.arg);
  });
  function take(list) {
    const { files, skipped } = imageFiles(list);
    if (skipped) toast(`跳过 ${skipped} 个非图片文件（只收 PNG / JPEG / GIF）`, { kind: 'warn' });
    if (files.length) store.upload(files);
  }
  root.addEventListener('change', event => {
    if (event.target.closest('[data-change="format"]')) { format = event.target.value || 'yolo'; paint(); return; }
    if (event.target.matches('#an-file, #an-folder')) { take(event.target.files); event.target.value = ''; }
  });

  // 整页都能拖入（文件或整个文件夹）；捕获阶段接住，拖放区自己的处理不再重复上传
  let depth = 0;
  const dropping = on => { root.classList.toggle('is-dropping', on); parts.side.querySelector('[data-filedrop]')?.classList.toggle('is-dragover', on); };
  const hasFiles = event => [...(event.dataTransfer?.types || [])].includes('Files');
  doc.addEventListener('dragenter', event => { if (!hasFiles(event)) return; event.preventDefault(); depth += 1; dropping(true); }, true);
  doc.addEventListener('dragover', event => { if (hasFiles(event)) event.preventDefault(); }, true);
  doc.addEventListener('dragleave', event => { if (!hasFiles(event)) return; depth = Math.max(0, depth - 1); if (!depth) dropping(false); }, true);
  doc.addEventListener('drop', event => {
    if (!hasFiles(event)) return;
    event.preventDefault(); event.stopPropagation();
    depth = 0; dropping(false);
    filesFromDrop(event.dataTransfer).then(take);
  }, true);

  doc.addEventListener('paste', event => {
    const files = [...(event.clipboardData?.items || [])].filter(item => item.kind === 'file')
      .map((item, i) => { const blob = item.getAsFile(); return blob && new File([blob], `paste-${Date.now()}-${i}.${(blob.type.split('/')[1] || 'png').replace('jpeg', 'jpg')}`, { type: blob.type }); })
      .filter(Boolean);
    if (!files.length) return;
    event.preventDefault();
    take(files);
  });

  const ifImage = fn => event => (store.current() ? fn(event) : false);
  registerKeys('annotate', {
    q: () => store.setRole('question'), a: () => store.setRole('answer'),
    1: () => store.setRole('question'), 2: () => store.setRole('answer'),
    tab: ifImage(() => store.cycle(1)), 'shift+tab': ifImage(() => store.cycle(-1)),
    delete: () => store.removeSelected(), backspace: () => store.removeSelected(),
    'shift+delete': ifImage(removeImage), 'shift+backspace': ifImage(removeImage),
    'mod+z': event => (event.shiftKey ? store.redo() : store.undo()), 'mod+y': () => store.redo(),
    'mod+s': () => { store.flush().then(ok => ok && toast('已保存', { kind: 'ok' })); },
    c: ifImage(() => store.copyPrevious()), f: ifImage(() => store.fullImage()),
    escape: () => canvas.cancel() || (store.state.sel != null ? store.select(null) : false),
    enter: ifImage(() => store.finish()), 'shift+enter': ifImage(() => store.finish({ allowEmpty: true })),
    arrowleft: () => store.step(-1), arrowright: () => store.step(1),
    arrowup: () => false, arrowdown: () => false,
    '+': () => store.zoom(1), '=': () => store.zoom(1), '-': () => store.zoom(-1), 0: () => store.zoom(0),
    '?': help,
  });
  setScope('annotate');
  bindKeys(doc);

  const save = () => { if (store.hasPending()) store.flush(); };
  doc.addEventListener('visibilitychange', () => { if (doc.visibilityState === 'hidden') save(); });
  window.addEventListener('beforeunload', event => { if (store.hasPending()) { save(); event.preventDefault(); event.returnValue = ''; } });

  store.subscribe(paint);
  paint();
  store.load();
  return store;
}

const app = document.getElementById('an-app');
if (app) {
  installIcons(document);
  startActivityTracking(document);
  mountAnnotate(app);
}
