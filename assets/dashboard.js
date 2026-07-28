// === assets/dashboard.js: 仪表盘图表 renderDash + 最近动态 ===
function dashClamp(value,min,max){return Math.max(min,Math.min(max,value))}
function dashValue(value){return asNumber(value,0)}
function dashPct(value,max){return dashClamp(dashValue(value)/Math.max(1,dashValue(max))*100,0,100)}
function dashDateKey(date){const y=date.getFullYear();const m=String(date.getMonth()+1).padStart(2,'0');const d=String(date.getDate()).padStart(2,'0');return`${y}-${m}-${d}`}
function dashEmpty(text='暂无数据'){return`<div class="empty"><p>${escapeHtml(text)}</p></div>`}
function dashBarRows(rows,{mode='plain'}={}){
  if(!rows.length)return dashEmpty();
  return`<div class="chart-bars ${mode==='compact'?'compact':''}">`+rows.map(row=>`<div class="chart-row ${row.tone||''}">
    <div class="chart-row-head">
      <span class="chart-name">${escapeHtml(row.label)}</span>
      <span class="chart-meta">${escapeHtml(row.meta||'')}</span>
      <span class="chart-value">${escapeHtml(row.value)}</span>
    </div>
    <div class="chart-track"><div class="chart-fill ${row.fill||'accent'}" style="width:${dashClamp(row.pct,0,100)}%"></div></div>
  </div>`).join('')+`</div>`;
}
function dashSmoothPoints(points){
  if(!points.length)return'';
  if(points.length===1)return`M ${points[0].x} ${points[0].y}`;
  let path=`M ${points[0].x} ${points[0].y}`;
  for(let i=1;i<points.length;i+=1){
    const prev=points[i-1],cur=points[i];
    const midX=(prev.x+cur.x)/2;
    path+=` C ${midX} ${prev.y}, ${midX} ${cur.y}, ${cur.x} ${cur.y}`;
  }
  return path;
}
function recentLedgerRow(row,rs){
  const fam=(typeof historyCommitFamily==='function')?historyCommitFamily(row.commit_type):'system';
  const dt=formatLedgerTime(row.created_at).slice(0,16);
  const title=(typeof historyNodeTitle==='function')?historyNodeTitle(row,rs):(row.summary||row.commit_type);
  let chip='';
  if(row.commit_type==='review.batch_submit'&&typeof historyReviewBatchStats==='function'){
    const s=historyReviewBatchStats(row,rs);
    chip=`<span class="recent-chip">${s.correct} 对 · ${s.wrong} 错</span>`;
  }
  return`<div class="recent-row"><span class="recent-dot fam-${fam}"></span><div class="recent-mid"><div class="recent-title">${escapeHtml(title)}</div><div class="recent-meta">${escapeHtml(row.commit_id||'')} · seq ${escapeHtml(row.seq)}</div></div>${chip}<span class="recent-time">${escapeHtml(dt||'GENESIS')}</span></div>`;
}
async function renderRecentLedger(){
  const box=document.getElementById('recent-ledger');if(!box)return;
  let commits=window.HISTORY_COMMITS,rs=window.HISTORY_RETRACTION_STATE;
  try{
    if(!commits||!commits.length){
      const r=await api('/api/history?limit=12');
      commits=r.commits||[];
      rs=r.retraction_state||null;
    }
  }catch(e){
    box.innerHTML='<div class="empty-inline">暂无动态（需要后端运行）</div>';
    return;
  }
  if(!commits||!commits.length){box.innerHTML='<div class="empty-inline">暂无动态</div>';return}
  const state=(typeof normalizeHistoryRetractionState==='function'&&normalizeHistoryRetractionState(rs))||(typeof historyRetractionState==='function'?historyRetractionState(commits):{retractedSessions:new Set(),retractedReviews:new Set()});
  const rows=[...commits].sort((a,b)=>asNumber(b.seq,0)-asNumber(a.seq,0)).filter(r=>{
    const corr=(typeof isHistoryCorrection==='function')?isHistoryCorrection(r):false;
    const retr=(typeof isNodeRetracted==='function')?isNodeRetracted(r,state):false;
    return !corr&&!retr;
  }).slice(0,4);
  box.innerHTML=rows.length?rows.map(r=>recentLedgerRow(r,state)).join(''):'<div class="empty-inline">暂无动态</div>';
}
function renderActivityHeatmap(activity){
  const el=document.getElementById('chart-activity');if(!el)return;
  const days=[];const today=new Date();
  for(let i=29;i>=0;i-=1){
    const dt=new Date(today);
    dt.setDate(dt.getDate()-i);
    const key=dashDateKey(dt);
    days.push({key,day:dt.getDate(),weekday:'日一二三四五六'[dt.getDay()],count:dashValue((activity||{})[key])});
  }
  const max=Math.max(1,...days.map(d=>d.count));
  const total=days.reduce((sum,d)=>sum+d.count,0);
  const active=days.filter(d=>d.count>0).length;
  const peak=days.reduce((best,d)=>d.count>best.count?d:best,days[0]||{count:0,key:''});
  const cells=days.map(d=>{
    const level=d.count?Math.max(1,Math.ceil(d.count/max*4)):0;
    return`<div class="activity-cell heat-${level}" title="${escapeAttr(d.key)}：${d.count} 次" aria-label="${escapeAttr(d.key)} ${d.count} 次"><span>${d.day}</span><small>${escapeHtml(d.weekday)}</small></div>`;
  }).join('');
  el.innerHTML=`<div class="activity-shell">
    <div class="activity-stats">
      <span><strong>${total}</strong> 次复习</span>
      <span><strong>${active}</strong> 天活跃</span>
      <span><strong>${peak.count}</strong> 单日峰值</span>
    </div>
    <div class="activity-heatmap">${cells}</div>
    <div class="activity-legend"><span>少</span><i class="heat-0"></i><i class="heat-1"></i><i class="heat-2"></i><i class="heat-3"></i><i class="heat-4"></i><span>多</span></div>
  </div>`;
}
function renderSubjectChart(subjectDist){
  const el=document.getElementById('chart-subjects');if(!el)return;
  const entries=Object.entries(subjectDist||{}).sort((a,b)=>dashValue(b[1]?.total)-dashValue(a[1]?.total));
  if(!entries.length){el.innerHTML=dashEmpty();return}
  const max=Math.max(1,...entries.map(([,value])=>dashValue(value.total)));
  el.innerHTML='<div class="subject-bars">'+entries.map(([name,value])=>{
    const total=dashValue(value.total),killed=dashValue(value.killed),killPct=total?killed/total*100:0,totalPct=dashPct(total,max);
    return`<div class="subject-row">
      <div class="subject-head"><span>${escapeHtml(name)}</span><strong>${total}</strong></div>
      <div class="subject-track">
        <div class="subject-total" style="width:${totalPct}%"></div>
        <div class="subject-killed" style="width:${dashClamp(killPct,0,100)}%"></div>
      </div>
      <div class="subject-foot"><span>已击杀 ${killed}</span><span>${killPct.toFixed(0)}%</span></div>
    </div>`;
  }).join('')+'</div>';
}
function renderMasteryChart(histogram){
  const el=document.getElementById('chart-mastery');if(!el)return;
  const mh=histogram||{};const keys=['0-10','10-20','20-30','30-40','40-50','50-60','60-70','70-80','80-90','90-100'];
  const max=Math.max(1,...keys.map(k=>dashValue(mh[k])));
  if(!Object.keys(mh).length){el.innerHTML=dashEmpty();return}
  el.innerHTML=dashBarRows(keys.map((key,idx)=>{
    const count=dashValue(mh[key]);
    return{label:`${key}%`,meta:idx<3?'危险':idx<6?'拉升':idx<8?'稳定':'掌握',value:String(count),pct:dashPct(count,max),fill:idx<3?'red':idx<6?'yellow':idx<8?'blue':'green'};
  }),{mode:'compact'});
}
function renderDifficultyChart(dist){
  const el=document.getElementById('chart-diff');if(!el)return;
  const values=Array.from({length:10},(_,i)=>dashValue((dist||{})[String(i+1)]));
  const max=Math.max(1,...values);
  el.innerHTML=`<div class="level-bars">`+values.map((count,idx)=>{
    const level=idx+1;
    const tone=level<=3?'easy':level<=6?'mid':level<=8?'hard':'risk';
    return`<div class="level-bar ${tone}" title="Lv.${level}：${count} 题">
      ${count>0?`<div class="level-fill" style="height:${dashPct(count,max)}%"></div>`:''}
      <span>${level}</span>
      <b>${count}</b>
    </div>`;
  }).join('')+`</div>`;
}
function renderAlertCards(alertData){
  const el=document.getElementById('chart-alerts');if(!el)return;
  const data=alertData||{};
  const alerts=[
    {label:'今日到期',val:data.due_today||0,desc:'按复习间隔排到今天的卡片数',tone:'danger'},
    {label:'未来3天到期',val:data.due_next_3_days||0,desc:'明天起 3 天内到期的卡片数',tone:'warning'},
    {label:'未来7天到期',val:data.due_next_7_days||0,desc:'明天起 7 天内到期的卡片数',tone:'cool'},
    {label:'未到期低熟练度',val:data.low_mastery_not_due||0,desc:'未到期但仍建议复习的低熟练度卡片数',tone:'accent'},
  ];
  el.innerHTML=`<div class="alert-grid">`+alerts.map(a=>`<div class="alert-card ${a.tone}">
    <div><span>${escapeHtml(a.label)}</span><p>${escapeHtml(a.desc)}</p></div>
    <strong>${escapeHtml(a.val)}</strong>
  </div>`).join('')+`</div>`;
}
function renderTrendChart(trend){
  const el=document.getElementById('chart-trend');if(!el)return;
  const data=trend||{};const dates=Object.keys(data).sort();
  if(!dates.length){el.innerHTML=dashEmpty();return}
  const max=Math.max(1,...Object.values(data).map(dashValue));
  const total=Object.values(data).reduce((sum,v)=>sum+dashValue(v),0);
  const last=dashValue(data[dates[dates.length-1]]);
  const w=680,h=286,padL=44,padR=18,padT=18,padB=38,baseY=h-padB,plotH=h-padT-padB,plotW=w-padL-padR;
  const pts=dates.map((dt,i)=>{const x=padL+(i/(dates.length-1||1))*plotW;const y=baseY-(dashValue(data[dt])/max)*plotH;return{dt,value:dashValue(data[dt]),x,y}});
  const linePath=dashSmoothPoints(pts);
  const areaPath=pts.length?`${linePath} L ${pts[pts.length-1].x} ${baseY} L ${pts[0].x} ${baseY} Z`:'';
  const grid=Array.from({length:5},(_,i)=>{const y=baseY-(i/4)*plotH;const val=Math.round(max*i/4);return`<line x1="${padL}" y1="${y}" x2="${w-padR}" y2="${y}" class="chart-grid-line"/><text x="${padL-10}" y="${y+4}" class="chart-axis" text-anchor="end">${val}</text>`}).join('');
  const labels=pts.filter((_,i)=>i===0||i===pts.length-1||i===Math.floor(pts.length/2)).map(pt=>`<text x="${pt.x}" y="${h-12}" class="chart-axis" text-anchor="${pt.x===padL?'start':pt.x===w-padR?'end':'middle'}">${pt.dt.slice(5)}</text>`).join('');
  const markers=pts.filter(pt=>pt.value>0).map(pt=>`<circle cx="${pt.x}" cy="${pt.y}" r="${pt.value===max?5:3.5}" class="${pt.value===max?'trend-peak':'trend-dot'}"><title>${escapeHtml(pt.dt)}：${pt.value} 次</title></circle>`).join('');
  el.innerHTML=`<div class="trend-shell">
    <div class="trend-summary"><span><strong>${total}</strong> 近 30 天</span><span><strong>${last}</strong> 最近一天</span><span><strong>${max}</strong> 单日最高</span></div>
    <svg viewBox="0 0 ${w} ${h}" class="trend-svg" role="img" aria-label="每日练习趋势">
      <defs><linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="var(--blue)" stop-opacity=".34"/><stop offset="100%" stop-color="var(--blue)" stop-opacity=".02"/></linearGradient></defs>
      ${grid}<path d="${areaPath}" class="trend-area"/><path d="${linePath}" class="trend-line"/>${markers}<line x1="${padL}" y1="${baseY}" x2="${w-padR}" y2="${baseY}" class="chart-axis-line"/>${labels}
    </svg>
  </div>`;
}
function renderDash(){
  const d=DATA;
  document.getElementById('s-total').textContent=d.total;
  document.getElementById('s-killed').textContent=d.killed;
  document.getElementById('s-kill-pct').textContent=d.total?`${(d.killed/d.total*100).toFixed(0)}% 击杀率`:'';
  document.getElementById('s-attack').textContent=d.attacking;
  document.getElementById('s-avgm').textContent=`${(d.avg_mastery*100).toFixed(0)}%`;
  renderSubjectChart(d.subject_dist);
  renderActivityHeatmap(d.recent_activity);
  renderAlertCards(d.review_alert);
  renderTrendChart(d.daily_trend);
  renderMasteryChart(d.mastery_histogram);
  renderDifficultyChart(d.difficulty_dist);
  renderRecentLedger();
}
