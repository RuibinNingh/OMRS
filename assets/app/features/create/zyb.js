/** 作业帮工作区控制器；异步操作绑定来源，后台任务离页后仍可恢复。 */
import { get, post } from '../../core/api.js';
import { uploadImage } from '../../core/uploads.js';
import { render, morph } from '../../core/dom.js';

import { bindFileDrop } from '../../ui/filedrop.js';
import { createCombobox } from '../../ui/combobox.js';
import { confirm } from '../../ui/dialog.js';
import { openImageViewer } from '../../ui/image-viewer.js';
import { openCreateLabelPicker } from '../../domain/labels/index.js';
import { boardQuickAdd } from '../../domain/board/index.js';
import { reloadData } from '../../domain/data.js';
import { notifyHistoryChanged } from '../../domain/history.js';
import { viewQ } from '../../domain/question/index.js';
import { loadTaxonomy, mergeTaxonomy } from '../../domain/taxonomy.js';
import { itemsOf } from '../../domain/items.js';
import { suggestions } from './cards-state.js';
import { mergeClassification } from './state.js';
import { createCamera } from './zyb-camera.js';
import { createAccountMenu } from './zyb-account.js';
import { sameService } from '../../domain/zuoyebang-service.js';
import { newZybState, bindRender, extractionSnapshot, mergeExtraction, commitPayload } from './zyb-state.js';
import * as view from './zyb-view.js';

const KEY = 'omrs-zuoyebang-workspace';
const S = newZybState();
let jobContext = null;
let revision = 0, resumeActive = null;
const need = result => { if (!result.ok) throw new Error(result.error?.message || '请求失败'); return result.data; };

export function createZuoyebang(root, ctx) {
  const host = root.querySelector('#ib-stage-zuoyebang');
  let alive = true, entered = false, entryEpoch = 0, timer = null, inputRequest = 0, selectionRequest = 0;
  const drops = new WeakSet();
  render(host, view.roots());
  S.accountPanel = '';
  const accountMenu = createAccountMenu(host, S, paint);
  const camera = createCamera({ video: host.querySelector('#zyb-video'), changed: state => {
    S.camera = state;
    if (!alive) return;
    const placeholder = host.querySelector('#zyb-camera-placeholder');
    placeholder.hidden = state.on;
    placeholder.textContent = state.message;
    paint();
  } });
  function remember() {
    try { sessionStorage.setItem(KEY, JSON.stringify({ render_id: S.render?.id, search_id: S.search?.id, selected: S.selected, sourceMode: S.sourceMode,
      form: S.form, labels: S.labels, sections: S.sections, versions: S.versions, dirty: S.dirty, job: S.job, jobContext })); }
    catch (_error) { /* 存储不可用时仍保留当前会话的工作区。 */ }
  }
  function status(message, error = false) { S.message = message; S.error = error; paint(); }
  function paint() {
    if (!alive) { resumeActive?.(); return; }
    for (const [id, renderView] of [['account', view.accountView], ['camera-controls', view.cameraView], ['upload', view.uploadView],
      ['source-modes', view.sourceModesView], ['source-preview', view.sourcePreviewView], ['paste', view.pasteView],
      ['candidates', view.candidatesView], ['preview', view.previewView], ['editor', view.editorView], ['history', view.historyView], ['result', view.resultView]]) {
      morph(host.querySelector(`#zyb-${id}`), renderView(S));
    }
    const node = host.querySelector('#zyb-status');
    node.textContent = S.message;
    node.classList.toggle('is-error', S.error);
    node.setAttribute('role', S.error ? 'alert' : 'status');
    const cameraActive = S.camera.on || S.camera.pending;
    host.querySelector('#zyb-camera-source').hidden = S.sourceMode !== 'camera' || (!!S.file && !cameraActive);
    host.querySelector('#zyb-upload').hidden = S.sourceMode !== 'upload';
    host.querySelector('#zyb-source-preview').hidden = S.sourceMode === 'camera' && cameraActive;
    host.querySelector('.zyb-input').classList.toggle('has-image', !!S.file);
    const zone = host.querySelector('#zyb-upload [data-filedrop]');
    if (zone && !drops.has(zone)) { drops.add(zone); bindFileDrop(zone, files => pick(files[0]), () => status('请选择 JPG、PNG 或 WebP 图片', true)); }
  }
  async function refresh() {
    const token = revision;
    const [account, records, config] = await Promise.all([get('/api/zuoyebang/status'), get('/api/zuoyebang/history'), get('/api/zuoyebang/service')]);
    if (!alive || token !== revision) return;
    // 状态响应自带冻结配置，避免并行读取的新旧配置与账号观察混配。
    const service = account.ok ? account.data.service : config.ok ? config.data.service : S.service;
    if (!sameService(S.service, service)) S.session = null;
    S.service = service;
    if (account.ok) { S.session = account.data; S.sessionError = ''; }
    else S.sessionError = account.error.message;
    if (records.ok) S.history = records.data.records;
    paint();
  }
  async function discardEdits() {
    return !S.dirty || await confirm('切换题目会清空当前正文编辑', { hint: '科目、分类等上下文会保留。', okText: '切换题目' });
  }
  function validImage(file) {
    return ['image/png', 'image/jpeg', 'image/webp'].includes(file.type) && file.size > 0 && file.size <= 8 * 1024 * 1024;
  }
  function useImage(file, mode) {
    revision += 1;
    if (S.fileUrl) URL.revokeObjectURL(S.fileUrl);
    S.file = file; S.fileUrl = URL.createObjectURL(file); S.sourceMode = mode;
    S.search = null; S.render = null; S.result = null; S.selected = null; S.dirty = false; S.role = 'question'; S.showHtml = false;
    camera.stop();
    remember(); status('图片已选择，可以开始搜题');
  }
  async function pick(file) {
    if (!alive || !entered || S.busy || S.job || !file) return;
    const request = ++inputRequest, token = revision, entry = entryEpoch;
    if (!validImage(file)) { status('请选择不超过8MB的 JPG、PNG 或 WebP 图片', true); return; }
    if (!await discardEdits() || !alive || !entered || entry !== entryEpoch || token !== revision || request !== inputRequest || S.busy || S.job) return;
    useImage(file, 'upload');
  }
  function source(mode) {
    if (!['camera', 'upload'].includes(mode) || mode === S.sourceMode || S.busy === 'capture') return;
    inputRequest += 1; S.sourceMode = mode; camera.stop(); remember(); paint();
  }
  async function capture() {
    if (!alive || !entered || S.busy || S.job || !S.camera.on) return;
    const request = ++inputRequest, token = revision, entry = entryEpoch;
    const current = () => alive && entered && request === inputRequest && token === revision && entry === entryEpoch;
    if (!await discardEdits() || !current() || S.busy || S.job) return;
    S.busy = 'capture'; paint();
    try {
      const blob = await camera.capture();
      if (!current()) return;
      const file = new File([blob], `photo-${Date.now()}.jpg`, { type: blob.type });
      if (!validImage(file)) throw new Error('照片超过8MB或无法读取，请重拍或上传图片');
      S.busy = ''; useImage(file, 'camera');
      if (S.session?.local_session_ready) await search();
      else status('照片已保留，连接作业帮服务后可开始搜题');
    } catch (error) { if (current()) status(error.message, true); }
    finally { if (S.busy === 'capture' && request === inputRequest) { S.busy = ''; paint(); } }
  }
  function onPaste(event) {
    if (!alive || !entered || S.busy || S.job || event.target.closest?.('input, textarea, [contenteditable="true"]')) return;
    const file = [...(event.clipboardData?.items || [])].find(item => item.kind === 'file' && item.type.startsWith('image/'))?.getAsFile();
    if (!file) return;
    event.preventDefault(); event.stopImmediatePropagation(); void pick(file);
  }
  async function paste() {
    if (!alive || !entered || S.busy || S.job) return;
    if (!navigator.clipboard?.read) { status('浏览器不支持读取剪贴板，请用 Ctrl / ⌘ + V', true); return; }
    const request = ++inputRequest, token = revision, entry = entryEpoch;
    const current = () => alive && entered && request === inputRequest && token === revision && entry === entryEpoch;
    try {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        const type = item.types.find(value => value.startsWith('image/'));
        if (!type) continue;
        const blob = await item.getType(type);
        if (current()) await pick(new File([blob], `clipboard-${Date.now()}.${type.split('/')[1]}`, { type }));
        return;
      }
      if (current()) status('剪贴板里没有图片，请复制图片后重试', true);
    } catch (_error) { if (current()) status('无法读取剪贴板，请允许访问或使用 Ctrl / ⌘ + V', true); }
  }
  const renderChanged = () => jobContext?.render && (jobContext.render.search_id !== S.search?.id || jobContext.render.candidate_index !== S.selected);
  async function startJob(type, payload) {
    const token = revision;
    S.busy = type; remember(); status({ search: '作业帮正在搜题…', render: '正在生成题目与完整答案预览…', extract: 'AI 正在识别题目与完整答案…' }[type]);
    try {
      const result = need(await post('/api/zuoyebang/jobs', { type, ...payload }));
      if (token !== revision) return;
      S.job = { id: result.job.id, type };
      remember(); if (alive) await poll(); else resumeActive?.();
    } catch (error) { if (token === revision) {
      S.busy = '';
      if (type === 'render' && renderChanged()) { jobContext = null; await renderSelected(); return; }
      jobContext = null; remember(); status(error.message, true);
    } }
  }
  async function poll() {
    clearTimeout(timer);
    if (!alive || !entered || !S.job) return;
    const identity = S.job.id, token = revision;
    const response = await get(`/api/zuoyebang/job?id=${encodeURIComponent(identity)}`);
    if (!alive || !entered || token !== revision || S.job?.id !== identity) return;
    if (!response.ok) { S.busy = ''; status(`${response.error.message}；任务记录已保留，重新进入工作区可继续读取`, true); return; }
    const job = response.data.job;
    if (job.status === 'running') { timer = setTimeout(poll, 1000); return; }
    S.job = null; S.busy = '';
    // 取最后一次选择，串行生成，避免快速点击挤满后端作业或显示旧题。
    if (job.type === 'render' && renderChanged()) { jobContext = null; await renderSelected(); return; }
    if (job.status === 'failed') { jobContext = null; remember(); status(job.error, true); void refresh(); return; }
    const record = job.result;
    if (job.type === 'search') { S.search = record; S.selected = null; S.render = null; S.result = null; S.dirty = false; status(record.candidates.length ? `找到 ${record.candidates.length} 个候选，点击题目即可预览` : '未找到匹配题目，请重拍或更换图片'); }
    else if (job.type === 'render') { bindRender(S, record); status('后端渲染完成，可检查题目与完整答案长图'); }
    else if (job.type === 'extract') {
      const snapshot = jobContext?.extraction || extractionSnapshot(S);
      if (mergeExtraction(S, record, snapshot)) {
        if (record.classification && jobContext?.form) S.form = mergeClassification(S.form, record.classification, { baseline: jobContext.form });
        const failures = Object.values(record.extraction).filter(part => part.status === 'failed').length;
        status(failures ? `${failures} 项提取失败，完整图片已保留；可重试或人工核对后按图片录入` : '识别完成，请核对保存方式、正文与科目分类', failures > 0);
      }
    }
    jobContext = null; remember(); void refresh();
  }
  async function search() {
    if (S.busy || S.job || !S.file) return;
    const before = revision;
    if (!await discardEdits() || !alive || !entered || before !== revision || S.busy || S.job) return;
    const file = S.file, token = ++revision;
    S.search = null; S.selected = null; S.render = null; S.result = null; S.dirty = false; S.role = 'question'; S.showHtml = false;
    jobContext = null; remember();
    S.busy = 'search'; status('正在上传搜题图片…');
    try {
      const image = await uploadImage(file, { purpose: 'zuoyebang' });
      if (!alive || token !== revision || S.file !== file) { if (S.file === file && !S.job) S.busy = ''; paint(); return; }
      await startJob('search', { image });
    } catch (error) { if (token === revision) { S.busy = ''; status(error.message, true); } }
  }
  async function select(index) {
    index = Number(index);
    if ((S.busy && S.busy !== 'render') || (S.job && S.job.type !== 'render') || !S.search?.candidates.some(candidate => candidate.index === index)) return;
    if (index === S.selected && (S.render || S.busy || S.job)) return;
    const token = revision, request = ++selectionRequest, entry = entryEpoch;
    if (!await discardEdits() || !alive || !entered || token !== revision || request !== selectionRequest || entry !== entryEpoch) return;
    S.selected = index; S.render = null; S.result = null; S.dirty = false; S.role = 'question'; S.showHtml = false;
    if (S.busy === 'render' || S.job?.type === 'render') {
      const retryPoll = !S.busy;
      S.busy = 'render'; remember(); status('已切换候选，正在准备所选题目的预览…');
      if (retryPoll) void poll();
      return;
    }
    await renderSelected();
  }
  async function renderSelected() {
    if (S.busy || S.job || !S.search || !Number.isInteger(S.selected)) return;
    revision += 1;
    jobContext = { render: { search_id: S.search.id, candidate_index: S.selected } };
    await startJob('render', { search_id: S.search.id, candidate_index: S.selected });
  }
  async function extract() {
    if (S.busy || !S.render || S.result) return;
    jobContext = { extraction: extractionSnapshot(S), form: { ...S.form } };
    await startJob('extract', { render_id: S.render.id });
  }
  function openSettings() { accountMenu.close(); ctx.router.go('settings?section=zuoyebang'); }
  const account = openSettings, login = openSettings; // 旧 action 入口不再操作账号。
  async function commit() {
    if (S.busy || S.result) return;
    let payload;
    try { payload = commitPayload(S); } catch (error) { status(error.message, true); return; }
    S.busy = 'commit'; paint();
    try {
      const result = need(await post('/api/zuoyebang/commit', payload, { timeout: 120000 }));
      S.result = result; S.dirty = false; remember(); status(`${result.uid} 已录入 OMRS`);
      notifyHistoryChanged(); void reloadData(); ctx.bus.emit('catalog:reload');
    } catch (error) { status(`${error.message}；原题与当前编辑已保留，可重试`, true); }
    finally { S.busy = ''; paint(); }
  }
  async function openHistory(identity) {
    if (S.busy || !await discardEdits()) return;
    const token = ++revision;
    try { const result = need(await get(`/api/zuoyebang/record?id=${encodeURIComponent(identity)}`)); if (!alive || token !== revision) return;
      bindRender(S, result.record); S.search = null; S.role = 'question'; remember(); status('已打开保存的后端渲染记录');
    } catch (error) { status(error.message, true); }
  }
  function onInput(event) {
    const { target } = event, role = target.dataset.zybText, field = target.dataset.zybField;
    if (role && S.sections[role]) { S.sections[role].text = target.value; S.versions[role] += 1; }
    else if (field && Object.hasOwn(S.form, field)) S.form[field] = target.value;
    else return;
    S.dirty = true; remember();
  }

  const combobox = createCombobox(host, { options(kind) { const data = mergeTaxonomy(suggestions(itemsOf(ctx.store.get().data))); return kind === 'category' ? data.categoriesBySubject[S.form.subject] || [] : kind === 'tags' ? data.tags : data.subjects; }, onSelect: input => onInput({ target: input }) });
  host.addEventListener('input', onInput);
  document.addEventListener('paste', onPaste, true);
  paint();
  async function enter() {
    entered = true;
    const entry = ++entryEpoch, token = revision;
    const current = () => alive && entered && entry === entryEpoch && token === revision;
    if (!S.fileUrl && S.file) S.fileUrl = URL.createObjectURL(S.file);
    await refresh(); void loadTaxonomy();
    if (!current()) return;
    if (!S.render && !S.search) {
      let saved;
      try { saved = JSON.parse(sessionStorage.getItem(KEY) || 'null'); } catch (_error) { /* 不恢复损坏的浏览器草稿。 */ }
      if (saved) {
        try {
          let searchRecord = null, renderRecord = null;
          if (saved.search_id) {
            searchRecord = need(await get(`/api/zuoyebang/record?id=${encodeURIComponent(saved.search_id)}`)).record;
            if (!current()) return;
          }
          if (saved.render_id) {
            renderRecord = need(await get(`/api/zuoyebang/record?id=${encodeURIComponent(saved.render_id)}`)).record;
            if (!current()) return;
          }
          S.search = searchRecord;
          if (renderRecord) {
            bindRender(S, renderRecord);
            if (!S.result && saved.sections) { S.sections = saved.sections; S.form = saved.form; S.labels = saved.labels || []; S.dirty = !!saved.dirty; if (saved.versions) S.versions = saved.versions; }
          }
          S.selected = Number.isInteger(saved.selected) ? saved.selected : null;
          S.sourceMode = saved.sourceMode === 'upload' ? 'upload' : 'camera';
          if (saved.job?.id) { S.job = saved.job; S.busy = saved.job.type; jobContext = saved.jobContext || null; }
          if (S.job?.type === 'render' && !jobContext?.render) jobContext = { render: { search_id: S.search?.id, candidate_index: S.selected } };
        } catch (error) { if (current()) status(`保存的来源无法读取：${error.message}`, true); }
      }
    }
    paint(); if (S.job) { S.busy = S.job.type; void poll(); }
  }
  function leave() { entered = false; entryEpoch += 1; inputRequest += 1; if (S.busy === 'capture') S.busy = ''; accountMenu.close(); camera.stop(); clearTimeout(timer); combobox.close(); remember(); }
  function resume() { if (alive && entered) { paint(); void refresh(); if (S.job) void poll(); } }
  resumeActive = resume;
  return { enter, leave, search, select, capture, source, paste, render: renderSelected, extract, account, login, settings: openSettings, commit, history: openHistory,
    menu: page => accountMenu.show(page),
    camera: () => camera.toggle(),
    role: role => { if (['question', 'answer'].includes(role)) { S.role = role; paint(); } },
    zoom: zoom => { S.zoom = zoom === 'actual' ? 'actual' : 'fit'; paint(); },
    html: () => { S.showHtml = !S.showHtml; paint(); },
    expand: () => { const images = ['question', 'answer'].filter(role => S.render?.images[role]?.url); openImageViewer(images.map(role => ({ src: S.render.images[role].url, label: role === 'question' ? '完整题目渲染图' : '完整答案渲染图' })), images.indexOf(S.role)); },
    mode: arg => { const [role, mode] = arg.split(':'); if (!S.result && S.sections[role]?.mode !== 'none' && ['image', 'text'].includes(mode)) { S.sections[role].mode = mode; S.versions[role] += 1; S.dirty = true; remember(); paint(); } },
    labels: el => openCreateLabelPicker(el, S.labels, labels => { S.labels = labels; S.dirty = true; remember(); paint(); }),
    board: (el, fast) => { if (S.result) boardQuickAdd([S.result.uid], el, { fast }); },
    open: () => { if (S.result) viewQ(S.result.uid); },
    dispose() { accountMenu.dispose(); alive = false; if (resumeActive === resume) resumeActive = null; leave(); host.removeEventListener('input', onInput); document.removeEventListener('paste', onPaste, true); combobox.dispose(); if (S.fileUrl) URL.revokeObjectURL(S.fileUrl); S.fileUrl = ''; },
  };
}
