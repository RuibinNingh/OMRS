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

  return `你是一名严谨的学习数据分析师，同时也是一名顶尖的信息设计师和数据可视化工程师。请读取我随后提供的 OMRS 错题复盘数据，生成一份可直接上传到 OMRS「报告」页面的完整 HTML 分析报告。报告不仅要准确、清晰，还要达到精心设计的专业数据产品水准。\n\n【分析要求】\n1. 所有数字和结论必须能从输入数据验证，禁止虚构、补全或猜测；证据不足时明确写“数据不足”。\n2. 先给出结论摘要，再分析科目、分类、难度、熟练度、正确率、复习行为、到期情况、顽固题和趋势。\n3. 找出最值得优先处理的薄弱点，说明判断依据；涉及具体题目时标注 UID。\n4. 给出按优先级排序、可执行的复习建议，并区分“立即处理、未来 7 天、长期策略”。\n5. 区分相关性与因果，不要把少量样本或单次波动解释成确定规律。\n\n【视觉与交互要求】\n1. 采用“编辑式数据叙事”思路：建立鲜明的标题、结论、指标、证据和行动层级，让读者先看到最重要的判断，再逐层探索细节。\n2. 自行确定一个与本次数据气质匹配、从头到尾一致的视觉概念；使用克制而有辨识度的色彩、精细的排版、充足留白和高数据墨水比，避免廉价模板感、过度渐变、霓虹科技风、emoji 装饰和无意义卡片堆砌。\n3. 可以通过 HTTPS 使用高质量外部资源，例如 Google Fonts、Fontsource、Chart.js、ECharts、D3、图标库或稳定公共 CDN；按实际需要选用，不要为了炫技引入多套重复依赖。禁止广告、统计、追踪脚本和任何需要密钥的资源。\n4. 外部资源加载失败时，正文、关键数字和结论仍必须可读；字体提供合理回退，图表至少保留文字摘要或数据表。\n5. 图表必须真正帮助理解数据，颜色承担语义并保持一致；提供清楚的标题、单位、图例、悬浮提示和空状态，禁止 3D 图、装饰性仪表盘和误导性坐标轴。\n6. 使用 CSS Grid/Flex、CSS 自定义属性和 clamp() 构建响应式系统；兼容桌面和手机，正文不小于 16px，交互目标不小于 44px，不产生横向滚动。\n7. 可加入克制的进入动画、悬停反馈、目录导航、主题切换或图表交互，但必须尊重 prefers-reduced-motion，且不能妨碍打印、阅读和数据核对。\n8. 提供适合 A4 的 @media print 样式：隐藏纯交互控件，避免图表/卡片被错误截断，确保黑白打印仍能区分信息。\n\n【图片规则】\n${imageRule}\n\n【HTML 交付规则】\n1. 只返回一个完整 HTML 文档，从 <!DOCTYPE html> 开始；不要使用 Markdown 代码围栏，不要附加解释文字。\n2. HTML、核心 CSS 和业务逻辑必须保存在同一个 .html 文件中；允许按上述规则引用 HTTPS 外部字体、样式或脚本。\n3. 使用 UTF-8，并包含正确的 viewport、语义化结构、键盘焦点样式和基础无障碍属性。\n4. 页面应包含：报告标题与生成时间、核心结论、关键指标、薄弱点证据、重点题目、复习计划、数据限制说明。\n5. 对空数组、缺失值和零样本做安全处理，不显示误导性的百分比；外部图表库初始化失败时不得导致整页报错或空白。\n6. 最终文件必须能保存为 .html，并由 OMRS 报告页直接上传托管。`;
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
        <div class="meta-line">${escapeHtml(r.created_at||'')} · ${fmtSize(r.size)} · <span style="font-family:'JetBrains Mono','Noto Sans SC',monospace;font-size:.66rem">${escapeHtml(r.id)}</span></div>
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
  if(!await uiConfirm('删除该报告？',{okText:'删除',danger:true}))return;
  try{
    await api('/api/report/delete',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({id})});
    await loadReports();
  }catch(e){
    document.getElementById('rp-status').innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`;
  }
}
