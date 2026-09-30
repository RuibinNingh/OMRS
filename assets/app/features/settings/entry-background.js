/** 入口背景的纯规则与设置卡片控制器。入口页和设置页共用模式、样式与模糊参数语义。 */
import { get, post } from '../../core/api.js';

export const ENTRY_BACKGROUND_MODES = ['black-hole', 'custom'];
export const ENTRY_BACKGROUND_STYLE = 'gaussian-blur';
export const ENTRY_BACKGROUND_MIN_BLUR = 0;
export const ENTRY_BACKGROUND_MAX_BLUR = 32;
export const ENTRY_BACKGROUND_MAX_BYTES = 200 * 1024 * 1024;
export const ENTRY_BACKGROUND_MIME = Object.freeze({
  'image/png': 'image', 'image/jpeg': 'image', 'image/webp': 'image',
  'image/gif': 'image', 'image/avif': 'image', 'image/bmp': 'image',
  'video/mp4': 'video', 'video/webm': 'video', 'video/ogg': 'video',
});

export function clampBlur(value) {
  const number = Number.parseInt(value, 10);
  if (!Number.isFinite(number)) return ENTRY_BACKGROUND_MIN_BLUR;
  return Math.max(ENTRY_BACKGROUND_MIN_BLUR, Math.min(ENTRY_BACKGROUND_MAX_BLUR, number));
}

export function normalizeEntryBackground(value) {
  const source = value && typeof value === 'object' ? value : {};
  const mode = ENTRY_BACKGROUND_MODES.includes(source.mode) ? source.mode : 'black-hole';
  const asset = source.asset && typeof source.asset === 'object' ? source.asset : null;
  return {
    mode,
    style: source.style === ENTRY_BACKGROUND_STYLE ? source.style : ENTRY_BACKGROUND_STYLE,
    blur_px: clampBlur(source.blur_px),
    asset,
  };
}

export function formatEntryBytes(value) {
  const bytes = Math.max(0, Number(value) || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`;
}

export function validateEntryFile(file) {
  if (!file) return { ok: false, message: '请选择图片或视频文件。' };
  if (!file.size) return { ok: false, message: '入口背景文件不能为空。' };
  if (file.size > ENTRY_BACKGROUND_MAX_BYTES) return { ok: false, message: '入口背景文件不能超过 200 MB。' };
  const kind = ENTRY_BACKGROUND_MIME[String(file.type || '').toLowerCase()];
  if (!kind) return { ok: false, message: '只支持常见 PNG、JPEG、WebP、GIF、AVIF、BMP 图片和 MP4、WebM、Ogg 视频。' };
  return { ok: true, kind };
}

function fileMeta(file) {
  const checked = validateEntryFile(file);
  if (!checked.ok) return checked.message;
  return `${file.name || '未命名文件'} · ${checked.kind === 'video' ? '视频' : '图片'} · ${formatEntryBytes(file.size)}`;
}

export function createEntryBackground(root) {
  const el = id => root.querySelector(`#${id}`);
  let alive = true;
  let busy = false;
  let state = normalizeEntryBackground(null);
  let pendingFile = null;
  let previewUrl = '';

  const note = (text, tone = '') => {
    const target = el('st-entry-background-status');
    if (target) { target.textContent = text; target.dataset.tone = tone; }
  };

  function revokePreview() {
    if (previewUrl && typeof URL !== 'undefined' && URL.revokeObjectURL) URL.revokeObjectURL(previewUrl);
    previewUrl = '';
  }

  function renderPreview() {
    const host = el('st-entry-background-preview');
    if (!host || typeof document === 'undefined') return;
    host.replaceChildren();
    host.dataset.mode = state.mode;
    host.dataset.blur = String(state.blur_px);
    if (state.mode === 'black-hole') {
      const visual = document.createElement('div');
      visual.className = 'st-entry-preview-hole';
      visual.setAttribute('aria-label', '黑洞 WebGL 入口预设');
      const title = document.createElement('span');
      title.textContent = 'BLACK HOLE';
      const caption = document.createElement('b');
      caption.textContent = 'WebGL 入口预设';
      visual.append(title, caption);
      host.append(visual);
      return;
    }
    const file = pendingFile;
    const asset = state.asset;
    const kind = file ? ENTRY_BACKGROUND_MIME[String(file.type || '').toLowerCase()] : asset?.kind;
    const source = file ? previewUrl : asset?.id ? `/api/entry-background?v=${encodeURIComponent(asset.id)}` : '';
    if (!source || !kind) {
      const empty = document.createElement('div');
      empty.className = 'st-entry-preview-empty';
      empty.textContent = '上传图片或视频后在这里预览';
      host.append(empty);
      return;
    }
    const media = document.createElement(kind === 'video' ? 'video' : 'img');
    media.className = 'st-entry-preview-media';
    media.src = source;
    media.alt = kind === 'video' ? '入口视频预览' : '入口图片预览';
    if (kind === 'video') {
      media.muted = true; media.loop = true; media.autoplay = true; media.playsInline = true;
      media.controls = false;
      media.addEventListener('loadeddata', () => media.play().catch(() => {}), { once: true });
    }
    host.append(media);
  }

  function render() {
    if (!alive) return;
    const black = el('st-entry-background-black-hole');
    const custom = el('st-entry-background-custom');
    black?.classList.toggle('active', state.mode === 'black-hole');
    custom?.classList.toggle('active', state.mode === 'custom');
    black?.setAttribute('aria-pressed', String(state.mode === 'black-hole'));
    custom?.setAttribute('aria-pressed', String(state.mode === 'custom'));
    const style = el('st-entry-background-style');
    if (style) style.value = state.style;
    const blur = el('st-entry-background-blur');
    if (blur) blur.value = String(state.blur_px);
    const output = el('st-entry-background-blur-value');
    if (output) output.textContent = `${state.blur_px}px`;
    const file = el('st-entry-background-file');
    if (file) file.disabled = state.mode !== 'custom';
    const meta = el('st-entry-background-file-meta');
    if (meta) meta.textContent = pendingFile ? fileMeta(pendingFile)
      : state.asset ? `${state.asset.kind === 'video' ? '视频' : '图片'} · ${formatEntryBytes(state.asset.bytes)} · 已保存`
        : state.mode === 'custom' ? '尚未上传媒体文件' : '切换到自定义后可上传媒体';
    renderPreview();
  }

  async function load() {
    const result = await get('/api/config');
    if (!alive) return result;
    if (!result.ok) { note(`无法读取入口背景：${result.error?.message || '未知错误'}`, 'danger'); return result; }
    state = normalizeEntryBackground(result.data?.entry_background);
    pendingFile = null; revokePreview(); render();
    return result;
  }

  function mode(value) {
    if (!ENTRY_BACKGROUND_MODES.includes(value)) return;
    state = { ...state, mode: value };
    note(''); render();
  }

  function blur(value) {
    state = { ...state, blur_px: clampBlur(value) };
    render();
  }

  function choose(event) {
    const file = event?.target?.files?.[0];
    if (event?.target) event.target.value = '';
    const checked = validateEntryFile(file);
    if (!checked.ok) { note(checked.message, 'danger'); return; }
    pendingFile = file;
    state = { ...state, mode: 'custom' };
    revokePreview();
    if (typeof URL !== 'undefined' && URL.createObjectURL) previewUrl = URL.createObjectURL(file);
    note('文件已载入本地预览，点击保存后上传。', 'success');
    render();
  }

  async function save() {
    if (busy) return false;
    if (state.mode === 'custom' && !pendingFile && !state.asset) {
      note('自定义背景需要先上传图片或视频。', 'danger'); return false;
    }
    const form = new FormData();
    form.append('mode', state.mode);
    form.append('style', ENTRY_BACKGROUND_STYLE);
    form.append('blur_px', String(clampBlur(state.blur_px)));
    if (state.mode === 'custom' && state.asset && !pendingFile) form.append('asset_id', state.asset.id);
    if (pendingFile) form.append('file', pendingFile, pendingFile.name);
    busy = true; note('正在保存入口背景…', 'busy');
    const result = await post('/api/entry-background', form);
    busy = false;
    if (!alive) return false;
    if (!result.ok) { note(`保存失败：${result.error?.message || '未知错误'}`, 'danger'); return false; }
    state = normalizeEntryBackground(result.data?.entry_background);
    pendingFile = null; revokePreview(); render();
    note(state.mode === 'black-hole' ? '已恢复黑洞入口预设。' : '入口背景已保存，下一次打开入口页即可看到。', 'success');
    return true;
  }

  return { load, mode, blur, choose, save, render, state: () => state,
    dispose() { alive = false; pendingFile = null; revokePreview(); } };
}
