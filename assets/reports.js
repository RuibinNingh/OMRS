// === assets/reports.js — 报告托管页：列表/上传创建/浏览/删除 ===
let REPORTS=[];

function fmtSize(bytes){const n=asNumber(bytes,0);if(n<1024)return n+' B';if(n<1024*1024)return (n/1024).toFixed(1)+' KB';return (n/1024/1024).toFixed(1)+' MB'}

async function loadReports(){
  const box=document.getElementById('rp-list');
  box.innerHTML='<div style="font-size:.8rem;color:var(--fg3)">加载中…</div>';
  try{
    const result=await api('/api/reports');
    REPORTS=result.reports||[];
    renderReports();
  }catch(e){
    box.innerHTML=`<div style="font-size:.8rem;color:var(--red)">✕ 无法加载报告（需后端运行）：${escapeHtml(e.message)}</div>`;
  }
}

function renderReports(){
  const box=document.getElementById('rp-list');
  if(!REPORTS.length){
    box.innerHTML='<div class="empty"><div class="icon">📄</div><p>还没有报告。在左侧上传一个 HTML 报告。</p></div>';
    return;
  }
  box.innerHTML=REPORTS.map(r=>`
    <div class="sched-item">
      <div style="flex:1">
        <div class="uid">${escapeHtml(r.name)}</div>
        <div class="meta-line">${escapeHtml(r.created_at||'')} · ${fmtSize(r.size)} · <span style="font-family:'JetBrains Mono',monospace;font-size:.66rem">${escapeHtml(r.id)}</span></div>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn sm primary" onclick="openReport('${escapeAttr(r.id)}')">浏览</button>
        <button class="btn sm danger" onclick="deleteReport('${escapeAttr(r.id)}')">删除</button>
      </div>
    </div>`).join('');
}

function openReport(id){
  // 同源新标签打开，报告内的 /api/image?name=... 可正常加载
  window.open(`/api/report/view?id=${encodeURIComponent(id)}`,'_blank');
}

function readFileText(file){
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(reader.result);
    reader.onerror=()=>reject(new Error('文件读取失败'));
    reader.readAsText(file,'utf-8');
  });
}

async function createReport(){
  const status=document.getElementById('rp-status');
  const name=document.getElementById('rp-name').value.trim();
  const fileInput=document.getElementById('rp-file');
  const file=fileInput.files&&fileInput.files[0];
  if(!name){status.innerHTML='<span style="color:var(--red)">请填写报告名称</span>';return}
  if(!file){status.innerHTML='<span style="color:var(--red)">请选择 HTML 文件</span>';return}
  const btn=document.getElementById('rp-btn');btn.disabled=true;btn.textContent='上传中…';
  try{
    const html=await readFileText(file);
    const result=await api('/api/report/create',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({name,html})});
    status.innerHTML=`<span style="color:var(--green)">✓ 已创建：${escapeHtml(result.name)}（${fmtSize(result.size)}）</span>`;
    document.getElementById('rp-name').value='';
    fileInput.value='';
    await loadReports();
  }catch(e){
    status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`;
  }
  btn.disabled=false;btn.textContent='上传并创建';
}

async function deleteReport(id){
  if(!confirm('确定删除该报告？'))return;
  try{
    await api('/api/report/delete',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id})});
    await loadReports();
  }catch(e){
    document.getElementById('rp-status').innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`;
  }
}
