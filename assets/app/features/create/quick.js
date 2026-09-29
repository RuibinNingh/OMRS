/** 快速录入：图片暂存、AI 识别、题目创建和提交后的上下文保留。 */
import { html } from '../../core/html.js';
import { render, morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { bindFileDrop } from '../../ui/filedrop.js';
import { createCombobox } from '../../ui/combobox.js';
import { button } from '../../ui/button.js';
import { toast } from '../../ui/toast.js';
import { itemsOf } from '../../domain/items.js';
import { labelChips, openCreateLabelPicker } from '../../domain/labels/index.js';
import { boardQuickAdd } from '../../domain/board/index.js';
import { reloadData } from '../../domain/data.js';
import { loadTaxonomy, mergeTaxonomy } from '../../domain/taxonomy.js';
import { notifyHistoryChanged } from '../../domain/history.js';
import { newQuickState, createPayload, mergeClassification, afterCreate } from './state.js';
import { quickView, imageThumbs, resultView, causeCandidate } from './quick-view.js';
import { suggestions } from './cards-state.js';

let state = newQuickState();

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
  const dataOptions = () => mergeTaxonomy(suggestions(itemsOf(ctx.store.get().data)));
  void loadTaxonomy();
  const field = name => host.querySelector(`[data-cr-field="${name}"]`);
  const imageList = kind => state.images[kind];
  const sourceKey = current => ['q', 'a'].map(kind => current.images[kind].map(image => image.id).join(',')).join('|');
  const editKey = current => `${sourceKey(current)}|${JSON.stringify(current.form)}|${JSON.stringify(current.labels)}`;

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
    const thumbs = host.querySelector(`#cr-${kind}-images`);
    morph(thumbs, imageThumbs(imageList(kind), kind));
    thumbs.hidden = imageList(kind).length === 0;
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

  function paintCandidate() {
    const node = host.querySelector('#cr-cause-candidate');
    if (alive && node) morph(node, causeCandidate(state.candidates.cause));
  }

  function pasteTarget(kind) {
    state.target = kind === 'a' ? 'a' : 'q';
    host.querySelectorAll('[data-cr-paste]').forEach(node => node.classList.toggle('is-target', node.dataset.crPaste === state.target));
  }

  async function addFiles(files, kind) {
    const images = [...(files || [])].filter(file => file?.type?.startsWith('image/'));
    if (!images.length) { status(kind, '请选择图片文件', true); return; }
    const targetState = state;
    try {
      const urls = await Promise.all(images.map(readDataUrl));
      if (!alive || state !== targetState) return;
      urls.forEach(dataUrl => imageList(kind).push({ id: ++state.nextImageId, dataUrl }));
      state.candidates = {};
      if (kind === 'a') { state.answerOpen = true; host.querySelector('#cr-a-paste').open = true; }
      paintImages(kind);
      paintCandidate();
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
      if (kind === 'a') wrapper.addEventListener('toggle', () => { state.answerOpen = wrapper.open; });
    }
  }

  function paint() {
    combobox.close();
    render(host, quickView(state));
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
    state.manual[name] = true;
    delete state.candidates[name];
    delete state.fieldSource[name];
    if (name === 'cause') paintCandidate();
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
    const requestState = state;
    const requestSource = sourceKey(state);
    const baseline = { ...state.form };
    const manual = { ...state.manual };
    const payload = mode === 'classify'
      ? { scope: 'quick', question_image: question, answer_image: answer || undefined, mode, subject: baseline.subject.trim(), category: baseline.category.trim() }
      : { scope: 'quick', image: kind === 'q' ? question : answer, mode };
    const result = await post('/api/ai-recognize', payload);
    if (!alive) return;
    if (state !== requestState || sourceKey(state) !== requestSource) {
      aiBusy[kind] = false;
      paintImages(kind);
      status(kind, '图片或题目已变化，已舍弃旧识别结果');
      return;
    }
    aiBusy[kind] = false;
    paintImages(kind);
    if (!result.ok) { status(kind, `识别失败：${result.error?.message || '未知错误'}`, true); return; }
    const data = result.data || {};
    if (mode === 'classify') {
      if (data.mode && data.mode !== mode) { status(kind, `后端返回了 ${data.mode} 模式，请重试`, true); return; }
      const before = state.form;
      state.form = mergeClassification(before, data, { manual: { ...manual, ...state.manual }, baseline });
      if (before.subject !== baseline.subject && before.subject !== data.subject) state.form.category = before.category;
      for (const name of ['subject', 'category', 'difficulty', 'related']) {
        if (state.form[name] !== before[name]) state.fieldSource[name] = { kind: 'ai', source: requestSource };
      }
      const candidate = data.cause_candidate;
      state.candidates.cause = candidate?.value && candidate?.evidence_text
        ? { value: String(candidate.value), evidence: String(candidate.evidence_text), source: requestSource } : null;
      syncForm(); paintCandidate();
      status(kind, '已补全可用字段，请核对；人工标记未变化');
    } else {
      if (data.mode && data.mode !== mode) { status(kind, `后端返回了 ${data.mode} 模式，请重试`, true); return; }
      const value = String(mode === 'answer' ? data.answer || '' : data.question_text || '').trim();
      if (!value) { status(kind, '模型没有返回文本，请换一张更清晰的图片或稍后重试', true); return; }
      const name = mode === 'answer' ? 'answer' : 'question';
      if (state.manual[name] || state.form[name] !== baseline[name]) {
        status(kind, '识别完成；该字段已由你修改，保留人工内容');
        return;
      }
      state.form[name] = value;
      state.fieldSource[name] = { kind: 'ai', source: requestSource };
      field(name).value = value;
      status(kind, mode === 'answer' ? '已提取答案文本，请核对' : '已提取题目文本，请核对');
    }
  }

  async function submit() {
    if (busy) return;
    const payload = createPayload(state);
    if (!payload.ok) { state.result = { error: payload.error }; paintResult(); return; }
    const submittedState = state;
    const submittedKey = editKey(state);
    busy = true;
    const control = host.querySelector('[data-action="create.submit"]');
    control.disabled = true;
    control.setAttribute('aria-busy', 'true');
    const result = await post('/api/create', payload.data);
    busy = false;
    if (!alive) return;
    if (!result.ok) {
      if (state === submittedState) { state.result = { error: `创建失败：${result.error?.message || '未知错误'}` }; paintResult(); }
      else toast(`先前提交失败：${result.error?.message || '未知错误'}`, { kind: 'warn' });
    }
    else {
      const data = result.data || {};
      if (state === submittedState && editKey(state) === submittedKey) {
        state = afterCreate(state);
        state.result = { uid: data.uid, filePath: data.file_path, imageCount: data.images?.length || 0 };
        paint();
      } else toast(`先前题目 ${data.uid} 已创建；当前草稿已保留`, { kind: 'ok' });
      notifyHistoryChanged('create');
      ctx.bus.emit('catalog:refresh');
      const refreshed = await reloadData();
      if (!refreshed.ok) toast('题目已创建，统计刷新失败，请刷新页面', { kind: 'warn' });
    }
    const next = host.querySelector('[data-action="create.submit"]');
    if (next) { next.disabled = false; next.removeAttribute('aria-busy'); }
  }

  const combobox = createCombobox(host, { options(name) {
    const data = dataOptions();
    if (name === 'subject') return data.subjects;
    if (name === 'category') return data.categoriesBySubject[state.form.subject.trim()] || [];
    return data.tags;
  }, onSelect(input) {
    if (input.dataset.combobox !== 'subject') return;
    const allowed = dataOptions().categoriesBySubject[state.form.subject.trim()] || [];
    if (state.form.category && !allowed.includes(state.form.category)) {
      state.form.category = '';
      field('category').value = '';
      state.manual.category = false;
    }
  } });
  const stopLabels = ctx.bus.on('labels', paintLabels);
  host.addEventListener('input', onInput);
  document.addEventListener('paste', onPaste, true);
  paint();

  return {
    readClipboard,
    removeImage(arg) { const [kind, id] = String(arg).split(':'); if (!state.images[kind]) return; state.images[kind] = imageList(kind).filter(image => image.id !== Number(id)); state.candidates = {}; paintImages(kind); paintCandidate(); },
    classify: () => recognize('classify', 'q'),
    questionText: () => recognize('question_text', 'q'),
    answerText: () => recognize('answer', 'a'),
    openLabels(el) { openCreateLabelPicker(el, { get: () => state.labels, onSave: values => { state.labels = [...new Set(values)]; paintLabels(); } }); },
    acceptCause() {
      const candidate = state.candidates.cause;
      if (!candidate || candidate.source !== sourceKey(state)) return;
      state.form.cause = candidate.value;
      state.manual.cause = true;
      delete state.candidates.cause;
      syncForm(); paintCandidate();
    },
    reset() { state = newQuickState(); paint(); },
    submit,
    boardAdd(el, direct) { if (state.result?.uid) boardQuickAdd(state.result.uid, { anchor: el, direct }); },
    dispose() { alive = false; combobox.dispose(); stopLabels(); host.removeEventListener('input', onInput); document.removeEventListener('paste', onPaste, true); },
  };
}
