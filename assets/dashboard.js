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
  const ac=document.getElementById('chart-activity');const hm=document.createElement('div');hm.className='heatmap';ac.innerHTML='';ac.appendChild(hm);const today=new Date();for(let i=29;i>=0;i-=1){const dt=new Date(today);dt.setDate(dt.getDate()-i);const key=dt.toISOString().slice(0,10);const count=(d.recent_activity||{})[key]||0;const alpha=count?Math.min(.1+count*.1,.6):.02;hm.innerHTML+=`<div class="heat-cell" style="background:rgba(139,94,60,${alpha})" title="${key}: ${count}次">${count||''}</div>`}
  const tc=document.getElementById('chart-trend');tc.innerHTML='';
  const trend=d.daily_trend||{};const trendDates=Object.keys(trend).sort();
  const trendMax=Math.max(1,...Object.values(trend));
  const w=320,h=120,p=24;
  const points=trendDates.map((dt,i)=>{const x=p+(i/(trendDates.length-1||1))*(w-p*2);const y=h-(p+(trend[dt]/trendMax)*(h-p*2));return `${x},${y}`}).join(' ');
  let bars='';trendDates.forEach((dt,i)=>{const v=trend[dt];const x=p+(i/(trendDates.length-1||1))*(w-p*2);const bh=(v/trendMax)*(h-p*2);bars+=`<rect x="${x-3}" y="${h-p-bh}" width="6" height="${bh}" fill="rgba(139,94,60,0.3)" rx="2"><title>${dt}: ${v}次</title></rect>`});
  tc.innerHTML=trendDates.length?`<svg viewBox="0 0 ${w} ${h}" style="width:100%;height:140px"><defs><linearGradient id="trendGrad" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba(139,94,60,0.5)"/><stop offset="100%" stop-color="rgba(139,94,60,0.05)"/></linearGradient></defs>${bars}<polyline points="${points}" fill="none" stroke="#8b5e3c" stroke-width="2"/><polygon points="${p},${h-p} ${points} ${w-p},${h-p}" fill="url(#trendGrad)"/><line x1="${p}" y1="${h-p}" x2="${w-p}" y2="${h-p}" stroke="#ccc"/><line x1="${p}" y1="${p}" x2="${p}" y2="${h-p}" stroke="#ccc"/><text x="${w/2}" y="${h-4}" font-size="10" fill="#999" text-anchor="middle">近30天</text><text x="8" y="${h/2}" font-size="10" fill="#999" transform="rotate(-90 8,${h/2})">练习次数</text></svg>`:'<div class="empty"><p>暂无数据</p></div>';
  const sp=document.getElementById('chart-scatter');sp.innerHTML='';
  const scatter=d.scatter_data||[];
  const sw=320,sh=160,spPad=28;
  let circles='';scatter.forEach(pt=>{const cx=spPad+((pt.difficulty-1)/9)*(sw-spPad*2);const cy=sh-spPad-(pt.mastery)*(sh-spPad*2);const color=pt.mastery>.8?'#27864a':pt.mastery>.4?'#b8860b':'#c0392b';circles+=`<circle cx="${cx}" cy="${cy}" r="3" fill="${color}" opacity="0.7"><title>${escapeHtml(pt.uid)} · D${pt.difficulty} · M${(pt.mastery*100).toFixed(0)}%</title></circle>`});
  sp.innerHTML=scatter.length?`<svg viewBox="0 0 ${sw} ${sh}" style="width:100%;height:170px"><rect x="${spPad}" y="${spPad}" width="${sw-spPad*2}" height="${sh-spPad*2}" fill="rgba(0,0,0,0.02)" rx="4"/><line x1="${spPad}" y1="${sh-spPad}" x2="${sw-spPad}" y2="${sh-spPad}" stroke="#bbb"/><line x1="${spPad}" y1="${spPad}" x2="${spPad}" y2="${sh-spPad}" stroke="#bbb"/><text x="${sw/2}" y="${sh-4}" font-size="10" fill="#888" text-anchor="middle">难度</text><text x="8" y="${sh/2}" font-size="10" fill="#888" transform="rotate(-90 8,${sh/2})">熟练度</text><text x="${spPad}" y="${sh-spPad+12}" font-size="9" fill="#999">1</text><text x="${sw-spPad}" y="${sh-spPad+12}" font-size="9" fill="#999" text-anchor="end">10</text><text x="${spPad-6}" y="${sh-spPad}" font-size="9" fill="#999" text-anchor="end">0%</text><text x="${spPad-6}" y="${spPad+4}" font-size="9" fill="#999" text-anchor="end">100%</text>${circles}</svg>`:'<div class="empty"><p>暂无数据</p></div>';
  const al=document.getElementById('chart-alerts');al.innerHTML='';
  const alertData=d.review_alert||{};
  const alerts=[{label:'急需复习',val:alertData.urgent||0,desc:'衰减熟练度<30%且超过7天未复习',color:'#c0392b'},{label:'警告队列',val:alertData.warning||0,desc:'衰减熟练度<50%且超过14天未复习',color:'#b8860b'},{label:'长期冷落',val:alertData.cold||0,desc:'超过30天未复习',color:'#2e6da4'},{label:'建议今日复习',val:alertData.total_due||0,desc:'基于调度优先级建议复习总量',color:'#8b5e3c'}];
  al.innerHTML=`<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px">`+alerts.map(a=>`<div style="background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:14px;text-align:center;border-top:3px solid ${a.color}"><div style="font-size:.7rem;color:var(--fg3);margin-bottom:4px">${escapeHtml(a.label)}</div><div style="font-size:1.6rem;font-weight:900;color:${a.color};font-family:'JetBrains Mono',monospace">${a.val}</div><div style="font-size:.65rem;color:var(--fg3);margin-top:4px">${escapeHtml(a.desc)}</div></div>`).join('')+`</div>`;
  const dc=document.getElementById('chart-diff');dc.innerHTML='';
  const maxDiff=Math.max(1,...Object.values(d.difficulty_dist||{}).map(value=>asNumber(value,0)));
  for(let i=1;i<=10;i+=1){const count=asNumber((d.difficulty_dist||{})[String(i)],0);const cls=i<=3?'green':i<=6?'blue':i<=8?'accent':'red';dc.innerHTML+=`<div class="bar-row"><div class="bar-label">Lv.${i}</div><div class="bar-track"><div class="bar-fill ${cls}" style="width:${count/maxDiff*100}%"></div></div><div class="bar-val">${count}</div></div>`}
}
