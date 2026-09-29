/** 评测原判与人工复核；轮询只更新列表，不重建正在查看的双图或表单。 */
import { html } from '../../core/html.js';
import { render, morph } from '../../core/dom.js';
import { button } from '../../ui/button.js';
import { switchControl } from '../../ui/switch.js';

export const labels = { usable: '可直接使用', needs_adjustment: '需要调整', unusable: '不可使用', uncertain: '不确定' };
export function reviewPayload(audit, item, action, verdict, note) {
  return { audit, case: item.id, revision: item.revision, action, verdict, note };
}
const purposes = {historical_regression:'历史回归',calibration:'提示词校准',val:'验证集',train:'训练集',independent:'独立验收'};
const states = {done:'已评测',cached:'缓存',pending:'待评测',error:'调用失败',missing:'漏检'};
const pct = (n, d) => d ? `${n}/${d}（${Math.round(n / d * 100)}%）` : '暂无样本';

export function mountAudits(root, api) {
  let audits = [], rows = [], current = '', chosen = null, selected = null, sequence = 0, detailSequence = 0;
  let timer, disposed = false, saving = false, offset = 0, total = 0;
  render(root, html`<h2>评测记录</h2><p class="tp-muted">比较原图与实际裁图，检查 DeepSeek 是否误判。人工复核保留历史，不改变训练标注。</p>
    <div class="ta-filters">
      <label>模型<select class="ui-select" id="ta-model"><option value="">全部</option></select></label>
      <label>提示词<select class="ui-select" id="ta-prompt"><option value="">全部</option></select></label>
      <label>评测实验<select class="ui-select" id="ta-audit"></select></label>
      <label>目标<select class="ui-select" id="ta-role"><option value="">全部</option><option value="question">题目</option><option value="answer">答案</option></select></label>
      <label>DeepSeek 原判<select class="ui-select" id="ta-verdict"><option value="">全部</option>${Object.entries(labels).map(([k,v]) => html`<option value="${k}">${v}</option>`)}</select></label>
      <label>复核状态<select class="ui-select" id="ta-review"><option value="">全部</option><option value="pending">待复核</option><option value="disagreed">判定有分歧</option><option value="reviewed">已复核</option></select></label>
      ${button({ label: '刷新评测', action: 'ta-refresh' })}
    </div><p id="ta-error" class="tp-errors" role="alert"></p><div id="ta-summary"></div>
    <div id="ta-list" class="ta-list"></div><div id="ta-pages" class="tp-row"></div><div id="ta-detail"></div>`);
  const el = id => root.querySelector(`#ta-${id}`);
  const value = id => el(id).value;
  function error(message = '') { el('error').textContent = message; }
  function options() {
    const model = value('model'), prompt = value('prompt');
    morph(el('model'), html`<option value="">全部</option>${[...new Set(audits.map(a => a.model))].map(v => html`<option value="${v}">${v}</option>`)}`);
    morph(el('prompt'), html`<option value="">全部</option>${[...new Set(audits.flatMap(a => a.prompt_versions || [a.prompt_version]))].map(v => html`<option value="${v}">${v}</option>`)}`);
    el('model').value = model; el('prompt').value = prompt;
    const filtered = audits.filter(a => (!model || a.model === model) && (!prompt || (a.prompt_versions || [a.prompt_version]).includes(prompt)));
    if (!filtered.some(a => a.id === current)) current = filtered[0]?.id || '';
    morph(el('audit'), html`${filtered.map(a => html`<option value="${a.id}">${a.id} · ${purposes[a.purpose || a.split] || a.purpose || a.split}</option>`)}`);
    el('audit').value = current;
  }
  async function loadList() {
    const seq = ++sequence;
    if (!current) {
      rows = []; morph(el('summary'), html`<p class="tp-muted">暂无评测记录。用命令创建评测后，在这里查看与复核。</p>`);
      morph(el('list'), html``); morph(el('detail'), html``); return;
    }
    const params = new URLSearchParams({ id: current, role: value('role'), prompt_version: value('prompt'), verdict: value('verdict'), review: value('review'), offset, limit: 30 });
    const res = await api.get(`/api/trainpanel/audit?${params}`);
    if (disposed || seq !== sequence) return;
    if (!res.ok) { error(res.error.message); return; }
    const a = res.data.audit; rows = res.data.cases; total = res.data.total;
    const calibration = a.purpose === 'calibration';
    morph(el('summary'), html`<div class="tp-facts"><span>${calibration ? '提示词校准案例，不用于独立准确率' : `DeepSeek 判定整图通过：${pct(a.raw_passed, a.images)}`}</span>
      ${!calibration ? html`<span>复核后整图通过：${pct(a.reviewed_passed, a.images)}</span>` : ''}
      <span>已复核 ${a.reviewed}/${a.cases}，其中用户 ${a.user_reviewed}</span>
      <span>成功 ${a.states.done || 0} · 缓存 ${a.states.cached || 0} · 错误 ${a.states.error || 0} · 漏检 ${a.states.missing || 0} · 待评 ${a.states.pending || 0}</span>
      <span>参考估算 US$${Number(a.cost_usd || 0).toFixed(5)} · ${Number(a.seconds || 0).toFixed(1)} 秒</span>
      ${a.progress?.state === 'running' ? html`<span>评测运行中</span>` : ''}${a.progress?.error ? html`<span>${a.progress.error}</span>` : ''}</div>
      <p class="tp-muted">复核后指标中，未复核项仍沿用原判；不代表人工确认准确率。费用按官方价格估算，中转实际扣费未知。</p>`);
    morph(el('list'), html`${rows.length ? rows.map(c => button({label: `${c.id} · ${c.role === 'answer' ? '答案' : '题目'} · ${labels[c.judgment?.verdict] || states[c.state] || c.state} · ${c.review?.source==='user' ? '用户已复核' : (c.review ? '执行者已复核' : '待复核')}`, action:'ta-case', arg:c.id, variant:chosen===c.id?'primary':'secondary'})) : html`<p>没有符合筛选条件的记录。</p>`}`);
    morph(el('pages'), html`${button({label:'上一页',action:'ta-page-prev',disabled:offset===0})}<span>${total ? offset + 1 : 0}–${Math.min(offset+30,total)} / ${total}</span>${button({label:'下一页',action:'ta-page-next',disabled:offset+30>=total})}`);
  }
  async function refresh() {
    clearTimeout(timer);
    const res = await api.get('/api/trainpanel/audits');
    if (disposed) return;
    if (!res.ok) error(res.error.message);
    else { audits = res.data.audits; error((res.data.errors || []).map(e=>`${e.id}：${e.error}`).join('；')); options(); await loadList(); }
    if (!disposed && !document.hidden && audits.some(a => a.progress?.state === 'running' || a.states.pending)) timer = setTimeout(refresh, 5000);
  }
  async function open(id) {
    const seq = ++detailSequence, auditId = current;
    const res = await api.get(`/api/trainpanel/audit?${new URLSearchParams({id:auditId,case:id})}`);
    if (disposed || seq!==detailSequence || current!==auditId) return;
    if (!res.ok || !res.data.cases.length) { error(res.error?.message || '记录不存在'); return; }
    selected = res.data.cases[0]; chosen = id;
    const c = selected;
    const box = c.box || (c.crop_xyxy ? {x:c.crop_xyxy[0],y:c.crop_xyxy[1],w:c.crop_xyxy[2]-c.crop_xyxy[0],h:c.crop_xyxy[3]-c.crop_xyxy[1]} : null);
    const src = resource => `/api/trainpanel/audit-image?${new URLSearchParams({id:auditId,resource})}`;
    const picture = (kind, title) => html`<figure><figcaption>${title}</figcaption><div class="ta-viewport" data-zoom="1" tabindex="0" aria-label="${title}，放大后可拖动或滚动">
      <div class="ta-image">${c[kind] ? html`<img src="${src(c[kind])}" alt="${title}" draggable="false">${kind==='original' && box ? html`<svg class="ta-box-layer" viewBox="0 0 1 1" preserveAspectRatio="none" aria-label="模型框"><rect class="tp-box tp-box-${c.role}" x="${box.x}" y="${box.y}" width="${box.w}" height="${box.h}"></rect></svg>`:''}` : html`<p>未检测到必要区域，没有裁图。</p>`}</div></div></figure>`;
    morph(el('detail'), html`<h3>${c.id} · ${c.sample}</h3><div class="tp-row">
      ${button({label:'上一条',action:'ta-prev',disabled:rows.findIndex(x=>x.id===id)<=0})}${button({label:'下一条',action:'ta-next',disabled:rows.findIndex(x=>x.id===id)>=rows.length-1})}
      <label>缩放<select class="ui-select" id="ta-zoom"><option value="1">100%</option><option value="2">200%</option><option value="3">300%</option></select></label>
      ${switchControl({id:'ta-boxes',label:'显示模型框',checked:true})}</div>
      <div class="tp-cols ta-pictures">${picture('original','原图')}${picture('crop','实际裁图')}</div>
      <div class="tp-cols"><div><h3>DeepSeek 原判：${labels[c.judgment?.verdict] || states[c.state] || c.state}</h3>
        <p>${c.judgment?.evidence || c.error || '等待评测'}</p>
        <p>缺漏：${(c.judgment?.missing_content || []).join('；') || '无记录'}</p><p>多余：${(c.judgment?.extra_content || []).join('；') || '无记录'}</p>
        <p>截字：${c.judgment?.cut_characters ? '是' : '否'}；${c.seconds || 0} 秒；${c.usage?.total_tokens || 0} tokens</p>
        ${c.structural_error ? html`<p>结构问题：${c.structural_error==='missing'?'漏检':'多余框'}，修改裁判结论不能补出缺少的框。</p>`:''}
        ${c.kind ? html`<p>历史案例：${c.kind} · ${c.variant} ${c.scope_ambiguous?'· 曾有范围歧义':''}</p>`:''}</div>
        <div><h3>复核结论：${labels[c.effective] || '待复核'}</h3>
          <label>复核操作<select class="ui-select" id="ta-action"><option value="agree">同意</option><option value="correct">误判，纠正结论</option><option value="uncertain">不确定</option></select></label>
          <label>正确结论<select class="ui-select" id="ta-correct">${Object.entries(labels).map(([k,v])=>html`<option value="${k}">${v}</option>`)}</select></label>
          <label>说明<textarea class="ui-textarea" id="ta-note" maxlength="2000" rows="3"></textarea></label>
          ${button({label:'保存复核',action:'ta-save',variant:'primary'})}<p id="ta-saved" aria-live="polite"></p></div></div>
      <details><summary>调用记录（${c.attempts?.length || 0} 次）</summary><p>请求模型 ${c.requested_model || '—'}；返回模型 ${c.response_model || '—'}</p>
      ${(c.attempts || []).map(a=>html`<p>${states[a.state] || a.state} · ${a.error || '已返回'} · ${a.seconds || 0} 秒 · ${a.usage?.total_tokens || 0} tokens · 参考 US$${Number(a.cost_usd || 0).toFixed(6)}</p>`)}</details>
      <h3>复核历史</h3><div id="ta-history"></div>`);
    root.querySelectorAll('.ta-pictures img').forEach(fitLegacyBox);
    await history(auditId,id,seq);
  }
  async function history(auditId,id,seq) {
    const res = await api.get(`/api/trainpanel/reviews?${new URLSearchParams({id:auditId,case:id})}`);
    if (disposed || seq!==detailSequence) return;
    if (!res.ok) { error(res.error.message); return; }
    morph(el('history'),html`${res.data.reviews.length ? res.data.reviews.map(h=>html`<p>第 ${h.revision} 次 · ${h.source==='user'?'用户':'执行者'} · ${labels[h.verdict]} · ${h.created_at} ${h.note}</p>`):html`<p class="tp-muted">尚未复核</p>`}`);
  }
  root.addEventListener('change', event => {
    if (event.target.id==='ta-zoom') root.querySelectorAll('.ta-viewport').forEach(v=>{v.dataset.zoom=event.target.value;});
    else if (event.target.id==='ta-boxes') root.querySelectorAll('.ta-box-layer').forEach(v=>{v.hidden=!event.target.checked;});
    else if (['ta-model','ta-prompt','ta-audit','ta-role','ta-verdict','ta-review'].includes(event.target.id)) {
      if (saving) return;
      ++detailSequence; selected=null; chosen=null; morph(el('detail'),html``);offset=0;
      if (event.target.id==='ta-audit') current=value('audit');
      else if (['ta-model','ta-prompt'].includes(event.target.id)) options();
      loadList();
    }
  });
  root.addEventListener('click', async event => {
    const target=event.target.closest('[data-action]'); if (!target || target.disabled || saving) return;
    const action=target.dataset.action;
    if (action==='ta-refresh') { error(); refresh(); }
    if (action==='ta-case') open(target.dataset.arg);
    if (action==='ta-page-prev' || action==='ta-page-next') { offset+=action==='ta-page-next'?30:-30; loadList(); }
    if (action==='ta-prev' || action==='ta-next') {
      const at=rows.findIndex(c=>c.id===chosen)+(action==='ta-next'?1:-1);if(rows[at]) open(rows[at].id);
    }
    if (action==='ta-save' && selected) {
      saving=true;target.disabled=true;error();
      root.querySelectorAll('.ta-filters select').forEach(e=>{e.disabled=true;});
      const id=current, c=selected;
      const res=await api.post('/api/trainpanel/review',reviewPayload(id,c,value('action'),value('correct'),value('note')));
      saving=false; if(disposed)return;
      target.disabled=false;
      root.querySelectorAll('.ta-filters select').forEach(e=>{e.disabled=false;});
      if (!res.ok) {error(res.error.message);return;}
      await open(c.id);if(el('saved')) el('saved').textContent='复核已保存，原判保持不变。';await loadList();
    }
  });
  function fitLegacyBox(img) {
    const svg=img.nextElementSibling;
    if (svg?.classList.contains('ta-box-layer') && selected && !selected.box && img.naturalWidth) svg.setAttribute('viewBox',`0 0 ${img.naturalWidth} ${img.naturalHeight}`);
  }
  root.addEventListener('load',event=>{if(event.target.matches?.('.ta-pictures img'))fitLegacyBox(event.target);},true);
  let drag=null;
  root.addEventListener('pointerdown',e=>{const v=e.target.closest('.ta-viewport');if(v){drag={v,x:e.clientX,y:e.clientY,l:v.scrollLeft,t:v.scrollTop};v.setPointerCapture(e.pointerId);}});
  root.addEventListener('pointermove',e=>{if(drag){drag.v.scrollLeft=drag.l+drag.x-e.clientX;drag.v.scrollTop=drag.t+drag.y-e.clientY;}});
  root.addEventListener('pointerup',()=>{drag=null;});
  root.addEventListener('pointercancel',()=>{drag=null;});
  const visibility=()=>{clearTimeout(timer);if(!document.hidden)refresh();};
  document.addEventListener('visibilitychange',visibility);refresh();
  return ()=>{disposed=true;++sequence;++detailSequence;clearTimeout(timer);document.removeEventListener('visibilitychange',visibility);};
}
