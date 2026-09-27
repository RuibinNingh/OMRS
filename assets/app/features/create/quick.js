/** 快速录入：图片暂存、AI 识别、题目创建和提交后的上下文保留。 */
import { html } from '../../core/html.js';
import { render, morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { bindFileDrop } from '../../ui/filedrop.js';
import { button } from '../../ui/button.js';
import { toast } from '../../ui/toast.js';
import { itemsOf } from '../../domain/items.js';
import { labelChips, openCreateLabelPicker } from '../../domain/labels/index.js';
import { boardQuickAdd } from '../../domain/board.js';
import { reloadData } from '../../domain/data.js';
import { notifyHistoryChanged } from '../../domain/history.js';
import { newQuickState, createPayload, mergeClassification, afterCreate } from './state.js';
import { quickView, imageThumbs, resultView } from './quick-view.js';

let state = newQuickState();

function options(items) {
  const unique = values => [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  return {
    subjects: unique(items.map(item => item.subject)),
    categories: unique(items.map(item => item.category)),
    tags: unique(items.flatMap(item => [item.category, ...(item.knowledge_tags || [])])),
  };
}

function readDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('图片读取失败'));
    reader.readAsDataURL(file);
  });
}

export function createQuick(root, ctx) {
  const host = root.querySelector('#ib-stage-quick');
  let alive = true;
  let busy = false;
  const aiBusy = { q: false, a: false };
  const dataOptions = () => options(itemsOf(ctx.store.get().data));
  const field = name => host.querySelector(`[data-cr-field="${name}"]`);
  const imageList = kind => state.images[kind];

  function status(kind, message, error = false) {
    if (!alive) return;
    const node = host.querySelector(kind === 'q' ? '#cr-classify-status' : '#cr-extract-status');
    if (!node) return;
    node.textContent = message;
    node.classList.toggle('is-error', error);
    node.setAttribute('role', error ? 'alert' : 'status');
  }

  function paintImages(kind) {
    if (!alive) return;
    morph(host.querySelector(`#cr-${kind}-images`), imageThumbs(imageList(kind), kind));
    const enabled = imageList(kind).length > 0 && !aiBusy[kind];
    const buttons = kind === 'q' ? ['#cr-classify-btn', '#cr-question-text-btn'] : ['#cr-extract-btn'];
    buttons.forEach(selector => { const control = host.querySelector(selector); if (control) control.disabled = !enabled; });
  }

  function paintLabels() {
    if (!alive) return;
    morph(host.querySelector('#crw-labels'), html`${labelChips(state.labels)}${button({ label: '添加标记', icon: 'plus', action: 'create.openLabels' })}`);
  }

  function paintResult() {
    if (alive) morph(host.querySelector('#cr-result'), resultView(state.result));
  }

  function pasteTarget(kind) {
    state.target = kind === 'a' ? 'a' : 'q';
    host.querySelectorAll('[data-cr-paste]').forEach(node => node.classList.toggle('is-target', node.dataset.crPaste === state.target));
  }

  async function addFiles(files, kind) {
    const images = [...(files || [])].filter(file => file?.type?.startsWith('image/'));
    if (!images.length) { status(kind, '请选择图片文件', true); return; }
    try {
      const urls = await Promise.all(images.map(readDataUrl));
      if (!alive) return;
      urls.forEach(dataUrl => imageList(kind).push({ id: ++state.nextImageId, dataUrl }));
      paintImages(kind);
      status(kind, `已添加 ${images.length} 张图片`);
    } catch (error) { status(kind, error.message || '图片读取失败', true); }
  }

  function bindImageZones() {
    for (const kind of ['q', 'a']) {
      const wrapper = host.querySelector(`[data-cr-paste="${kind}"]`);
      const zone = wrapper.querySelector('[data-filedrop]');
      wrapper.addEventListener('pointerdown', () => pasteTarget(kind));
      wrapper.addEventListener('focusin', () => pasteTarget(kind));
      bindFileDrop(zone, files => addFiles(files, kind), () => status(kind, '请选择图片文件', true));
    }
  }

  function paint() {
    render(host, quickView(state, dataOptions()));
    bindImageZones();
  }

  function syncForm() {
    Object.entries(state.form).forEach(([name, value]) => { const input = field(name); if (input) input.value = value; });
    const output = host.querySelector('#cr-diff-val');
    if (output) output.value = state.form.difficulty;
  }

  function onInput(event) {
    const name = event.target.dataset.crField;
    if (!name) return;
    state.form[name] = event.target.value;
    if (name === 'difficulty') host.querySelector('#cr-diff-val').value = event.target.value;
  }

  function onPaste(event) {
    if (!root.classList.contains('active') || !host.classList.contains('on')) return;
    const files = [...(event.clipboardData?.items || [])]
      .filter(item => item.kind === 'file' && item.type.startsWith('image/'))
      .map(item => item.getAsFile()).filter(Boolean);
    if (!files.length) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    addFiles(files, host.querySelector('[data-cr-paste]:focus-within')?.dataset.crPaste || state.target);
  }

  async function readClipboard(kind) {
    pasteTarget(kind);
    if (!navigator.clipboard?.read) { status(kind, '当前浏览器不支持直接读取剪贴板，请用 Ctrl / ⌘ + V', true); return; }
    try {
      const list = await navigator.clipboard.read();
      const images = [];
      for (const item of list) {
        const type = (item.types || []).find(value => value.startsWith('image/'));
        if (type) images.push(new File([await item.getType(type)], `clipboard-${Date.now()}.png`, { type }));
      }
      if (!alive) return;
      if (images.length) await addFiles(images, kind);
      else status(kind, '剪贴板里没有图片', true);
    } catch (error) { status(kind, `读取剪贴板失败：${error.message || error}`, true); }
  }

  async function recognize(mode, kind) {
    if (aiBusy[kind] || !imageList(kind).length) return;
    aiBusy[kind] = true;
    paintImages(kind);
    status(kind, '识别中…');
    const question = state.images.q[0]?.dataUrl;
    const answer = state.images.a[0]?.dataUrl;
    const payload = mode === 'classify'
      ? { question_image: question, answer_image: answer || undefined, mode, subject: state.form.subject.trim(), category: state.form.category.trim() }
      : { image: kind === 'q' ? question : answer, mode };
    const result = await post('/api/ai-recognize', payload);
    aiBusy[kind] = false;
    if (!alive) return;
    paintImages(kind);
    if (!result.ok) { status(kind, `识别失败：${result.error?.message || '未知错误'}`, true); return; }
    const data = result.data || {};
    if (mode === 'classify') {
      state.form = mergeClassification(state.form, data);
      state.labels = [...new Set([...state.labels, ...(data.labels || []).map(name => String(name).trim()).filter(Boolean)])];
      syncForm(); paintLabels();
      status(kind, '已填充，请核对' + (data.labels?.length ? ` · 已生成${data.labels.length}个标记` : ''));
    } else {
      if (data.mode && data.mode !== mode) { status(kind, `后端返回了 ${data.mode} 模式，请重试`, true); return; }
      const value = String(mode === 'answer' ? data.answer || '' : data.question_text || '').trim();
      if (!value) { status(kind, '模型没有返回文本，请换一张更清晰的图片或稍后重试', true); return; }
      const name = mode === 'answer' ? 'answer' : 'question';
      state.form[name] = value;
      field(name).value = value;
      status(kind, mode === 'answer' ? '已提取答案文本，请核对' : '已提取题目文本，请核对');
    }
  }

  async function submit() {
    if (busy) return;
    const payload = createPayload(state);
    if (!payload.ok) { state.result = { error: payload.error }; paintResult(); return; }
    busy = true;
    const control = host.querySelector('[data-action="create.submit"]');
    control.disabled = true;
    control.setAttribute('aria-busy', 'true');
    const result = await post('/api/create', payload.data);
    busy = false;
    if (!alive) return;
    if (!result.ok) { state.result = { error: `创建失败：${result.error?.message || '未知错误'}` }; paintResult(); }
    else {
      const data = result.data || {};
      state = afterCreate(state);
      state.result = { uid: data.uid, filePath: data.file_path, imageCount: data.images?.length || 0 };
      paint();
      notifyHistoryChanged('create');
      ctx.bus.emit('catalog:refresh');
      const refreshed = await reloadData();
      if (!refreshed.ok) toast('题目已创建，统计刷新失败，请刷新页面', { kind: 'warn' });
    }
    const next = host.querySelector('[data-action="create.submit"]');
    if (next) { next.disabled = false; next.removeAttribute('aria-busy'); }
  }

  const stopData = ctx.store.subscribe(() => {
    if (!alive) return;
    const next = dataOptions();
    [['crw-subj-list', next.subjects], ['crw-cat-list', next.categories], ['crw-ktag-list', next.tags]].forEach(([id, values]) => {
      const list = host.querySelector(`#${id}`);
      if (list) morph(list, html`${values.map(value => html`<option value="${value}"></option>`)}`);
    });
  }, value => value.data);
  const stopLabels = ctx.bus.on('labels', paintLabels);
  host.addEventListener('input', onInput);
  document.addEventListener('paste', onPaste, true);
  paint();

  return {
    readClipboard,
    removeImage(arg) { const [kind, id] = String(arg).split(':'); if (!state.images[kind]) return; state.images[kind] = imageList(kind).filter(image => image.id !== Number(id)); paintImages(kind); },
    classify: () => recognize('classify', 'q'),
    questionText: () => recognize('question_text', 'q'),
    answerText: () => recognize('answer', 'a'),
    openLabels(el) { openCreateLabelPicker(el, { get: () => state.labels, onSave: values => { state.labels = [...new Set(values)]; paintLabels(); } }); },
    reset() { state = newQuickState(); paint(); },
    submit,
    boardAdd(el, direct) { if (state.result?.uid) boardQuickAdd(state.result.uid, { anchor: el, direct }); },
    dispose() { alive = false; stopData(); stopLabels(); host.removeEventListener('input', onInput); document.removeEventListener('paste', onPaste, true); },
  };
}
