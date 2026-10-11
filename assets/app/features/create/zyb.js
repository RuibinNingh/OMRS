/** 作业帮工作区控制器；异步操作绑定来源，后台任务离页后仍可恢复。 */
import { get, post } from '../../core/api.js';
import { uploadImage } from '../../core/uploads.js';
import { render, morph } from '../../core/dom.js';
import { html } from '../../core/html.js';
import { bindFileDrop } from '../../ui/filedrop.js';
import { createCombobox } from '../../ui/combobox.js';
import { dialog, confirm, closeDialog } from '../../ui/dialog.js';
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
import { newZybState, bindRender, extractionSnapshot, mergeExtraction, commitPayload } from './zyb-state.js';
import * as view from './zyb-view.js';

const KEY = 'omrs-zuoyebang-workspace';
const S = newZybState();
let jobContext = null;
let revision = 0, resumeActive = null;
const need = result => { if (!result.ok) throw new Error(result.error?.message || '请求失败'); return result.data; };

export function createZuoyebang(root, ctx) {
  const host = root.querySelector('#ib-stage-zuoyebang');
  let alive = true, entered = false, entryEpoch = 0, timer = null, qrTimer = null, qrDialog = null, qrAbort = null;
  const drops = new WeakSet();
  render(host, view.roots());
  const camera = createCamera({ video: host.querySelector('#zyb-video'), changed: state => {
    S.camera = state;
    if (!alive) return;
    const placeholder = host.querySelector('#zyb-camera-placeholder');
    placeholder.hidden = state.on;
    placeholder.textContent = state.message;
    morph(host.querySelector('#zyb-camera-controls'), view.cameraView(S));
  } });
  function remember() {
    try { sessionStorage.setItem(KEY, JSON.stringify({ render_id: S.render?.id, search_id: S.search?.id, selected: S.selected,
      form: S.form, labels: S.labels, sections: S.sections, versions: S.versions, dirty: S.dirty, job: S.job, jobContext })); }
    catch (_error) { /* 存储不可用时仍保留当前会话的工作区。 */ }
  }
  function status(message, error = false) { S.message = message; S.error = error; paint(); }
  function paint() {
    if (!alive) { resumeActive?.(); return; }
    for (const [id, renderView] of [['account', view.accountView], ['camera-controls', view.cameraView], ['upload', view.uploadView],
      ['candidates', view.candidatesView], ['preview', view.previewView], ['editor', view.editorView], ['history', view.historyView], ['result', view.resultView]]) {
      morph(host.querySelector(`#zyb-${id}`), renderView(S));
    }
    const node = host.querySelector('#zyb-status');
    node.textContent = S.message;
    node.classList.toggle('is-error', S.error);
    node.setAttribute('role', S.error ? 'alert' : 'status');
    const zone = host.querySelector('#zyb-upload [data-filedrop]');
    if (!drops.has(zone)) { drops.add(zone); bindFileDrop(zone, files => pick(files[0]), () => status('请选择 JPG、PNG 或 WebP 图片', true)); }
  }
  async function refresh() {
    const token = revision;
    const [account, records] = await Promise.all([get('/api/zuoyebang/status'), get('/api/zuoyebang/history')]);
    if (!alive || token !== revision) return;
    if (account.ok) { S.session = account.data; S.sessionError = ''; }
    else S.sessionError = account.error.message;
    if (records.ok) S.history = records.data.records;
    paint();
  }
  async function discardEdits() {
    return !S.dirty || await confirm('切换题目会清空当前正文编辑', { hint: '科目、分类等上下文会保留。', okText: '切换题目' });
  }
  async function pick(file) {
    if (S.busy || !file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 8 * 1024 * 1024) { status('请选择不超过8MB的 JPG、PNG 或 WebP 图片', true); return; }
    if (!await discardEdits()) return;
    revision += 1;
    if (S.fileUrl) URL.revokeObjectURL(S.fileUrl);
    S.file = file; S.fileUrl = URL.createObjectURL(file); S.search = null; S.render = null; S.result = null; S.selected = 0; S.dirty = false;
    remember(); status('图片已选择，可以开始搜题');
  }
  async function startJob(type, payload) {
    const token = revision;
    S.busy = type; status({ search: '作业帮正在搜题…', render: '后端正在加载附图、公式和字体并渲染完整长图…', extract: 'AI 正在识别题目与完整答案…' }[type]);
    try {
      const result = need(await post('/api/zuoyebang/jobs', { type, ...payload }));
      if (token !== revision) return;
      S.job = { id: result.job.id, type };
      remember(); if (alive) await poll(); else resumeActive?.();
    } catch (error) { if (token === revision) { S.busy = ''; status(error.message, true); } }
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
    if (job.status === 'failed') { remember(); status(job.error, true); void refresh(); return; }
    const record = job.result;
    if (job.type === 'search') { S.search = record; S.selected = 0; S.render = null; S.result = null; S.dirty = false; status(`找到 ${record.candidates.length} 个候选，请选择并核对后渲染`); }
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
    if (S.busy || !S.file || !await discardEdits()) return;
    const file = S.file, token = ++revision;
    S.busy = 'search'; status('正在上传搜题图片…');
    try {
      const image = await uploadImage(file, { purpose: 'zuoyebang' });
      if (!alive || token !== revision || S.file !== file) { if (S.file === file && !S.job) S.busy = ''; paint(); return; }
      await startJob('search', { image });
    } catch (error) { if (token === revision) { S.busy = ''; status(error.message, true); } }
  }
  async function select(index) {
    if (S.busy || !S.search?.candidates[Number(index)] || Number(index) === S.selected || !await discardEdits()) return;
    revision += 1; S.selected = Number(index); S.render = null; S.result = null; S.dirty = false; remember(); status('候选已切换，请重新渲染这道题');
  }
  async function renderSelected() {
    if (S.busy || !S.search || !await discardEdits()) return;
    revision += 1;
    await startJob('render', { search_id: S.search.id, candidate_index: S.selected });
  }
  async function extract() {
    if (S.busy || !S.render || S.result) return;
    jobContext = { extraction: extractionSnapshot(S), form: { ...S.form } };
    await startJob('extract', { render_id: S.render.id });
  }
  async function account(operation) {
    if (S.busy) return;
    S.busy = 'account'; status(operation === 'verify' ? '正在检查作业帮账号…' : '正在刷新作业帮账号…');
    try { need(await post('/api/zuoyebang/account', { operation }, { timeout: 120000 })); status('作业帮账号已在线核对'); }
    catch (error) { status(error.message, true); }
    finally { S.busy = ''; await refresh(); paint(); }
  }
  async function importProfile(file) {
    if (S.busy || !file) return;
    if (file.size > 256 * 1024) { status('设备会话文件不能超过256KB', true); return; }
    S.busy = 'account'; paint();
    try { const profile = JSON.parse(await file.text()); need(await post('/api/zuoyebang/profile', { profile })); status('设备会话已导入，请检查账号或扫码登录'); }
    catch (error) { status(error instanceof SyntaxError ? '设备会话不是有效 JSON 文件' : error.message, true); }
    finally { S.busy = ''; await refresh(); paint(); }
  }
  function stopQr() {
    clearTimeout(qrTimer); qrAbort?.abort(); qrAbort = null;
    const flow = S.qr; S.qr = null;
    if (flow && flow.state === 'pending') void post('/api/zuoyebang/account', { operation: 'qr_cancel', flow_id: flow.flow_id }, { timeout: 45000 });
  }
  async function pollQr() {
    if (!alive || !entered || !S.qr || !qrDialog?.open) return;
    const flow = S.qr, abort = new AbortController(); qrAbort = abort;
    const response = await post('/api/zuoyebang/account', { operation: 'qr_poll', flow_id: flow.flow_id }, { timeout: 90000, signal: abort.signal });
    if (!alive || S.qr !== flow || !qrDialog?.open) return;
    const code = response.data?.code || response.error?.code;
    const terminalError = !response.ok && ['signing_session', 'session_changed', 'qr_missing', 'profile_missing', 'protocol'].includes(code);
    const result = response.ok ? response.data.account : { message: response.error.message, state: 'pending' };
    qrDialog.querySelector('[data-zyb-qr-status]').textContent = result.message || '等待作业帮 App 确认登录…';
    flow.state = result.state;
    if (result.state === 'authenticated') { status('登录成功，可以上传图片搜题'); void refresh(); return; }
    if (terminalError) { void refresh(); return; }
    if (['expired', 'cancelled', 'session_changed', 'replaced', 'missing'].includes(result.state)) return;
    qrTimer = setTimeout(pollQr, (Number(result.retry_after) || 2) * 1000);
  }
  async function login() {
    if (S.busy) return;
    const entry = entryEpoch;
    S.busy = 'account'; status('正在创建登录二维码…');
    try {
      const result = need(await post('/api/zuoyebang/account', { operation: 'qr_start' }, { timeout: 45000 }));
      if (!alive || !entered || entry !== entryEpoch) {
        void post('/api/zuoyebang/account', { operation: 'qr_cancel', flow_id: result.account.flow_id }, { timeout: 45000 });
        return;
      }
      S.qr = result.account;
      void dialog({ title: '登录作业帮', hint: '请用已登录的作业帮 App 扫码，并在官方页面确认。', okText: '关闭', hideCancel: true,
        body: html`<div class="zyb-qr"><img src="${S.qr.qr_image}" alt="作业帮登录二维码"><p data-zyb-qr-status role="status">等待扫码确认…</p><small>二维码约5分钟有效，关闭会取消当前登录流程。</small></div>`,
        onOpen(el) { qrDialog = el; qrTimer = setTimeout(pollQr, 2000); },
      }).then(() => { stopQr(); qrDialog = null; });
    } catch (error) { status(error.message, true); }
    finally { S.busy = ''; paint(); }
  }
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
  function onChange(event) { if (event.target.id === 'zyb-profile') { void importProfile(event.target.files?.[0]); event.target.value = ''; } }
  const combobox = createCombobox(host, { options(kind) { const data = mergeTaxonomy(suggestions(itemsOf(ctx.store.get().data))); return kind === 'category' ? data.categoriesBySubject[S.form.subject] || [] : kind === 'tags' ? data.tags : data.subjects; }, onSelect: input => onInput({ target: input }) });
  host.addEventListener('input', onInput); host.addEventListener('change', onChange);
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
          S.selected = Number(saved.selected) || 0;
          if (saved.job?.id) { S.job = saved.job; S.busy = saved.job.type; jobContext = saved.jobContext || null; }
        } catch (error) { if (current()) status(`保存的来源无法读取：${error.message}`, true); }
      }
    }
    paint(); if (S.job) { S.busy = S.job.type; void poll(); }
  }
  function leave() { entered = false; entryEpoch += 1; camera.stop(); clearTimeout(timer); stopQr(); if (qrDialog) closeDialog(qrDialog); combobox.close(); remember(); }
  function resume() { if (alive && entered) { paint(); void refresh(); if (S.job) void poll(); } }
  resumeActive = resume;
  return { enter, leave, search, select, render: renderSelected, extract, account, login, commit, history: openHistory,
    camera: () => camera.toggle(),
    role: role => { if (['question', 'answer'].includes(role)) { S.role = role; paint(); } },
    zoom: zoom => { S.zoom = zoom === 'actual' ? 'actual' : 'fit'; paint(); },
    html: () => { S.showHtml = !S.showHtml; paint(); },
    expand: () => { const images = ['question', 'answer'].filter(role => S.render?.images[role]?.url); openImageViewer(images.map(role => ({ src: S.render.images[role].url, label: role === 'question' ? '完整题目渲染图' : '完整答案渲染图' })), images.indexOf(S.role)); },
    mode: arg => { const [role, mode] = arg.split(':'); if (!S.result && S.sections[role]?.mode !== 'none' && ['image', 'text'].includes(mode)) { S.sections[role].mode = mode; S.versions[role] += 1; S.dirty = true; remember(); paint(); } },
    labels: el => openCreateLabelPicker(el, S.labels, labels => { S.labels = labels; S.dirty = true; remember(); paint(); }),
    board: (el, fast) => { if (S.result) boardQuickAdd([S.result.uid], el, { fast }); },
    open: () => { if (S.result) viewQ(S.result.uid); },
    dispose() { alive = false; if (resumeActive === resume) resumeActive = null; leave(); host.removeEventListener('input', onInput); host.removeEventListener('change', onChange); combobox.dispose(); if (S.fileUrl) URL.revokeObjectURL(S.fileUrl); S.fileUrl = ''; },
  };
}
