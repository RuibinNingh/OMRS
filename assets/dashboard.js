// === assets/dashboard.js — 仪表盘图表 renderDash ===
function renderDash(){
  const d=DATA;
  document.getElementById('s-total').textContent=d.total;
  document.getElementById('s-killed').textContent=d.killed;
  document.getElementById('s-kill-pct').textContent=d.total?`${(d.killed/d.total*100).toFixed(0)}% 击杀率`:'';
  document.getElementById('s-attack').textContent=d.attacking;
  document.getElementById('s-avgm').textContent=`${(d.avg_mastery*100).toFixed(0)}%`;
  const sc=document.getElementById('chart-subjects');sc.innerHTML='';
  const subjectEntries=Object.entries(d.subject_dist||{});
  const mx=Math.max(1,...subjectEntries.map(([,value])=>value.total||0));
  subjectEntries.forEach(([name,value])=>{const killPct=value.total?value.killed/value.total*100:0;sc.innerHTML+=`<div class="bar-row"><div class="bar-label">${escapeHtml(name)}</div><div class="bar-track"><div class="bar-fill green" style="width:${killPct}%"></div></div><div class="bar-track" style="flex:.4"><div class="bar-fill accent" style="width:${value.total/mx*100}%"></div></div><div class="bar-val">${value.total}</div></div>`});
  if(!subjectEntries.length)sc.innerHTML='<div class="empty"><p>暂无数据</p></div>';
  const mc=document.getElementById('chart-mastery');mc.innerHTML='';
  const mh=d.mastery_histogram||{};const mhMax=Math.max(1,...Object.values(mh));
  ['0-10','10-20','20-30','30-40','40-50','50-60','60-70','70-80','80-90','90-100'].forEach((label,idx)=>{const key=`${idx*10}-${(idx+1)*10}`;const count=mh[key]||0;const cls=idx<3?'red':idx<6?'yellow':idx<8?'blue':'green';mc.innerHTML+=`<div class="bar-row"><div class="bar-label">${label}%</div><div class="bar-track"><div class="bar-fill ${cls}" style="width:${count/mhMax*100}%"></div></div><div class="bar-val">${count}</div></div>`});
  if(!Object.keys(mh).length)mc.innerHTML='<div class="empty"><p>暂无数据</p></div>';
  const ac=document.getElementById('chart-activity');const hm=document.createElement('div');hm.className='heatmap';ac.innerHTML='';ac.appendChild(hm);const today=new Date();for(let i=29;i>=0;i-=1){const dt=new Date(today);dt.setDate(dt.getDate()-i);const key=dt.toISOString().slice(0,10);const count=(d.recent_activity||{})[key]||0;const alpha=count?Math.min(.12+count*.12,.68):.04;const heatText=count>=3?'#fff':count?'#5a321c':'#8b8176';const heatShadow=count>=3?'text-shadow:0 1px 1px rgba(0,0,0,.35);':'';hm.innerHTML+=`<div class="heat-cell" style="background:rgba(139,94,60,${alpha});color:${heatText};${heatShadow}" title="${key}: ${count}次">${count||''}</div>`}
  const tc=document.getElementById('chart-trend');tc.innerHTML='';
  const trend=d.daily_trend||{};const trendDates=Object.keys(trend).sort();
  const trendMax=Math.max(1,...Object.values(trend));
  const w=640,h=300,p=34,baseY=h-p,plotH=h-p*2,plotW=w-p*2;
  const trendPoints=trendDates.map((dt,i)=>{const x=p+(i/(trendDates.length-1||1))*plotW;const y=baseY-(trend[dt]/trendMax)*plotH;return{dt,value:trend[dt],x,y}});
  const points=trendPoints.map(pt=>`${pt.x},${pt.y}`).join(' ');
  let trendGrid='';for(let i=0;i<=4;i+=1){const y=baseY-(i/4)*plotH;const value=Math.round((trendMax*i)/4);trendGrid+=`<line x1="${p}" y1="${y}" x2="${w-p}" y2="${y}" stroke="rgba(0,0,0,.07)"/><text x="${p-8}" y="${y+4}" font-size="11" fill="#777" text-anchor="end">${value}</text>`}
  let bars='';let markers='';trendPoints.forEach((pt,i)=>{const bh=(pt.value/trendMax)*plotH;bars+=`<rect x="${pt.x-5}" y="${baseY-bh}" width="10" height="${bh}" fill="rgba(139,94,60,0.22)" rx="3"><title>${pt.dt}: ${pt.value}次</title></rect>`;const showLabel=pt.value>0&&(trendPoints.length<=16||i%2===0||pt.value===trendMax);markers+=`<circle cx="${pt.x}" cy="${pt.y}" r="${pt.value?4.5:3}" fill="#fff" stroke="#8b5e3c" stroke-width="2"><title>${pt.dt}: ${pt.value}次</title></circle>${showLabel?`<text x="${pt.x}" y="${Math.max(14,pt.y-9)}" font-size="11" fill="#5a321c" font-weight="700" text-anchor="middle">${pt.value}</text>`:''}`});
  const trendDateLabels=trendPoints.filter((_,i)=>i===0||i===trendPoints.length-1||i===Math.floor(trendPoints.length/2)).map(pt=>`<text x="${pt.x}" y="${h-11}" font-size="11" fill="#777" text-anchor="${pt.x===p?'start':pt.x===w-p?'end':'middle'}">${pt.dt.slice(5)}</text>`).join('');
  tc.innerHTML=trendDates.length?`<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:280px;display:block"><defs><linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba(139,94,60,0.38)"/><stop offset="100%" stop-color="rgba(139,94,60,0.04)"/></linearGradient></defs>${trendGrid}${bars}<polygon points="${p},${baseY} ${points} ${w-p},${baseY}" fill="url(#trendGrad)"/><polyline points="${points}" fill="none" stroke="#8b5e3c" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>${markers}<line x1="${p}" y1="${baseY}" x2="${w-p}" y2="${baseY}" stroke="#b9b2aa"/><line x1="${p}" y1="${p}" x2="${p}" y2="${baseY}" stroke="#b9b2aa"/><text x="${w/2}" y="${h-2}" font-size="12" fill="#666" text-anchor="middle">近30天</text><text x="13" y="${h/2}" font-size="12" fill="#666" transform="rotate(-90 13,${h/2})">练习次数</text>${trendDateLabels}</svg>`:'<div class="empty"><p>暂无数据</p></div>';
  const al=document.getElementById('chart-alerts');al.innerHTML='';
  const alertData=d.review_alert||{};
  const alerts=[{label:'急需复习',val:alertData.urgent||0,desc:'衰减熟练度<30%且超过7天未复习',color:'#c0392b'},{label:'警告队列',val:alertData.warning||0,desc:'衰减熟练度<50%且超过14天未复习',color:'#b8860b'},{label:'长期冷落',val:alertData.cold||0,desc:'超过30天未复习',color:'#2e6da4'},{label:'建议今日复习',val:alertData.total_due||0,desc:'基于调度优先级建议复习总量',color:'#8b5e3c'}];
  al.innerHTML=`<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px">`+alerts.map(a=>`<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:14px;text-align:center;border-top:3px solid ${a.color}"><div style="font-size:.7rem;color:var(--fg3);margin-bottom:4px">${escapeHtml(a.label)}</div><div style="font-size:1.6rem;font-weight:900;color:${a.color};font-family:'JetBrains Mono',monospace">${a.val}</div><div style="font-size:.65rem;color:var(--fg3);margin-top:4px">${escapeHtml(a.desc)}</div></div>`).join('')+`</div>`;
  const dc=document.getElementById('chart-diff');dc.innerHTML='';
  const maxDiff=Math.max(1,...Object.values(d.difficulty_dist||{}).map(value=>asNumber(value,0)));
  for(let i=1;i<=10;i+=1){const count=asNumber((d.difficulty_dist||{})[String(i)],0);const cls=i<=3?'green':i<=6?'blue':i<=8?'accent':'red';dc.innerHTML+=`<div class="bar-row"><div class="bar-label">Lv.${i}</div><div class="bar-track"><div class="bar-fill ${cls}" style="width:${count/maxDiff*100}%"></div></div><div class="bar-val">${count}</div></div>`}
}
