/** 调度提醒全局默认，预览走服务端静态与纸面profile校验。 */
import { html } from '../../core/html.js';
import { morph } from '../../core/dom.js';
import { get, post } from '../../core/api.js';
export const bannerView = () => html`<div class="card st-card" id="st-banner-card"><div class="card-title">调度提醒</div><p class="hint">新建正式计划时固定首页提醒。旧计划保持原快照；单次导出可以关闭或替换。</p><div id="st-banner-editor"></div></div>`;
export function createScheduleBanner(root) {
  const host = root.querySelector('#st-banner-editor');
  const s = {enabled:false,svg:'',revision:0,src:'',message:'',busy:false};
  let alive = true;
  function paint() {
    if (!alive) return;
    morph(host,html`<label class="st-row"><span>新计划默认启用首页 SVG</span><input type="checkbox" data-banner-enabled ${s.enabled ? 'checked' : ''}></label><label>SVG 源码<textarea class="ui-textarea" rows="5" data-banner-svg placeholder="粘贴静态SVG，建议高度10–18mm">${s.svg}</textarea></label><label>上传 SVG<input type="file" class="ui-input" accept="image/svg+xml,.svg" data-banner-file></label><p class="hint">通栏显示，高度不超过28mm；文字至少8.5pt。危险内容、外部资源和过高图形会被拒绝。</p><div class="st-actions"><button class="ui-btn" data-banner-preview>校验并预览</button><button class="ui-btn ui-btn--primary" data-banner-save ${s.busy ? 'disabled' : ''}>保存调度提醒</button><button class="ui-btn ui-btn--ghost" data-banner-remove>删除提醒</button></div>${s.src ? html`<img class="st-banner-preview" src="${s.src}" alt="调度首页提醒预览">` : ''}<p class="st-status" role="status">${s.message}</p>`);
  }
  const input = e => { if (e.target.matches('[data-banner-svg]')) s.svg = e.target.value; if (e.target.matches('[data-banner-enabled]')) s.enabled = e.target.checked; };
  const change = async e => { if (e.target.matches('[data-banner-file]') && e.target.files[0]) { s.svg = await e.target.files[0].text(); paint(); } };
  async function click(e) {
    if (e.target.closest('[data-banner-remove]')) { s.svg = ''; s.src = ''; s.enabled = false; paint(); return; }
    const preview = e.target.closest('[data-banner-preview]');
    if (!preview && !e.target.closest('[data-banner-save]')) return;
    if (s.busy) return;
    s.busy = true; paint();
    const res = await post(preview ? '/api/schedule-banner/preview' : '/api/schedule-banner',{enabled:s.enabled,svg:s.svg,expected_revision:s.revision});
    s.busy = false;
    if (res.ok) { if (!preview) s.revision = res.data.revision; s.src = res.data.snapshot?.src || ''; s.message = preview ? '校验通过；预览按通栏比例显示。' : '已保存，仅影响之后创建的计划。'; } else s.message = res.error?.message || '保存失败，输入已保留';
    paint();
  }
  host.addEventListener('input',input); host.addEventListener('change',input); host.addEventListener('change',change); host.addEventListener('click',click);
  return { async load() { const res = await get('/api/schedule-banner'); if (res.ok) { Object.assign(s,res.data); s.src = res.data.snapshot?.src || ''; } else s.message = res.error?.message || '读取失败'; paint(); }, dispose() { alive = false; host.removeEventListener('input',input); host.removeEventListener('change',input); host.removeEventListener('change',change); host.removeEventListener('click',click); } };
}
