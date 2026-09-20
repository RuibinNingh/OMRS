// 复习计划工作区与共享 Session 同步；扫描、录入入口保留。
let SCH_VIEW = 'arrange';
let SCH_EXPORT_RETURN = 'arrange';
let SCH_SESSION_REQUEST = 0;
let SCH_DETAIL_REQUEST = 0;
let SCH_SESSIONS_LOADING = false;
let SCH_SESSIONS_ERROR = '';
let SCH_SELECTED_ID = '';
let SCH_DETAIL = null;

function schShow(view) {
  const changed = SCH_VIEW !== view;
  SCH_VIEW = view;
  document.getElementById('recommend-panel-v2').hidden = view !== 'arrange';
  document.getElementById('sch-plans').hidden = view !== 'plans';
  document.getElementById('export-panel').style.display = view === 'export' ? 'block' : 'none';
  for (const name of ['arrange','plans']) {
    const tab = document.getElementById(`sch-tab-${name}`);
    tab.classList.toggle('active',view === name);
    tab.setAttribute('aria-selected',String(view === name));
    tab.tabIndex = view === name ? 0 : -1;
  }
  if (view === 'arrange') renderUnifiedListV2();
  if (view === 'plans') schRenderPlans();
  if (view === 'export') renderExportPicker();
  if (changed) document.getElementById('panel-schedule').scrollIntoView({block:'start'});
}
document.addEventListener('keydown', event => {
  if (!event.target.matches('.sch-tab') || !['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
  event.preventDefault();
  const view = event.key === 'Home' ? 'arrange' : event.key === 'End' ? 'plans' : SCH_VIEW === 'arrange' ? 'plans' : 'arrange';
  schShow(view);
  document.getElementById(`sch-tab-${view}`).focus();
});
function schEnter() {
  initRecommendV2();
  schShow(SCH_VIEW);
  refreshSessions();
  loadRecommendationsV2();
}
async function refreshSessions() {
  const request = ++SCH_SESSION_REQUEST;
  SCH_SESSIONS_LOADING = true;
  SCH_SESSIONS_ERROR = '';
  schRenderPlans();
  try {
    const result = await api('/api/sessions');
    if (request !== SCH_SESSION_REQUEST) return;
    SESSIONS = result.sessions || [];
    refreshFbSessionPicker();
    if (typeof renderActionPlan === 'function' && DATA) renderActionPlan();
  } catch (error) {
    if (request !== SCH_SESSION_REQUEST) return;
    SCH_SESSIONS_ERROR = error.message;
  } finally {
    if (request === SCH_SESSION_REQUEST) {
      SCH_SESSIONS_LOADING = false;
      schRenderPlans();
      if (typeof renderUnifiedListV2 === 'function') renderUnifiedListV2();
      if (!SCH_SESSIONS_ERROR && SCH_SELECTED_ID && SCH_VIEW === 'plans') await schOpenPlan(SCH_SELECTED_ID, false);
    }
  }
}
function schRenderPlans() {
  const box = document.getElementById('sch-plan-list');
  if (!box) return;
  const active = (SESSIONS || []).filter(s => (s.status || 'active') === 'active').length;
  document.getElementById('sch-plan-count').textContent = `待完成 ${active}`;
  const status = document.getElementById('sch-session-status');
  status.innerHTML = SCH_SESSIONS_ERROR ? `计划加载失败：${escapeHtml(SCH_SESSIONS_ERROR)} <button class="btn sm" onclick="refreshSessions()">重试</button>` : SCH_SESSIONS_LOADING ? '正在更新计划…' : '';
  const filter = document.getElementById('sch-plan-filter').value;
  const text = document.getElementById('sch-plan-search').value.trim().toLowerCase();
  const plans = (SESSIONS || []).filter(s => (filter === 'all' || s.status === filter) && s.session_id.toLowerCase().includes(text));
  box.innerHTML = plans.length ? plans.map(s => {
    const progress = fbSessionProgress(s);
    return `<button class="sch-plan ${SCH_SELECTED_ID === s.session_id?'active':''}" onclick="schOpenPlan(${jsArg(s.session_id)})" aria-pressed="${SCH_SELECTED_ID === s.session_id}">
      <span class="sch-plan-head"><strong>${escapeHtml(s.created_at.replace('T',' ').slice(0,16))}</strong><span class="sch-reason">${s.status === 'completed'?'已完成':'待完成'}</span></span>
      <span>${escapeHtml(s.subject_filter || '多科复习')} · ${progress.total} 题</span>
      <progress max="${Math.max(1,progress.total)}" value="${progress.feedback_count}" aria-label="计划完成进度"></progress>
      <span class="sch-meta">已录入 ${progress.feedback_count} / 共 ${progress.total} 题</span><span class="sch-plan-id">${escapeHtml(s.session_id)}</span></button>`;
  }).join('') : `<div class="sch-empty">${SCH_SESSIONS_ERROR?'暂时无法获取计划，请重试。':SCH_SESSIONS_LOADING?'正在读取计划…':'没有符合条件的计划。'}<button class="btn sm" onclick="schShow('arrange')">安排新复习</button></div>`;
}
async function schOpenPlan(sessionId, focus = true) {
  const request = ++SCH_DETAIL_REQUEST;
  SCH_SELECTED_ID = sessionId;
  SCH_DETAIL = null;
  schRenderPlans();
  const box = document.getElementById('sch-plan-detail');
  if (focus) document.getElementById('sch-plan-work').classList.add('show-detail');
  box.innerHTML = '<div class="empty-inline" role="status">正在读取计划详情…</div>';
  try {
    const detail = await api(`/api/session?id=${encodeURIComponent(sessionId)}`);
    if (request !== SCH_DETAIL_REQUEST) return;
    SCH_DETAIL = detail;
    const recorded = new Set(detail.feedback_uids || []);
    const items = detail.items || [];
    qvSetContext('schedule-plan',items.filter(i => !i._missing).map(i => i.UID || i.uid));
    box.innerHTML = `<button class="btn sm sch-back" onclick="schBackToPlans()">← 返回计划列表</button>
      <div class="sch-detail-head"><div><h3>${escapeHtml(detail.subject_filter || '多科')}复习计划</h3><p class="sch-meta">${escapeHtml(detail.created_at.replace('T',' '))} · ${escapeHtml(sessionId)}</p></div><span class="sch-reason">${detail.status === 'completed'?'已完成':'待完成'}</span></div>
      <div class="sch-progress-summary"><strong>已录入 ${detail.feedback_count || 0} / 共 ${detail.count} 题</strong><span class="hint">${detail.pending_count ? `还有 ${detail.pending_count} 题待录入` : '本次复习已全部录入'}</span></div>
      <div class="sch-actions"><button class="btn primary" onclick="feedbackSession(${jsArg(sessionId)})" ${!detail.pending_count || detail.status === 'completed'?'disabled':''}>录入结果</button><button class="btn" onclick="schExportPlan('a4')">导出打印版</button><button class="btn" onclick="schExportPlan('screen')">导出屏幕版</button></div>
      <details class="sch-export-options"><summary>打印选项</summary><div class="sch-actions"><label><input id="sch-include-answers" type="checkbox"> 附带答案</label><label>题间留白 <input id="sch-question-gap" class="input" type="number" min="0" max="20" value="0"> 行</label></div></details>
      <div id="sch-status" class="sch-status" role="status"></div>
      <div class="sch-detail-questions">${items.map((item,index) => {
        const uid = item.UID || item.uid;
        return `<div class="sch-plan-question"><span class="sch-number">${index+1}</span><div class="sch-question-main"><strong>${escapeHtml(uid)}</strong><div class="sch-meta">${item._missing?'题目已缺失，无法预览':`${escapeHtml(item.Subject || item.subject || '')} · ${escapeHtml(item.Category || item.category || '')}`}</div></div><span class="sch-reason ${recorded.has(uid)?'is-done':''}">${recorded.has(uid)?'已录入':'待录入'}</span><button class="btn sm" ${item._missing?'disabled':''} onclick="viewQ(${jsArg(uid)},'schedule-plan')">预览</button></div>`;
      }).join('')}</div>`;
    if (focus && window.matchMedia('(max-width:760px)').matches) box.scrollIntoView({block:'start'});
  } catch (error) {
    if (request !== SCH_DETAIL_REQUEST) return;
    box.innerHTML = `<button class="btn sm" onclick="schBackToPlans()">← 返回计划列表</button><div class="sch-empty">无法读取计划：${escapeHtml(error.message)}<button class="btn" onclick="schOpenPlan(${jsArg(sessionId)})">重试</button></div>`;
  }
}
function schBackToPlans() { document.getElementById('sch-plan-work').classList.remove('show-detail'); }
async function schExportPlan(variant) {
  if (!SCH_DETAIL) return;
  setExportVariant(variant);
  await exportSession(SCH_DETAIL.session_id);
}
async function previewSession(sessionId) { switchTab('schedule'); schShow('plans'); await schOpenPlan(sessionId); }
async function feedbackSession(sessionId) {
  switchTab('feedback');
  await refreshSessions();
  if (!SESSIONS.some(s => s.session_id === sessionId)) { uiToast('暂时无法读取该计划，请刷新后重试。',{kind:'error'}); return; }
  document.getElementById('fb-session-picker').value = sessionId;
  await onFbSessionChange();
}
function refreshFbSessionPicker(){const picker=document.getElementById('fb-session-picker');if(!picker)return;const current=picker.value;picker.innerHTML='<option value="">— 手动录入(不关联 Session) —</option>'+SESSIONS.map(session=>{const progress=fbSessionProgress(session);const label=`${session.session_id} · ${session.subject_filter||'全部'} · ${progress.feedback_count}/${progress.total}题${progress.pending_count?` · 待录${progress.pending_count}`:' · 已完成'}`;return `<option value="${escapeAttr(session.session_id)}">${escapeHtml(label)}</option>`}).join('');if(current&&SESSIONS.find(session=>session.session_id===current))picker.value=current}
function resetCreateForm(){['cr-subject','cr-category','cr-note','cr-related','cr-question','cr-answer','cr-cause'].forEach(id=>{const el=document.getElementById(id);if(el)el.value=''});if(typeof setCreateLabels==='function')setCreateLabels([]);else{const labels=document.getElementById('cr-labels-value');if(labels)labels.value=''}const diff=document.getElementById('cr-diff');if(diff)diff.value='5';const diffVal=document.getElementById('cr-diff-val');if(diffVal)diffVal.textContent='5';CR_Q_IMAGES.length=0;CR_A_IMAGES.length=0;if(typeof crRenderImages==='function'){crRenderImages('q');crRenderImages('a')}['cr-classify-status','cr-extract-status'].forEach(id=>{const el=document.getElementById(id);if(el){el.textContent='';el.className='ai-status'}})}
async function doCreate(){const subject=document.getElementById('cr-subject').value.trim();const category=document.getElementById('cr-category').value.trim();const difficulty=document.getElementById('cr-diff').value;const note=document.getElementById('cr-note').value.trim();const relatedRaw=document.getElementById('cr-related').value.trim();const relatedTags=relatedRaw?relatedRaw.split(/[,，]/).map(tag=>tag.trim()).filter(Boolean):[];const labels=typeof selectedCreateLabels==='function'?selectedCreateLabels():String(document.getElementById('cr-labels-value')?.value||'').split('|').map(value=>value.trim()).filter(Boolean);const questionText=(document.getElementById('cr-question')?.value||'').trim();const answerText=(document.getElementById('cr-answer')?.value||'').trim();const cause=(document.getElementById('cr-cause')?.value||'').trim();const questionImages=(CR_Q_IMAGES||[]).map(img=>({data:img.dataUrl}));const answerImages=(CR_A_IMAGES||[]).map(img=>({data:img.dataUrl}));if(!subject||!category){uiToast('请填写科目和分类',{kind:'warn'});return}const button=document.getElementById('cr-btn');button.disabled=true;button.textContent='创建中...';try{const result=await api('/api/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({subject,category,difficulty:+difficulty,note,related_tags:relatedTags,labels,question_text:questionText,answer_text:answerText,cause,question_images:questionImages,answer_images:answerImages})});const imgCount=(result.images&&result.images.length)||0;const imgNote=imgCount?`，已保存 ${imgCount} 张图片`:'';document.getElementById('cr-result').innerHTML=`<div class="create-result ok">✓ <strong>${escapeHtml(result.uid)}</strong> 已创建${escapeHtml(imgNote)}<br>${escapeHtml(result.file_path)}${typeof boardQuickAdd==='function'?`<div class="create-result-acts"><button class="btn sm" type="button" data-board-hint onclick="boardQuickAdd(${jsArg(result.uid)},{anchor:this,direct:event.shiftKey})">📋 加入展示板</button><span class="hint">加入最近用过的板；没有板会先新建</span></div>`:''}</div>`;if(typeof crOnCreated==='function')crOnCreated();resetCreateForm();await reloadData()}catch(error){document.getElementById('cr-result').innerHTML=`<div class="create-result err">✕ ${escapeHtml(error.message)}</div>`}button.disabled=false;button.textContent='创建题目'}
async function doScan(){try{const result=await api('/api/scan');if(result.status==='ok'){uiToast(`扫描完成，共 ${result.count} 道题目`,{kind:'warn'});await reloadData();await refreshSessions()}else{uiToast(`扫描失败: ${result.msg||'未知错误'}`,{kind:'error'})}}catch(error){uiToast(`无法连接后端: ${error.message}`,{kind:'error'})}}
