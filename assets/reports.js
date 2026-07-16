// === assets/reports.js — 报告托管页：列表/上传创建/浏览/删除 ===
let REPORTS=[];

function fmtSize(bytes){const n=asNumber(bytes,0);if(n<1024)return n+' B';if(n<1024*1024)return (n/1024).toFixed(1)+' KB';return (n/1024/1024).toFixed(1)+' MB'}

function reportIncludesImages(){return !!document.getElementById('rp-include-images')?.checked}

function updateReportMaterialHint(){
  const hint=document.getElementById('rp-material-hint');
  if(!hint)return;
  hint.textContent=reportIncludesImages()
    ?'下载 ZIP：包含分析 Markdown 与题面引用的图片。图片仅供 AI 阅读，最终报告须按系统图片接口规则引用。'
    :'下载 Markdown 数据文件，不包含图片文件；AI 不会依据题图内容进行分析。';
}

function buildReportAiPrompt(includeImages){
  const imageRule=includeImages
    ?`本次材料包含 images/ 目录。你可以查看图片辅助理解题目，但最终 HTML 禁止引用 images/ 相对路径、file:// 路径或把图片转为 base64。需要展示题图时，只能使用数据中 items[].images 的原始文件名，并按以下格式引用：\n<img src="/api/image?name=<对文件名执行 URL 编码后的值>" alt="题目 UID">\n只展示确实有助于说明薄弱点的图片，不要把所有图片堆入报告。`
    :`本次材料不包含图片文件。不要猜测题图内容，也不要在报告中生成任何题目图片或 <img> 标签；只能依据数据文件中的统计、题目元数据和复习历史分析。`;

  return `你是一名严谨的学习数据分析师。请读取我随后提供的 OMRS 错题复盘数据，生成一份可直接上传到 OMRS「报告」页面的完整 HTML 分析报告。\n\n【分析要求】\n1. 所有数字和结论必须能从输入数据验证，禁止虚构、补全或猜测；证据不足时明确写“数据不足”。\n2. 先给出结论摘要，再分析科目、分类、难度、熟练度、正确率、复习行为、到期情况、顽固题和趋势。\n3. 找出最值得优先处理的薄弱点，说明判断依据；涉及具体题目时标注 UID。\n4. 给出按优先级排序、可执行的复习建议，并区分“立即处理、未来 7 天、长期策略”。\n5. 区分相关性与因果，不要把少量样本或单次波动解释成确定规律。\n\n【图片规则】\n${imageRule}\n\n【HTML 交付规则】\n1. 只返回一个完整 HTML 文档，从 <!DOCTYPE html> 开始；不要使用 Markdown 代码围栏，不要附加解释文字。\n2. CSS 和必要 JavaScript 全部内嵌，不引用 CDN、外部字体、外部脚本或其他网络资源。\n3. 使用 UTF-8，适配桌面与手机，保证打印可读；图表优先使用 HTML/CSS 或内嵌 SVG。\n4. 页面应包含：报告标题与生成时间、核心结论、关键指标、薄弱点证据、重点题目、复习计划、数据限制说明。\n5. 对空数组、缺失值和零样本做安全处理，不显示误导性的百分比。\n6. 最终文件必须能保存为 .html，并由 OMRS 报告页直接上传托管。`;
}

async function copyReportAiPrompt(){
  const status=document.getElementById('rp-status');
  const ok=await copyTextToClipboard(buildReportAiPrompt(reportIncludesImages()));
  status.innerHTML=ok
    ?'<span style="color:var(--green)">✓ AI 报告提示词已复制</span>'
    :'<span style="color:var(--red)">✕ 复制失败，请检查剪贴板权限</span>';
}

async function downloadReportData(){
  const status=document.getElementById('rp-status');
  const button=document.getElementById('rp-data-btn');
  const includeImages=reportIncludesImages();
  button.disabled=true;
  button.textContent=includeImages?'正在打包…':'正在导出…';
  status.innerHTML='<span style="color:var(--yellow)">正在准备 AI 分析材料…</span>';
  try{
    const response=await fetch(`/api/export-review?include_images=${includeImages?'1':'0'}`);
    if(!response.ok){let message='导出失败';try{message=(await response.json()).msg||message}catch(e){}throw new Error(message)}
    await downloadExportResponse(response,includeImages?'OMRS-AI数据-含图片.zip':'OMRS-AI数据.md','rp-status');
  }catch(e){
    status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`;
  }finally{
    button.disabled=false;
    button.textContent='下载分析数据';
  }
}

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
