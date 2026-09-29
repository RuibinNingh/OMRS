/** 受管检测服务；查看实验不改变在线模型，控制请求携带版本与唯一ID。 */
import { html } from '../../core/html.js';
import { morph } from '../../core/dom.js';
import { button } from '../../ui/button.js';
import { dialog } from '../../ui/dialog.js';

const names = {start:'启动服务',stop:'停止服务',restart:'重启服务',activate:'应用到框选',rollback:'恢复上一模型'};
export function controlPayload(data, action, model, requestId) {
  return {action, revision:data.revision, request_id:requestId, ...(action==='activate' ? {model_id:model.id,sha256:model.sha256,conf:model.conf,imgsz:model.imgsz} : {})};
}
export function modelScores(model) {
  return model?.scores?.length ? model.scores.map(s=>`${s.purpose==='independent'?'独立验收':'历史回归'}：原判 ${s.raw_passed}/${s.images}，复核后 ${s.reviewed_passed}/${s.images}；已复核 ${s.reviewed}/${s.cases}（用户 ${s.user_reviewed}）`).join('；') : '暂无内容验收记录，不代表质量达标';
}
export function mountControl(root, api, changed) {
  let data=null, selected='', timer=null, disposed=false, sending=false, generation=0;
  let pending=null, failure='';
  function paint() {
    if (!data) { morph(root,html`<h2>检测服务</h2><p role="status">${failure || '正在读取服务状态…'}</p>${button({label:'刷新服务',action:'tc-refresh'})}`);return; }
    if (!data.supported) { morph(root,html`<h2>检测服务</h2><p>${data.message}</p>`);return; }
    if (!data.models.some(m=>m.id===selected)) selected=data.models.find(m=>m.sha256===data.selected?.sha256)?.id || data.models[0]?.id || '';
    const model=data.models.find(m=>m.id===selected), busy=sending || data.operation?.state==='running';
    morph(root,html`<h2>检测服务</h2><div class="tp-facts">
      <span>${busy?'操作进行中':data.online?'检测服务在线':'检测服务离线'}</span>
      <span>实际在线：${data.online?.name || '未加载'}</span>
      ${data.online ? html`<span>${data.online.imgsz} · 置信度 ${data.online.conf} · SHA ${data.online.sha256}</span>`:''}
      ${data.online && !data.matches ? html`<strong>实际在线模型与所选配置不一致，请检查后重启服务。</strong>`:''}</div>
      <p>已配置模型：${data.selected?.name}。实时测试使用实际在线模型；查看下方实验或选择列表不会切换服务。</p>
      <div class="tp-row">${['start','stop','restart','rollback'].map(action=>button({label:names[action],action:'tc-action',arg:action,disabled:busy || (action==='rollback'&&!data.previous)}))}${button({label:'刷新服务',action:'tc-refresh',disabled:sending})}</div>
      <label class="tc-model-label">查看模型<select class="ui-select" id="tc-model" ${busy?'disabled':''}>${data.models.map(m=>html`<option value="${m.id}" ${m.id===selected?'selected':''}>${m.name}${m.sha256===data.online?.sha256?' · 当前在线':''}</option>`)}</select></label>
      <p id="tc-score">${modelScores(model)}</p><p>模型 ${model?.imgsz || '—'} · 置信度 ${model?.conf ?? '—'}。复核后指标含未复核原判，不是独立准确率。</p>
      ${button({label:names.activate,action:'tc-action',arg:'activate',variant:'primary',disabled:busy || !model})}
      <p id="tc-error" class="tp-errors" role="alert">${failure || data.operation?.rollback_error || data.operation?.error || ''}</p>
      ${pending ? button({label:'重试获取操作结果',action:'tc-retry',disabled:sending}):''}
      <p id="tc-result" aria-live="polite">${data.operation?.state==='done'?'上次操作已完成':data.operation?.state==='failed'?'上次操作失败，详见原因与历史':''}</p>
      ${data.errors?.map(e=>html`<p class="tp-errors">${e.id}：${e.error}</p>`)}
      <details><summary>服务操作历史</summary>${data.history?.map(h=>html`<p>${h.started_at} · ${h.actor} · ${names[h.action]} · ${h.state==='done'?'完成':h.state==='failed'?'失败':'进行中'} ${h.model_id || ''} ${h.error || ''} ${h.rollback_error || ''}</p>`)}</details>`);
  }
  async function refresh() {
    clearTimeout(timer); const gen=++generation;
    const res=await api.get('/api/trainpanel/manager');
    if (disposed || gen!==generation) return;
    if (res.ok) {
      const before=data?.online?.sha256; const wasRunning=data?.operation?.state==='running';
      data=res.data;
      if (before!==data.online?.sha256 || (wasRunning && data.operation?.state!=='running')) changed();
    } else failure=res.error.message;
    paint();
    if (!document.hidden && !disposed) timer=setTimeout(refresh,data?.operation?.state==='running'?1000:5000);
  }
  async function send(payload) {
    sending=true; failure='';paint();
    const res=await api.post('/api/trainpanel/control',payload);
    if (disposed) return;
    sending=false;
    if (!res.ok) {failure=res.error.message; pending=res.status===0 ? payload : null;} else {pending=null;failure='';}
    await refresh();changed();
  }
  async function click(event) {
    const target=event.target.closest('[data-action]');if(!target || target.disabled)return;
    if(target.dataset.action==='tc-refresh') {failure='';await refresh();return;}
    if(target.dataset.action==='tc-retry'&&pending) {await send(pending);return;}
    if(target.dataset.action!=='tc-action')return;
    const action=target.dataset.arg, model=data.models.find(m=>m.id===selected);
    const payload=controlPayload(data,action,model,crypto.randomUUID().replaceAll('-',''));
    const answer=await dialog({title:names[action],size:'md',okText:'确认'+names[action],body:html`<p>此操作影响收件箱和聊天草稿的自动框选。</p>${action==='activate'?html`<p>将应用 ${model.name}。${modelScores(model)}</p><p>先预检模型，再切换服务；失败自动恢复原模型。不会启动训练或付费评测。</p>`:html`<p>${action==='stop'?'停止后自动框选暂不可用。':action==='rollback'?'恢复最近一次切换前的模型。':'服务启动后会核验实际加载的模型。'}</p>`}`});
    if(answer.ok && !disposed) await send(payload);
  }
  root.addEventListener('click',click);
  root.addEventListener('change',event=>{if(event.target.id==='tc-model'){selected=event.target.value;paint();}});
  const visibility=()=>{clearTimeout(timer);if(!document.hidden)refresh();};
  document.addEventListener('visibilitychange',visibility);paint();refresh();
  return ()=>{disposed=true;++generation;clearTimeout(timer);root.removeEventListener('click',click);document.removeEventListener('visibilitychange',visibility);};
}
