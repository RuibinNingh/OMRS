/** 图片实时测试：独立于轮询区，原图预览不随进度更新重建。 */
import { html } from '../../core/html.js';
import { render, morph } from '../../core/dom.js';
import { filedrop, bindFileDrop } from '../../ui/filedrop.js';
import { button } from '../../ui/button.js';
import { switchControl } from '../../ui/switch.js';
import { status } from '../../ui/status.js';
import { pct } from './state.js';

export function mountTry(root, api) {
  let file = null, url = '', busy = false, saving = false, result = null, error = '', collect = false;
  render(root, html`<h2>实时测试</h2><p class="tp-muted">上传一张截图，查看题目与答案框。也可粘贴图片。</p>
    ${filedrop({ id: 'tp-file', title: '拖入图片，或点击选择', hint: 'PNG / JPEG / GIF，≤15 MB', accept: 'image/png,image/jpeg,image/gif' })}
    <div id="tp-try-controls" class="tp-row tp-try-controls"></div><div id="tp-try-result" class="tp-try-result" aria-live="polite"></div>`);
  const controls = root.querySelector('#tp-try-controls');
  const host = root.querySelector('#tp-try-result');
  function paint() {
    morph(controls, html`<div class="tp-row">${button({ label: '测试', variant: 'primary', loading: busy, disabled: !file || busy, action: 'test' })}<span class="tp-muted">${file?.name || '尚未选择图片'}</span></div>
      ${switchControl({ id: 'tp-collect', label: '积累到标注集', checked: collect, disabled: saving || busy })}`);
    morph(host, html`${error ? html`<p class="tp-errors" role="alert">${error}</p>` : ''}
      ${result ? html`<div class="tp-facts"><span>${result.width} × ${result.height}</span><span>${result.strips} 条带</span><span>${result.elapsed_ms} ms</span>${result.boxes.map(box => html`<span>${box.role === 'answer' ? '答案' : '题目'} · 置信度 ${pct(box.conf)}</span>`)}</div>
        ${result.collected ? html`<div class="tp-row">${status({ tone: 'success', text: result.collected.duplicate ? '标注集里已有这张' : '已加入标注集（待校正）' })}<a class="tp-link" href="/annotate" target="_blank" rel="noopener">打开标注页校正</a></div>` : ''}
        ${result.collect_error ? html`<p class="tp-errors">${result.collect_error}</p>` : ''}` : ''}
      ${url ? html`<div class="tp-preview"><img src="${url}" alt="实时测试原图">${result ? html`<svg viewBox="0 0 ${result.width} ${result.height}" aria-label="模型框选结果">${result.boxes.map(box => html`<rect class="tp-box tp-box-${box.role}" x="${box.x * result.width}" y="${box.y * result.height}" width="${box.w * result.width}" height="${box.h * result.height}"></rect>`)}</svg>` : ''}</div>` : ''}`);
  }
  function choose(files) {
    if (busy) return;
    const next = files[0];
    if (!next) return;
    if (!['image/png', 'image/jpeg', 'image/gif'].includes(next.type) || next.size > 15 * 1024 * 1024) { error = '请选择不超过 15 MB 的 PNG、JPEG 或 GIF'; paint(); return; }
    if (url) URL.revokeObjectURL(url);
    file = next; url = URL.createObjectURL(file); result = null; error = ''; paint();
  }
  bindFileDrop(root.querySelector('[data-filedrop]'), choose, () => { error = '只支持 PNG、JPEG 或 GIF'; paint(); });
  const paste = event => {
    if (event.target.closest?.('input:not([type=file]), textarea, [contenteditable]')) return;
    const files = [...(event.clipboardData?.files || [])];
    if (files.length) { event.preventDefault(); choose(files); }
  };
  document.addEventListener('paste', paste);
  root.addEventListener('click', async event => {
    if (!event.target.closest('[data-action="test"]') || !file || busy) return;
    busy = true; error = ''; result = null; paint();
    const form = new FormData(); form.append('file', file, file.name || 'image.png');
    const response = await api.request('/api/trainpanel/try', { method: 'POST', body: form, timeout: 180000 });
    busy = false;
    if (response.ok) result = response.data;
    else error = response.error?.message || '检测失败，请重试';
    paint();
  });
  root.addEventListener('change', async event => {
    if (event.target.id !== 'tp-collect' || saving) return;
    const value = event.target.checked;
    saving = true; paint();
    const response = await api.post('/api/config', { train_try_collect: value });
    saving = false;
    if (response.ok) collect = value;
    else error = response.error?.message || '保存积累开关失败';
    paint();
  });
  paint();
  return { sync(value) { if (!saving && !busy && collect !== value) { collect = value; paint(); } },
    dispose() { document.removeEventListener('paste', paste); if (url) URL.revokeObjectURL(url); } };
}
