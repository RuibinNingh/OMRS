/** 报告页：列表生命周期、上传、材料下载与隔离预览。 */
import { morph } from '../../core/dom.js';
import { get, post } from '../../core/api.js';
import { downloadResponse } from '../../core/download.js';
import { bindFileDrop } from '../../ui/filedrop.js';
import { confirm } from '../../ui/dialog.js';
import { buildReportAiPrompt, fileError } from './state.js';
import { view } from './view.js';

let controller = null;

function readFileText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ''));
    reader.onerror = () => reject(new Error('文件读取失败'));
    reader.readAsText(file, 'utf-8');
  });
}

async function copyText(text) {
  try {
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; }
    const probe = document.createElement('textarea');
    probe.value = text;
    document.body.append(probe);
    probe.select();
    try { return document.execCommand('copy'); } finally { probe.remove(); }
  } catch { return false; }
}

function createController(root) {
  const host = root.querySelector('#rp-app') || root;
  const s = { reports: [], loaded: false, loading: false, listError: '', selectedId: '', includeImages: false,
    name: '', file: null, fileError: '', uploading: false, downloading: false,
    deleting: false, copying: false, confirming: false, status: '', statusTone: '' };
  const bound = new WeakSet();
  let alive = true;
  let loadId = 0;
  let slow = 0;
  const busy = () => s.uploading || s.downloading || s.deleting || s.copying || s.confirming;
  const paint = () => {
    if (!alive) return;
    morph(host, view(s));
    const zone = host.querySelector('.rpw-upload [data-filedrop]');
    if (zone && !bound.has(zone)) {
      bound.add(zone);
      bindFileDrop(zone, files => {
        if (!alive || busy()) return;
        s.file = files[0] || null;
        s.fileError = fileError(s.file);
        paint();
      }, () => {
        if (!alive) return;
        s.file = null;
        s.fileError = '只支持 .html 或 .htm 文件';
        paint();
      });
    }
  };
  const message = (value, tone = '') => { s.status = value; s.statusTone = tone; paint(); };

  async function load() {
    if (s.loading) return;
    const mine = ++loadId;
    clearTimeout(slow);
    if (s.loaded) s.loading = true;
    else slow = setTimeout(() => { if (alive && mine === loadId) { s.loading = true; paint(); } }, 300);
    s.listError = '';
    paint();
    const result = await get('/api/reports');
    clearTimeout(slow);
    if (!alive || mine !== loadId) return result;
    s.loading = false;
    s.loaded = true;
    if (result.ok) {
      s.reports = result.data?.reports || [];
      if (s.selectedId && !s.reports.some(row => row.id === s.selectedId)) s.selectedId = '';
    } else s.listError = result.error?.message || '未知错误';
    paint();
    return result;
  }

  async function create() {
    if (busy()) return;
    const name = s.name.trim();
    if (!name) { message('请填写报告名称', 'danger'); return; }
    s.fileError = fileError(s.file);
    if (s.fileError) { message(s.fileError, 'danger'); return; }
    s.uploading = true;
    message('正在上传报告…');
    try {
      const html = await readFileText(s.file);
      if (!html.trim()) throw new Error('HTML 文件为空');
      const result = await post('/api/report/create', { name, html });
      if (!result.ok) throw new Error(result.error?.message || '上传失败');
      s.name = '';
      s.file = null;
      s.fileError = '';
      message(`已创建：${result.data?.name || name}`, 'success');
      await load();
    } catch (error) {
      if (error.message === '文件读取失败') s.fileError = error.message;
      message(error.message || '文件读取失败', 'danger');
    }
    finally { s.uploading = false; paint(); }
  }

  async function remove(id) {
    if (busy() || !s.reports.some(row => row.id === id)) return;
    s.confirming = true;
    const accepted = await confirm('删除该报告？', {
      hint: '托管的 HTML 文件会被删除，AI 分析材料不受影响。', okText: '删除', danger: true,
    });
    s.confirming = false;
    if (!alive || !accepted) return;
    s.deleting = true;
    paint();
    try {
      const result = await post('/api/report/delete', { id });
      if (!alive) return;
      if (!result.ok) { message(`删除失败：${result.error?.message || '未知错误'}`, 'danger'); return; }
      message('报告已删除', 'success');
      await load();
    } finally { s.deleting = false; if (alive) paint(); }
  }

  async function download() {
    if (busy()) return;
    s.downloading = true;
    message('正在准备 AI 分析材料…');
    try {
      const images = s.includeImages;
      const response = await fetch(`/api/export-review?include_images=${images ? '1' : '0'}`, { credentials: 'same-origin' });
      if (!response.ok) {
        let reason = `HTTP ${response.status}`;
        try { reason = (await response.json()).msg || reason; } catch { /* 非 JSON 错误体 */ }
        throw new Error(reason);
      }
      const name = await downloadResponse(response, images ? 'OMRS-AI数据-含图片.zip' : 'OMRS-AI数据.md');
      message(`已下载 ${name}`, 'success');
    } catch (error) { message(`导出失败：${error.message || '未知错误'}`, 'danger'); }
    finally { s.downloading = false; paint(); }
  }

  async function copyPrompt() {
    if (busy()) return;
    s.copying = true;
    paint();
    try {
      const ok = await copyText(buildReportAiPrompt(s.includeImages));
      if (alive) message(ok ? 'AI 报告提示词已复制' : '复制失败，请检查剪贴板权限', ok ? 'success' : 'danger');
    } finally { s.copying = false; if (alive) paint(); }
  }

  return {
    paint, load, create, remove, download, copyPrompt,
    name(value) { s.name = String(value || ''); },
    images(checked) { s.includeImages = !!checked; paint(); },
    open(id) { if (s.reports.some(row => row.id === id)) { s.selectedId = id; paint(); host.querySelector('.rpw-preview')?.scrollIntoView?.({ block: 'nearest' }); } },
    close() { s.selectedId = ''; paint(); },
    newTab(id) { if (s.reports.some(row => row.id === id)) window.open(`/api/report/view?id=${encodeURIComponent(id)}`, '_blank', 'noopener'); },
    dispose() { alive = false; loadId += 1; clearTimeout(slow); },
  };
}

export const page = {
  id: 'reports', title: '报告',
  mount(root) {
    controller = createController(root);
    controller.paint();
    controller.load();
    return () => { controller?.dispose(); controller = null; };
  },
  actions: {
    refresh: () => controller?.load(),
    name: ({ value }) => controller?.name(value),
    images: ({ el }) => controller?.images(el.checked),
    prompt: () => controller?.copyPrompt(),
    download: () => controller?.download(),
    create: () => controller?.create(),
    delete: ({ arg }) => controller?.remove(arg),
    open: ({ arg }) => controller?.open(arg),
    close: () => controller?.close(),
    newTab: ({ arg }) => controller?.newTab(arg),
  },
};
