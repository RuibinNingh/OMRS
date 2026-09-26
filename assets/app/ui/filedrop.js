/**
 * 文件拖放区：filedrop({id, title, hint, accept, multiple, disabled, error}) 产出 <label> 包着的 file input（键盘可达）；
 * bindFileDrop(zone, onFiles, onReject) 处理拖入高亮、放下与选择，回调收到 File[]；不符合 accept 的文件被滤掉并给区域加 is-error。
 */
import { html } from '../core/html.js';
import { icon } from './icon.js';

export function filedrop({ id, title = '拖入文件，或点击选择', hint = '', accept = '', multiple = false, disabled = false, error = '', state } = {}) {
  return html`<label class="ui-filedrop${error ? ' is-error' : ''}${disabled ? ' is-disabled' : ''}${state ? ` is-${state}` : ''}" data-filedrop>
<input class="ui-filedrop__input" type="file" id="${id}"${accept ? html` accept="${accept}"` : ''}${multiple ? html` multiple` : ''}${disabled ? html` disabled` : ''}>
<span class="ui-filedrop__icon">${icon('upload')}</span><span class="ui-filedrop__title">${title}</span>
${hint ? html`<span class="ui-filedrop__hint">${hint}</span>` : ''}${error ? html`<span class="ui-filedrop__error" role="alert">${error}</span>` : ''}
</label>`;
}

export function acceptsFile(file, accept) {
  if (!accept) return true;
  const name = String(file.name || '').toLowerCase();
  const type = String(file.type || '').toLowerCase();
  return accept.split(',').map(s => s.trim().toLowerCase()).filter(Boolean).some(rule => {
    if (rule.startsWith('.')) return name.endsWith(rule);
    if (rule.endsWith('/*')) return type.startsWith(rule.slice(0, -1));
    return type === rule;
  });
}

export function bindFileDrop(zone, onFiles, onReject) {
  const input = zone.querySelector('input[type="file"]');
  let depth = 0;
  const deliver = list => {
    const files = [...(list || [])];
    const ok = files.filter(file => acceptsFile(file, input?.getAttribute('accept') || ''));
    zone.classList.toggle('is-error', ok.length < files.length);
    if (ok.length < files.length) onReject?.(files.filter(file => !ok.includes(file)));
    if (ok.length) onFiles(input?.multiple ? ok : ok.slice(0, 1));
  };
  zone.addEventListener('dragenter', event => { event.preventDefault(); if (input?.disabled) return; depth += 1; zone.classList.add('is-dragover'); });
  zone.addEventListener('dragover', event => event.preventDefault());
  zone.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (!depth) zone.classList.remove('is-dragover'); });
  zone.addEventListener('drop', event => {
    event.preventDefault();
    depth = 0;
    zone.classList.remove('is-dragover');
    if (!input?.disabled) deliver(event.dataTransfer?.files);
  });
  input?.addEventListener('change', () => { deliver(input.files); input.value = ''; });
  return zone;
}
