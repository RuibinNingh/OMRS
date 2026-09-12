// === assets/instant.js — 即时练习：推荐取题、在线翻答案、即时反馈 ===
let INSTANT_SUBMITTING = false;
function instTimestamp(){const d=new Date();const p=n=>String(n).padStart(2,'0');return`${d.getFullYear()}${p(d.getMonth()+1)}${p(d.getDate())}${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}`}
function instBuildParams(count){const params=new URLSearchParams({due_count:String(count),prof_count:String(count)});const subject=document.getElementById('inst-subject')?.value||'';const category=document.getElementById('inst-category')?.value||'';const knowledgeTag=document.getElementById('inst-ktag')?.value||'';if(subject)params.set('subject',subject);if(category)params.set('category',category);if(knowledgeTag)params.set('knowledge_tag',knowledgeTag);if(typeof selectedLabelNamesFor==='function')selectedLabelNamesFor('inst').forEach(label=>params.append('label',label));return params}
function instFilterItems(items){const filters={...(typeof getFilterState==='function'?getFilterState('inst'):{})};filters.sort='none';return typeof filterItems==='function'?filterItems(items||[],filters):(items||[])}
function instMergeRecommendations(data,count){const rows=[];const seen=new Set();const add=(items,source)=>{(items||[]).forEach(item=>{if(!item?.uid||seen.has(item.uid))return;seen.add(item.uid);rows.push({...item,_source:source})})};add(data?.due,'due');add(data?.proficiency,'proficiency');return rows.slice(0,count)}
function instSourceLabel(source){return source==='due'?'到期':'熟练度'}
function instLabelsHtml(item,options={}){return typeof lblChips==='function'?lblChips(item?.labels||[],options):''}
function instQueueMeta(item){
  const masteryPct=(asNumber(item.mastery,0)*100).toFixed(0);
  const dueDays=getDueDays(item);
  const dueDate=item.due_date||'—';
  const labels=instLabelsHtml(item);
  return `熟练度 ${masteryPct}% · 到期 ${escapeHtml(dueDate)} ${formatDueInfo(dueDays)}${labels?' · ':''}${labels}`;
}
function instAnsweredCount(){return Object.values(INSTANT_RESULTS).filter(row=>row.correct===true||row.correct===false).length}
function instResult(uid){if(!INSTANT_RESULTS[uid])INSTANT_RESULTS[uid]={revealed:false,score:null,correct:null};return INSTANT_RESULTS[uid]}
function instCurrentItem(){return INSTANT_QUEUE[INSTANT_INDEX]||null}
function instInit(){instRenderSide();if(INSTANT_QUEUE.length)instRender()}

async function instLoadPractice(){
  const count=Math.floor(clampNumber(document.getElementById('inst-count')?.value,1,50,10));
  const status=document.getElementById('inst-status');
  if(status)status.textContent='加载中...';
  try{
    const data=await api(`/api/recommend?${instBuildParams(count).toString()}`);
    INSTANT_DATA=data;
    INSTANT_QUEUE=instMergeRecommendations({
      due:instFilterItems(data?.due),
      proficiency:instFilterItems(data?.proficiency),
    },count);
    INSTANT_INDEX=0;
    INSTANT_RESULTS={};
    INSTANT_SUBMITTING=false;
    INSTANT_SESSION_ID=`IMM-${instTimestamp()}`;
    document.getElementById('inst-submit-results').innerHTML='';
    if(!INSTANT_QUEUE.length){
      if(status)status.innerHTML='<span style="color:var(--yellow)">当前筛选下没有可练习题目</span>';
      instShowEmpty('没有符合当前筛选条件的题目。');
      instRenderSide();
      return;
    }
    if(status)status.innerHTML=`<span style="color:var(--green)">✓ 已载入 ${INSTANT_QUEUE.length} 道题</span>`;
    await ensureQuestionDetail(INSTANT_QUEUE[0].uid);
    instRender();
    instPreloadDetails();
  }catch(error){
    if(status)status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`;
  }
}

function instShowEmpty(message){
  const empty=document.getElementById('inst-empty');
  const review=document.getElementById('inst-review');
  if(empty){empty.style.display='block';empty.innerHTML=`<div class="icon">▶</div><p>${escapeHtml(message||'尚未开始')}</p>`}
  if(review){review.style.display='none';review.innerHTML=''}
}

async function instPreloadDetails(){
  const next=INSTANT_QUEUE.slice(Math.max(0,INSTANT_INDEX),INSTANT_INDEX+4);
  await Promise.all(next.map(item=>ensureQuestionDetail(item.uid)));
}

async function instGo(index){
  if(index<0||index>=INSTANT_QUEUE.length)return;
  INSTANT_INDEX=index;
  const item=instCurrentItem();
  if(item)await ensureQuestionDetail(item.uid);
  instRender();
  instPreloadDetails();
}
function instPrev(){instGo(INSTANT_INDEX-1)}
function instNext(){instGo(INSTANT_INDEX+1)}
function instReveal(){const item=instCurrentItem();if(!item)return;instResult(item.uid).revealed=true;instRender()}
function instSetVerdict(correct){const item=instCurrentItem();if(!item)return;const row=instResult(item.uid);row.revealed=true;row.correct=!!correct;if(row.score==null)row.score=correct?8:4;instRender()}
function instSetScore(value){const item=instCurrentItem();if(!item)return;const row=instResult(item.uid);row.score=Math.max(0,Math.min(10,Math.round(asNumber(value,5))));const val=document.getElementById('inst-score-val');if(val)val.textContent=row.score;instRenderSide()}
function instJumpNextOpen(){if(!INSTANT_QUEUE.length)return;for(let step=1;step<=INSTANT_QUEUE.length;step++){const i=(INSTANT_INDEX+step)%INSTANT_QUEUE.length;const uid=INSTANT_QUEUE[i].uid;const row=INSTANT_RESULTS[uid];if(!row||!(row.correct===true||row.correct===false)){instGo(i);return}}}

function instRender(){
  const item=instCurrentItem();
  if(!item){instShowEmpty('尚未开始');return}
  const q=QUESTION_CACHE[item.uid];
  if(!q){document.getElementById('inst-review').innerHTML='<div class="empty-inline">加载题目中...</div>';return}
  const row=instResult(item.uid);
  const score=row.score==null?5:row.score;
  const ktags=(q.knowledge_tags||item.knowledge_tags||[]).map(tag=>`<span class="tag" style="background:var(--accent-bg);color:var(--accent2)">${escapeHtml(tag)}</span>`).join('');
  const labels=instLabelsHtml({...item,labels:q.labels||item.labels||[]});
  const masteryPct=(asNumber(item.mastery,0)*100).toFixed(0);
  const grading=row.revealed?`<div class="instant-grade">
    <div class="fb-toggle">
      <span class="${row.correct===true?'active-correct':''}" onclick="instSetVerdict(true)">✓ 对</span>
      <span class="${row.correct===false?'active-wrong':''}" onclick="instSetVerdict(false)">✗ 错</span>
    </div>
    <div class="instant-score">
      <span>主观分</span>
      <input type="range" min="0" max="10" value="${score}" oninput="instSetScore(this.value)">
      <strong id="inst-score-val">${score}</strong>
    </div>
  </div>`:'';
  document.getElementById('inst-empty').style.display='none';
  const review=document.getElementById('inst-review');
  review.style.display='block';
  review.innerHTML=`<div class="instant-head">
    <div class="instant-headl">
      <div class="instant-pos">题 ${INSTANT_INDEX+1} / ${INSTANT_QUEUE.length}</div>
      <div class="instant-uid">${escapeHtml(item.uid)} <span class="tag ${item._source==='due'?'attack':'trap'}">${instSourceLabel(item._source)}</span></div>
    </div>
    <div class="instant-chips">
      <span class="chip">${escapeHtml(item.subject||q.subject||'')}</span>
      <span class="chip">${escapeHtml(item.category||q.category||'')}</span>
      <span class="chip">难度 ${escapeHtml(item.difficulty||q.difficulty||'?')}</span>
      <span class="chip">熟练度 ${masteryPct}%</span>
    </div>
  </div>
  <div class="instant-prog"><div style="width:${Math.round((INSTANT_INDEX+1)/Math.max(1,INSTANT_QUEUE.length)*100)}%"></div></div>
  ${labels||ktags?`<div class="instant-tagrow">${labels}${ktags}</div>`:''}
  <div class="instant-block" id="inst-qv"></div>
  ${grading}
  <div class="instant-nav">
    <button class="btn" onclick="instPrev()" ${INSTANT_INDEX<=0?'disabled':''}>上一题</button>
    <button class="btn" onclick="instJumpNextOpen()">下一道未判定</button>
    <button class="btn" onclick="instNext()" ${INSTANT_INDEX>=INSTANT_QUEUE.length-1?'disabled':''}>下一题</button>
  </div>`;
  // 题面 / 答案 / 备注交给共享的 qview 组件，与题目 Modal、反馈工作台同一份渲染
  qvRender('#inst-qv',item.uid,{layout:'split',reveal:row.revealed,showHistory:false,actions:['edit','board','labels'],onReveal:instReveal});
  instRenderSide();
}

function instRenderSide(){
  const summary=document.getElementById('inst-summary');
  const queue=document.getElementById('inst-queue');
  if(!summary||!queue)return;
  const answered=instAnsweredCount();
  summary.innerHTML=INSTANT_QUEUE.length
    ? `<div>已判定 ${answered} / ${INSTANT_QUEUE.length}</div><div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap"><button class="btn sm primary" id="inst-submit" onclick="instSubmitPractice()" ${answered&&!INSTANT_SUBMITTING?'':'disabled'}>提交已判定</button><button class="btn sm" onclick="instJumpNextOpen()" ${answered===INSTANT_QUEUE.length?'disabled':''}>未判定</button></div>`
    : '尚未加载';
  queue.innerHTML=INSTANT_QUEUE.map((item,index)=>{
    const row=INSTANT_RESULTS[item.uid];
    const answeredRow=row&&(row.correct===true||row.correct===false);
    const cls=['instant-qbtn',index===INSTANT_INDEX?'active':'',answeredRow?(row.correct?'correct':'wrong'):''].filter(Boolean).join(' ');
    const mk=index===INSTANT_INDEX?'<span class="qmk cur"></span>':(answeredRow?(row.correct?'<span class="qmk ok">✓</span>':'<span class="qmk no">✗</span>'):'<span class="qmk up"></span>');
    return `<button class="${cls}" onclick="instGo(${index})"><span class="qn">${index+1}</span><div class="instant-qmain"><strong>${escapeHtml(item.uid)}</strong><small>${instQueueMeta(item)}</small></div>${mk}</button>`;
  }).join('');
}

async function instSubmitPractice(){
  if(INSTANT_SUBMITTING)return;
  const itemMap={};INSTANT_QUEUE.forEach(item=>{itemMap[item.uid]=item});
  const rows=Object.entries(INSTANT_RESULTS)
    .filter(([,row])=>row.correct===true||row.correct===false)
    .map(([uid,row])=>({uid,sub_score:row.score==null?(row.correct?8:4):row.score,is_correct:row.correct,source:itemMap[uid]?._source||'due',note:'即时练习'}));
  if(!rows.length){uiToast('还没有已判定题目',{kind:'warn'});return}
  INSTANT_SUBMITTING=true;
  const button=document.getElementById('inst-submit');
  const status=document.getElementById('inst-status');
  if(button)button.disabled=true;
  if(status)status.textContent='提交中...';
  try{
    const result=await api('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feedbacks:rows,session_id:INSTANT_SESSION_ID||`IMM-${instTimestamp()}`})});
    INSTANT_RESULTS={};
    if(status)status.innerHTML=`<span style="color:var(--green)">✓ 已提交 ${rows.length} 条反馈</span>`;
    document.getElementById('inst-submit-results').innerHTML='<div class="card-title" style="margin-top:14px">提交结果</div>'+(result.results||[]).map(row=>{
      const ok=row.status==='ok';
      const labelClass=row.label==='已击杀'?'kill':row.label==='真不会'?'attack':'trap';
      const summary=ok?`${(asNumber(row.old_mastery,0)*100).toFixed(0)}% → ${(asNumber(row.new_mastery,0)*100).toFixed(0)}%`:escapeHtml(row.msg||'失败');
      return `<div class="result-row ${ok?'ok':'err'}"><span style="font-weight:700;color:var(--accent2)">${escapeHtml(row.uid)}</span><span class="tag ${labelClass}">${escapeHtml(row.label||'')}</span><span style="font-family:'JetBrains Mono',monospace;font-size:.76rem">${summary}</span></div>`;
    }).join('');
    await reloadData();
    if(typeof qvInvalidateMany==='function')await qvInvalidateMany(rows.map(row=>row.uid));
    instRenderSide();
  }catch(error){
    if(status)status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`;
    if(button)button.disabled=false;
  }finally{
    INSTANT_SUBMITTING=false;
  }
}
