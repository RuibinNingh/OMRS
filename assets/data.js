// === assets/data.js — 数据复盘页 + 复盘报告导出 ===
/* ══════════════════════════════════════════════════════════
   数据页（复盘）
   ══════════════════════════════════════════════════════════ */
let ANALYTICS=null;
function pctFmt(v){return v===null||v===undefined?'—':`${(v*100).toFixed(0)}%`}
function _kpiCard(cls,label,value,sub){return `<div class="stat-card ${cls}"><div class="stat-label">${escapeHtml(label)}</div><div class="stat-value">${escapeHtml(value)}</div>${sub?`<div class="stat-sub">${escapeHtml(sub)}</div>`:''}</div>`}
function _bars(id,rows){const el=document.getElementById(id);if(!el)return;if(!rows.length){el.innerHTML='<div class="empty"><p>暂无数据</p></div>';return}const mx=Math.max(1,...rows.map(r=>asNumber(r.value,0)));el.innerHTML=rows.map(r=>`<div class="bar-row"><div class="bar-label">${escapeHtml(r.label)}</div><div class="bar-track"><div class="bar-fill ${r.cls||'accent'}" style="width:${asNumber(r.value,0)/mx*100}%"></div></div><div class="bar-val">${escapeHtml(r.display!=null?r.display:r.value)}</div></div>`).join('')}
function _tbl(id,headers,rows){const el=document.getElementById(id);if(!el)return;if(!rows.length){el.innerHTML='<div class="empty"><p>暂无数据</p></div>';return}el.innerHTML=`<table><thead><tr>${headers.map(h=>`<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table>`}
function masteryCls(i){return i<3?'red':i<6?'yellow':i<8?'blue':'green'}
function accColor(v){return v===null?'var(--fg3)':v>=.8?'var(--green)':v>=.5?'var(--yellow)':'var(--red)'}

function renderAnalytics(){
  const a=ANALYTICS;if(!a)return;
  const ov=a.overview;
  document.getElementById('data-kpi').innerHTML=
    _kpiCard('c1','总复习次数',ov.total_reviews,`答对 ${ov.total_correct} / 答错 ${ov.total_wrong}`)+
    _kpiCard('c2','总体正确率',pctFmt(ov.accuracy),'')+
    _kpiCard('c4','当前连续',`${ov.current_streak} 天`,`最长 ${ov.longest_streak} 天`)+
    _kpiCard('c3','顽固题 Leech',ov.leech,`从未复习 ${ov.never_reviewed}`);
  document.getElementById('data-kpi2').innerHTML=
    _kpiCard('c1','平均熟练度',pctFmt(ov.avg_mastery),`衰减后 ${pctFmt(ov.avg_decayed_mastery)}`)+
    _kpiCard('c4','平均 EF',ov.avg_ef,`平均复习 ${ov.avg_attempts} 次`)+
    _kpiCard('c2','活跃天数',ov.active_days,ov.first_review?`自 ${ov.first_review}`:'')+
    _kpiCard('c3','近 30 天复习',ov.reviews_last_30,`近 7 天 ${ov.reviews_last_7}`);

  // 科目维度
  _tbl('data-subjects',['科目','题数','击杀','待攻克','leech','平均熟练','EF','正确率'],
    a.subjects.map(s=>[`<b style="color:var(--accent2)">${escapeHtml(s.subject)}</b>`,s.total,s.killed,s.attacking,
      s.leech?`<span style="color:var(--red)">${s.leech}</span>`:0,
      `<span style="color:${accColor(s.avg_mastery)}">${pctFmt(s.avg_mastery)}</span>`,s.avg_ef,
      `<span style="color:${accColor(s.accuracy)}">${pctFmt(s.accuracy)}</span>`]));

  // 分类维度 Top 15
  _tbl('data-categories',['分类','科目','题数','平均熟练','复习','正确率','leech'],
    a.categories.slice(0,15).map(c=>[escapeHtml(c.category),escapeHtml(c.subject||''),c.total,
      `<span style="color:${accColor(c.avg_mastery)}">${pctFmt(c.avg_mastery)}</span>`,c.reviews,
      `<span style="color:${accColor(c.accuracy)}">${pctFmt(c.accuracy)}</span>`,c.leech||0]));

  // 分布
  const mh=a.distributions.mastery_histogram,dh=a.distributions.decayed_histogram;
  const keys10=Object.keys(mh);
  _bars('data-mastery',keys10.map((k,i)=>({label:`${k}%`,value:mh[k],cls:masteryCls(i)})));
  _bars('data-decayed',keys10.map((k,i)=>({label:`${k}%`,value:dh[k],cls:masteryCls(i)})));
  const ef=a.distributions.ef_dist;const efKeys=Object.keys(ef);
  _bars('data-ef',efKeys.map((k,i)=>({label:k,value:ef[k],cls:i===0?'red':i===1?'yellow':i===2?'blue':'green'})));
  const dd=a.distributions.difficulty_dist;
  _bars('data-difficulty',Object.keys(dd).map(k=>{const i=+k;return{label:`Lv.${k}`,value:dd[k],cls:i<=3?'green':i<=6?'blue':i<=8?'accent':'red'}}));
  const rep=a.distributions.repetition_dist;
  _bars('data-repetition',Object.keys(rep).map((k,i)=>({label:k,value:rep[k],cls:i===0?'red':i===1?'yellow':i<=2?'blue':'green'})));
  const iv=a.distributions.interval_dist;
  _bars('data-interval',Object.keys(iv).map((k,i)=>({label:`${k}天`,value:iv[k],cls:i<=1?'red':i<=2?'yellow':i<=3?'blue':'green'})));

  // 主观分正确率
  const bs=a.accuracy.by_score;
  _bars('data-score-acc',Object.keys(bs).filter(s=>bs[s].count).map(s=>({label:`${s}分`,value:Math.round((bs[s].accuracy||0)*100),display:`${pctFmt(bs[s].accuracy)} (${bs[s].count})`,cls:bs[s].accuracy>=.8?'green':bs[s].accuracy>=.5?'yellow':'red'})));

  // 按周正确率
  _tbl('data-weekly',['周','复习','答对','正确率'],
    a.accuracy.weekly.map(w=>[escapeHtml(w.week),w.reviews,w.correct,
      `<span style="color:${accColor(w.accuracy)}">${pctFmt(w.accuracy)}</span>`]));

  // 按星期
  const wd=a.behavior.by_weekday;
  _bars('data-weekday',Object.keys(wd).map(k=>({label:k,value:wd[k],cls:'accent'})));

  // 按时段（24 格热力）
  const hourEl=document.getElementById('data-hour');const bh=a.behavior.by_hour;
  const hMax=Math.max(1,...Object.values(bh));
  hourEl.innerHTML=`<div class="heatmap">${Array.from({length:24},(_,h)=>{const c=bh[h]||bh[String(h)]||0;const alpha=c?Math.min(.12+c/hMax*.55,.7):.03;return `<div class="heat-cell" style="background:rgba(139,94,60,${alpha})" title="${h}:00 — ${c} 次">${String(h).padStart(2,'0')}</div>`}).join('')}</div><div style="font-size:.65rem;color:var(--fg3);margin-top:6px">每格为一个小时（00–23），颜色越深复习越多</div>`;

  // 到期预测
  const fc=a.forecast;
  _bars('data-forecast',[
    {label:'今日',value:fc['0'],cls:'yellow'},
    ...[1,2,3,4,5,6,7].map(i=>({label:`+${i}天`,value:fc[String(i)],cls:'blue'})),
    {label:'7天+',value:fc['7+'],cls:'green'},
  ]);

  // 预警
  const al=a.review_alert;
  const cells=[
    {label:'逾期',val:al.overdue,color:'#c0392b'},
    {label:'今日到期',val:al.due_today,color:'#b8860b'},
    {label:'急需复习',val:al.urgent,color:'#c0392b'},
    {label:'警告队列',val:al.warning,color:'#b8860b'},
    {label:'长期冷落',val:al.cold,color:'#2e6da4'},
    {label:'顽固题',val:al.leech,color:'#8b5e3c'},
  ];
  document.getElementById('data-alerts').innerHTML=`<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px">`+cells.map(c=>`<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:12px;text-align:center;border-top:3px solid ${c.color}"><div style="font-size:.68rem;color:var(--fg3);margin-bottom:4px">${escapeHtml(c.label)}</div><div style="font-size:1.5rem;font-weight:900;color:${c.color};font-family:'JetBrains Mono',monospace">${c.val}</div></div>`).join('')+`</div>`;

  // Leech / 屡练不熟
  const leechBtn=u=>`<button class="btn sm" onclick="viewQ('${escapeAttr(u)}')">查看</button>`;
  _tbl('data-leeches',['UID','科目','分类','答错','熟练度','EF','复习',''],
    a.weak_spots.leeches.map(it=>[`<b style="color:var(--accent2)">${escapeHtml(it.uid)}</b>`,escapeHtml(it.subject||''),escapeHtml(it.category||''),
      `<span style="color:var(--red);font-weight:700">${it.fail_count}</span>`,
      `<span style="color:${accColor(it.mastery)}">${pctFmt(it.mastery)}</span>`,it.ef,it.attempts,leechBtn(it.uid)]));
  _tbl('data-struggling',['UID','科目','分类','熟练度','复习','答错',''],
    a.weak_spots.struggling.map(it=>[`<b style="color:var(--accent2)">${escapeHtml(it.uid)}</b>`,escapeHtml(it.subject||''),escapeHtml(it.category||''),
      `<span style="color:${accColor(it.mastery)}">${pctFmt(it.mastery)}</span>`,it.attempts,
      it.fail_count?`<span style="color:var(--red)">${it.fail_count}</span>`:0,leechBtn(it.uid)]));
}

async function loadAnalytics(){
  const status=document.getElementById('data-status');
  status.innerHTML='<span style="color:var(--fg3)">加载中…</span>';
  try{
    ANALYTICS=await api('/api/analytics');
    status.innerHTML=`<span style="color:var(--fg3)">数据基准时间 ${escapeHtml(ANALYTICS.generated_at||'')}</span>`;
    renderAnalytics();
  }catch(e){
    status.innerHTML=`<span style="color:var(--red)">✕ 无法加载数据（需后端运行）：${escapeHtml(e.message)}</span>`;
  }
}

async function exportReview(){
  const status=document.getElementById('data-status');
  status.innerHTML='<span style="color:var(--yellow)">导出中…</span>';
  try{
    const response=await fetch('/api/export-review');
    if(!response.ok){let m='导出失败';try{m=(await response.json()).msg||m}catch(e){}status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(m)}</span>`;return}
    await downloadExportResponse(response,`OMRS-复盘-${new Date().toISOString().slice(0,10)}.html`,'data-status');
  }catch(e){status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`}
}

