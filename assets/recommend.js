// === assets/recommend.js — 推荐面板（双列表 + 勾选确认） ===
/* ══════════════════════════════════════════════════════════
   推荐面板（Phase 3）
   ══════════════════════════════════════════════════════════ */
function showRecommendPanel(){
  document.getElementById('recommend-panel').style.display='block';
  document.getElementById('export-panel').style.display='none';
  document.getElementById('btn-regular-review').classList.add('primary');
  document.getElementById('btn-export').classList.remove('primary');
  loadRecommendations();
}
function showExportPanel(){
  document.getElementById('recommend-panel').style.display='none';
  document.getElementById('export-panel').style.display='block';
  document.getElementById('btn-regular-review').classList.remove('primary');
  document.getElementById('btn-export').classList.add('primary');
  renderExportPicker();
}
function isRecSelected(uid){return !!REC_SELECTED[uid]}
function getRecSelectedCount(){return Object.keys(REC_SELECTED).length}
function getRecSelectedUids(){return Object.keys(REC_SELECTED).map(uid=>({uid,source:REC_SELECTED[uid]}))}
function estimateTime(count){return count<3?count*10+'分钟':count<7?count*8+'分钟':count+'题,约'+(count*8)+'分钟'}

function normalizeRecItem(item){if(!item)return item;if(item.due_date)return item;const od=item._overdue_days;if(od==null)return item;const d=new Date();d.setDate(d.getDate()-od);return{...item,due_date:d.toISOString().slice(0,10)}}
function applyRecFilters(items,filters){return filterItems(items.map(normalizeRecItem),filters)}
function getFilteredRecData(){if(!REC_DATA)return{due:[],proficiency:[]};const filters=getFilterState('rec');return{due:applyRecFilters(REC_DATA.due||[],filters),proficiency:applyRecFilters(REC_DATA.proficiency||[],filters)}}

async function loadRecommendations(){
  const subject=document.getElementById('rec-subject').value||'';
  const dueCount=Math.max(1,Math.min(50,asNumber(document.getElementById('rec-due-count').value,10)));
  const profCount=Math.max(1,Math.min(50,asNumber(document.getElementById('rec-prof-count').value,10)));
  const status=document.getElementById('rec-status');
  status.textContent='加载中...';
  try{
    REC_DATA=await api(`/api/recommend?due_count=${dueCount}&prof_count=${profCount}${subject?`&subject=${encodeURIComponent(subject)}`:''}`);
    REC_SELECTED={};
    renderDualLists();
    updateRecSelectionBar();
    status.textContent='✓';
  }catch(e){
    status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`;
  }
}

function setRecView(view){
  REC_VIEW=view;
  document.getElementById('rec-view-flat').classList.toggle('active',view==='flat');
  document.getElementById('rec-view-gallery').classList.toggle('active',view==='gallery');
  renderDualLists();
}

function renderDualLists(){
  if(!REC_DATA) return;
  const filtered=getFilteredRecData();
  const due=filtered.due;
  const prof=filtered.proficiency;
  document.getElementById('rec-due-label').textContent=`(${due.length} 道)`;
  document.getElementById('rec-prof-label').textContent=`(${prof.length} 道)`;
  if(REC_VIEW==='gallery'){
    document.getElementById('rec-due-list').innerHTML=due.length
      ? renderRecGalleryList(due,'due')
      : '<div class="empty-inline">暂无到期题目 ✓</div>';
    document.getElementById('rec-prof-list').innerHTML=prof.length
      ? renderRecGalleryList(prof,'proficiency')
      : '<div class="empty-inline">所有未到期题目已列入熟练度</div>';
    hydrateRecGalleryPreviews();
  }else{
    document.getElementById('rec-due-list').innerHTML=due.length
      ? due.map(item=>renderRecItem(item,'due')).join('')
      : '<div class="empty-inline">暂无到期题目 ✓</div>';
    document.getElementById('rec-prof-list').innerHTML=prof.length
      ? prof.map(item=>renderRecItem(item,'proficiency')).join('')
      : '<div class="empty-inline">所有未到期题目已列入熟练度</div>';
  }
}

function renderRecGalleryList(items,source){
  return `<div class="gallery-grid">${items.map(item=>{
    const selected=isRecSelected(item.uid);
    const masteryPct=(asNumber(item.mastery,0)*100).toFixed(0);
    const masteryColor=asNumber(item.mastery,0)>.8?'var(--green)':asNumber(item.mastery,0)>.4?'var(--yellow)':'var(--red)';
    const dueDays=item._overdue_days;
    const dueBadge=source==='due'&&dueDays!=null
      ? (dueDays>0?`<span class="due-badge overdue">逾期${dueDays}天</span>`:dueDays===0?`<span class="due-badge today">今日到期</span>`:'')
      : '';
    const detail=QUESTION_CACHE[item.uid];
    const previewHtml=detail?renderMdContent(detail.question||'（无题目内容）'):'<div class="preview-placeholder">正在加载题目预览…</div>';
    const ef=asNumber(item.ef,2.5).toFixed(2);
    const tagLabel=(item.tag||'').replace(/#/g,'');
    return `<div class="gallery-card ${selected?'selected':''}">
      <div class="gallery-head">
        <div><div class="uid">${escapeHtml(item.uid)} ${dueBadge}</div>
        <div class="gallery-meta">${escapeHtml(item.subject||'')} · ${escapeHtml(item.category||'')}<br>难度 ${escapeHtml(item.difficulty)} · EF ${ef} · 来源: ${source==='due'?'到期':'熟练度'}</div></div>
        <span class="tag ${(item.tag||'').includes('已击杀')?'kill':'attack'}">${escapeHtml(tagLabel)}</span>
      </div>
      <div class="question-progress-row"><div class="question-progress-main"><span>熟练度</span><span class="m-bar"><span class="m-bar-fill" style="width:${masteryPct}%;background:${masteryColor}"></span></span><span>${masteryPct}%</span></div></div>
      <div class="gallery-preview" data-rec-preview-uid="${escapeAttr(item.uid)}">${previewHtml}</div>
      <div style="display:flex;justify-content:space-between;align-items:center">
        <button class="btn sm" onclick="viewQ('${escapeAttr(item.uid)}')">查看详情</button>
        <button class="btn sm ${selected?'danger':''}" onclick="toggleRecSelection('${escapeAttr(item.uid)}','${source}')">${selected?'移除':'勾选'}</button>
      </div>
    </div>`;
  }).join('')}</div>`;
}

async function hydrateRecGalleryPreviews(){
  const nodes=[...document.querySelectorAll('.gallery-preview[data-rec-preview-uid]')];
  await Promise.all(nodes.map(async node=>{
    const uid=node.dataset.recPreviewUid;
    if(!uid)return;
    const detail=await ensureQuestionDetail(uid);
    if(node.dataset.recPreviewUid===uid){
      node.innerHTML=renderMdContent(detail.question||'（无题目内容）');
    }
  }));
}

function renderRecItem(item,source){
  const selected=isRecSelected(item.uid);
  const masteryPct=(asNumber(item.mastery,0)*100).toFixed(0);
  const difficulty=item.difficulty||'?';
  const ef=asNumber(item.ef,2.5).toFixed(2);
  const overdueDays=item._overdue_days;
  let dueBadge='';
  if(source==='due' && overdueDays!=null){
    if(overdueDays>0) dueBadge='<span class="due-badge overdue">逾期'+overdueDays+'天</span>';
    else if(overdueDays===0) dueBadge='<span class="due-badge today">今日到期</span>';
  }
  const masteryColor=asNumber(item.mastery,0)>.8?'var(--green)':asNumber(item.mastery,0)>.4?'var(--yellow)':'var(--red)';
  const estTime=Math.max(3,Math.round(difficulty*1.5))+'分钟';
  const tagLabel=(item.tag||'').replace(/#/g,'');
  return `<div class="rec-item ${selected?'selected':''}" onclick="toggleRecSelection('${escapeAttr(item.uid)}','${source}')">
    <input type="checkbox" ${selected?'checked':''} onclick="event.stopPropagation();toggleRecSelection('${escapeAttr(item.uid)}','${source}')">
    <div class="rec-item-body">
      <div class="uid">${escapeHtml(item.uid)} ${dueBadge}</div>
      <div class="meta">${escapeHtml(item.subject||'')} · ${escapeHtml(item.category||'')} · EF ${ef} · <span class="tag ${(item.tag||'').includes('已击杀')?'kill':'attack'}">${escapeHtml(tagLabel)}</span></div>
    </div>
    <div class="rec-item-right">
      <div><span class="m-bar"><span class="m-bar-fill" style="width:${masteryPct}%;background:${masteryColor}"></span></span> ${masteryPct}%</div>
      <div class="difficulty">难度 ${difficulty}</div>
      <div class="est-time">预计 ${estTime}</div>
    </div>
  </div>`;
}

function toggleRecSelection(uid,source){
  if(REC_SELECTED[uid]){delete REC_SELECTED[uid]}
  else{REC_SELECTED[uid]=source}
  renderDualLists();
  updateRecSelectionBar();
}

function clearRecommendSelection(){
  REC_SELECTED={};
  renderDualLists();
  updateRecSelectionBar();
  document.getElementById('rec-preview-panel').style.display='none';
}

function updateRecSelectionBar(){
  const count=getRecSelectedCount();
  const bar=document.getElementById('rec-selection-bar');
  bar.style.display=count>0?'block':'none';
  document.getElementById('rec-selected-count').textContent=`已选: ${count} 道`;
  document.getElementById('rec-est-time').textContent=`预计耗时: ${estimateTime(count)}`;
}

function smartConfirm(){
  const filtered=getFilteredRecData();
  if(!filtered.due.length){alert('暂无到期题目');return}
  const count=asNumber(document.getElementById('rec-due-count').value,10);
  REC_SELECTED={};
  filtered.due.slice(0,count).forEach(item=>{REC_SELECTED[item.uid]='due'});
  renderDualLists();
  updateRecSelectionBar();
}

function previewSelection(){
  const selected=getRecSelectedUids();
  if(!selected.length){alert('请先勾选题目');return}
  const panel=document.getElementById('rec-preview-panel');
  const allItems=[...(REC_DATA?.due||[]),...(REC_DATA?.proficiency||[])];
  const itemMap={};allItems.forEach(item=>{itemMap[item.uid]=item});
  const items=selected.map(s=>{const item=itemMap[s.uid];return item?{...item,_source:s.source}:null}).filter(Boolean);
  const totalTime=items.reduce((sum,item)=>sum+Math.max(3,Math.round(asNumber(item.difficulty,5)*1.5)),0);
  const dueCount=items.filter(item=>item._source==='due').length;
  const profCount=items.filter(item=>item._source==='proficiency').length;

  let html=`<div class="preview-card">
    <div class="card-title">计划预览（共 ${items.length} 道）</div>
    <div class="filter-note">总计预计耗时: ${totalTime} 分钟 · 来自到期列表: ${dueCount} 道 | 来自熟练度列表: ${profCount} 道</div>
    <div class="view-switch" style="margin:10px 0">
      <button class="btn sm toggle" id="pv-list" onclick="setPreviewView('list')">列表视图</button>
      <button class="btn sm toggle" id="pv-card" onclick="setPreviewView('card')">卡片视图</button>
      <button class="btn sm toggle" id="pv-group" onclick="setPreviewView('group')">分组视图</button>
      <button class="btn sm toggle" id="pv-time" onclick="setPreviewView('time')">时间视图</button>
    </div>
    <div id="rec-preview-content"></div>
  </div>`;
  panel.style.display='block';
  panel.innerHTML=html;
  REC_PREVIEW_ITEMS=items;
  setPreviewView('list');
}
let REC_PREVIEW_ITEMS=[];

function setPreviewView(mode){
  REC_PREVIEW_MODE=mode;
  ['pv-list','pv-card','pv-group','pv-time'].forEach(id=>{
    const el=document.getElementById(id);if(el)el.classList.toggle('active',id===`pv-${mode}`);
  });
  const content=document.getElementById('rec-preview-content');
  if(!content)return;
  const items=REC_PREVIEW_ITEMS||[];
  switch(mode){
    case 'list': content.innerHTML=renderPreviewList(items);break;
    case 'card': content.innerHTML=renderPreviewCards(items);break;
    case 'group': content.innerHTML=renderPreviewGroups(items);break;
    case 'time': content.innerHTML=renderPreviewTime(items);break;
  }
}

function renderPreviewList(items){
  return items.map((item,i)=>{
    const sourceLabel=item._source==='due'?'<span class="due-badge overdue">到期</span>':'<span class="due-badge today">熟练度</span>';
    const estTime=Math.max(3,Math.round(asNumber(item.difficulty,5)*1.5));
    return `<div class="sched-item">
      <div><div class="uid">${i+1}. ${escapeHtml(item.uid)} ${sourceLabel}</div>
      <div class="meta-line">${escapeHtml(item.subject||'')} · ${escapeHtml(item.category||'')} · 难度 ${escapeHtml(item.difficulty)} · 预计 ${estTime} 分钟</div></div>
      <div class="priority">M=${(asNumber(item.mastery,0)*100).toFixed(0)}%</div>
    </div>`;
  }).join('');
}

function renderPreviewCards(items){
  return `<div class="gallery-grid">${items.map(item=>{
    const sourceLabel=item._source==='due'?'到期':'熟练度';
    const masteryPct=(asNumber(item.mastery,0)*100).toFixed(0);
    return `<div class="gallery-card">
      <div class="gallery-head"><div><div class="uid">${escapeHtml(item.uid)}</div>
      <div class="gallery-meta">${escapeHtml(item.subject||'')} · ${escapeHtml(item.category||'')}<br>难度 ${escapeHtml(item.difficulty)} · 来源: ${sourceLabel}</div></div>
      <span class="tag ${(item.tag||'').includes('已击杀')?'kill':'attack'}">${escapeHtml((item.tag||'').replace(/#/g,''))}</span></div>
      <div class="question-progress-row"><span>熟练度 ${masteryPct}%</span></div>
      <button class="btn sm" onclick="viewQ('${escapeAttr(item.uid)}')">查看详情</button>
    </div>`;
  }).join('')}</div>`;
}

function renderPreviewGroups(items){
  const grouped={};
  items.forEach(item=>{
    const key=item.subject||'未知';
    if(!grouped[key])grouped[key]=[];
    grouped[key].push(item);
  });
  return Object.entries(grouped).map(([subject,group])=>{
    const estTime=group.reduce((sum,item)=>sum+Math.max(3,Math.round(asNumber(item.difficulty,5)*1.5)),0);
    return `<div class="preview-group-header">${escapeHtml(subject)} (${group.length} 道, 约 ${estTime} 分钟)</div>
    ${group.map((item,i)=>
      `<div class="sched-item"><div><div class="uid">${i+1}. ${escapeHtml(item.uid)}</div>
      <div class="meta-line">${escapeHtml(item.category||'')} · 难度 ${escapeHtml(item.difficulty)} · 来源: ${item._source==='due'?'到期':'熟练度'}</div></div>
      <div class="priority">M=${(asNumber(item.mastery,0)*100).toFixed(0)}%</div></div>`
    ).join('')}`;
  }).join('');
}

function renderPreviewTime(items){
  const sorted=[...items].sort((a,b)=>asNumber(a.difficulty,5)-asNumber(b.difficulty,5));
  return sorted.map((item,i)=>{
    const estTime=Math.max(3,Math.round(asNumber(item.difficulty,5)*1.5));
    return `<div class="sched-item">
      <div><div class="uid">${i+1}. ${escapeHtml(item.uid)}</div>
      <div class="meta-line">${escapeHtml(item.subject||'')} · ${escapeHtml(item.category||'')} · 难度 ${escapeHtml(item.difficulty)} · 预计 ${estTime} 分钟</div></div>
      <div class="priority">${estTime}分</div>
    </div>`;
  }).join('');
}

async function confirmSchedule(){
  const selected=getRecSelectedUids();
  if(!selected.length){alert('请至少勾选 1 道题');return}
  const status=document.getElementById('rec-status');
  status.textContent='生成中...';
  try{
    const result=await api('/api/confirm-schedule',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({selected,subject:document.getElementById('rec-subject').value||null})
    });
    if(result.session_type==='tmp'){
      status.innerHTML=`<span style="color:var(--yellow)">✓ 自定义练习 ${escapeHtml(result.session_id)} (${result.count} 题) — 不写入 sessions.csv</span>`;
    }else{
      status.innerHTML=`<span style="color:var(--green)">✓ 常规 Session ${escapeHtml(result.session_id)} (${result.count} 题) 已创建</span>`;
    }
    REC_SELECTED={};
    renderDualLists();
    updateRecSelectionBar();
    document.getElementById('rec-preview-panel').style.display='none';
    await refreshSessions();
    if(result.items)previewSession(result.session_id,result.items);
  }catch(e){
    status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`;
  }
}


/* ══════════════════════════════════════════════════════════
   End 推荐面板
   ══════════════════════════════════════════════════════════ */
