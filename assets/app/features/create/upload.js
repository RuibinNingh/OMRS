/** 上传只负责把原图送进暂存收件箱；列表仍由旧控制器维护。 */
import { render } from '../../core/dom.js';
import { uploadFiles } from '../../core/uploads.js';
import { bindFileDrop } from '../../ui/filedrop.js';
import { toast } from '../../ui/toast.js';
import { uploadView } from './upload-view.js';

export function createUpload(root, bus) {
  const host = root.querySelector('#create-upload');
  render(host, uploadView());
  const zone = host.querySelector('[data-filedrop]');
  const input = host.querySelector('#ib-file');
  const status = host.querySelector('#ib-up-status');
  const clipboard = host.querySelector('[data-action="create.clipboard"]');
  let busy = false;
  let alive = true;

  function message(value, error = false) {
    if (!alive) return;
    status.textContent = value;
    status.classList.toggle('is-error', error);
    status.setAttribute('role', error ? 'alert' : 'status');
  }

  async function upload(files) {
    if (!alive) return;
    const list = [...(files || [])].filter(file => file && file.type?.startsWith('image/'));
    if (!list.length) { message('请选择图片文件', true); return; }
    if (busy) return;
    busy = true;
    input.disabled = true;
    clipboard.disabled = true;
    zone.classList.add('is-disabled');
    message(`上传 ${list.length} 张…`);
    const result = await uploadFiles(list, 'inbox', '/api/inbox/upload-refs');
    if (result.ok) {
      const count = result.data?.items?.length || 0;
      const duplicates = result.data?.duplicates?.length || 0;
      const summary = `已接收 ${count} 张${duplicates ? `，${duplicates} 张与收件箱已有图片相同，已合并` : ''}`;
      message(summary);
      toast(summary, { kind: 'ok' });
      if (alive) bus.emit('inbox:reload');
    } else {
      message(`上传失败：${result.error?.message || '未知错误'}`, true);
    }
    busy = false;
    if (alive) { input.disabled = false; clipboard.disabled = false; zone.classList.remove('is-disabled'); }
  }

  bindFileDrop(zone, upload, () => message('请选择图片文件', true));

  function onPaste(event) {
    if (!root.classList.contains('active') || !root.querySelector('#ib-stage-upload')?.classList.contains('on')) return;
    const files = [...(event.clipboardData?.items || [])]
      .filter(item => item.kind === 'file' && item.type.startsWith('image/'))
      .map(item => item.getAsFile()).filter(Boolean);
    if (!files.length) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    upload(files);
  }
  document.addEventListener('paste', onPaste, true);

  async function readClipboard() {
    if (!navigator.clipboard?.read) { message('浏览器不支持读取剪贴板，请用 Ctrl / ⌘ + V', true); return; }
    try {
      const items = await navigator.clipboard.read();
      const files = [];
      for (const item of items) {
        const type = (item.types || []).find(value => value.startsWith('image/'));
        if (type) files.push(new File([await item.getType(type)], `clipboard-${Date.now()}.png`, { type }));
      }
      if (!alive) return;
      if (files.length) await upload(files);
      else message('剪贴板里没有图片', true);
    } catch (error) { message(`读取剪贴板失败：${error.message || error}`, true); }
  }

  return {
    readClipboard,
    dispose() { alive = false; document.removeEventListener('paste', onPaste, true); },
  };
}
