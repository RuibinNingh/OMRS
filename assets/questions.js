// === assets/questions.js — 题目库表格/画廊视图 + 题目 Modal + 题目操作 ===
// 围绕列表的壳（筛选抽屉 / chips / 批量条 / 列设置）在 qtable.js；标记芯片与 picker 在 labels.js。
const QB_TABLE_COLUMN_ORDER = ['select', 'main', 'labels', 'mastery', 'due', 'status', 'difficulty', 'decayed', 'attempts', 'last_review', 'ef', 'actions'];
const QB_TABLE_COLUMN_LABELS = {
  select: '<input type="checkbox" id="qb-select-all" onchange="qbSelectAll(this.checked)" title="全选当前显示">',
  main: 'UID / 题目',
  labels: '标记',
  mastery: '熟练度',
  due: '到期',
  status: '状态',
  difficulty: '难度',
  decayed: '衰减后',
  attempts: '次数',
  last_review: '上次复习',
  ef: 'EF',
  actions: '',
};
function statusTagHtml(item){if(item.suspended)return'<span class="tag suspended">停用</span>';const tag=String(item.tag||'').replace(/^#/,'').replace(/^状态\//,'');const cls=tag.includes('已击杀')?'kill':tag.includes('易错')?'trap':'attack';return`<span class="tag ${cls}">${escapeHtml(tag||'待攻克')}</span>`}
function masteryBarHtml(item,width){const m=asNumber(item.mastery,0);const color=m>.8?'var(--green)':m>.4?'var(--yellow)':'var(--red)';return`<span class="m-bar"${width?` style="width:${width}px"`:''}><span class="m-bar-fill" style="width:${m*100}%;background:${color}"></span></span>${(m*100).toFixed(0)}%`}
// 行内「⋯」菜单：查看 / 加入展示板 / 打标记 / 编辑 Markdown / 迁移分类 / 停用·恢复 / 删除（表格与画廊共用）
function renderQuestionMoreMenu(uid){const item=getItemByUid(uid)||{};const u=escapeAttr(uid);return`<div class="q-edit-wrap" data-edit-uid="${u}"><button class="btn sm ghost q-more" type="button" data-q-more="${u}" title="更多操作" aria-label="更多操作">⋯</button><div class="q-edit-menu"><button type="button" data-q-action="view" data-q-uid="${u}">查看详情</button><button type="button" data-q-action="board" data-q-uid="${u}">加入展示板</button><button type="button" data-q-action="labels" data-q-uid="${u}">打标记</button><button type="button" data-q-action="edit" data-q-uid="${u}">编辑 Markdown</button><button type="button" data-q-action="move" data-q-uid="${u}">迁移分类</button>${item.suspended?`<button type="button" data-q-action="resume" data-q-uid="${u}">恢复题目</button>`:`<button type="button" data-q-action="suspend" data-q-uid="${u}">停用题目</button>`}<button type="button" class="danger" data-q-action="delete" data-q-uid="${u}">删除题目</button></div></div>`}
function renderQuestionEditMenu(uid){return renderQuestionMoreMenu(uid)}
function renderQuestionTable(items){qvSetContext('q',items.map(item=>item.uid));const tbody=document.getElementById('q-tbody');if(!tbody)return;const columns=typeof qbVisibleColumns==='function'?qbVisibleColumns():new Set(['select','main','labels','mastery','due','status','actions']);const cell=(key,html,tag='td')=>columns.has(key)?`<${tag} data-qb-col="${key}">${html}</${tag}>`:'';const head=tbody.closest('table')?.querySelector('thead tr');if(head)head.innerHTML=QB_TABLE_COLUMN_ORDER.filter(key=>columns.has(key)).map(key=>cell(key,QB_TABLE_COLUMN_LABELS[key],'th')).join('');tbody.innerHTML=items.map(item=>{const uid=escapeAttr(item.uid);const cursor=typeof QB_CURSOR_UID!=='undefined'&&QB_CURSOR_UID===item.uid;const selected=typeof QB_SELECTED!=='undefined'&&QB_SELECTED.has(item.uid);const labels=lblChips(item.labels||[],{add:true,max:4});const extra={difficulty:escapeHtml(item.difficulty??''),decayed:`${(asNumber(item.decayed_mastery,0)*100).toFixed(0)}%`,attempts:escapeHtml(item.attempts??0),last_review:escapeHtml(item.last_review||'—'),ef:escapeHtml(item.ef??'')};return`<tr class="${item.suspended?'q-row-suspended':''}${cursor?' qb-cursor':''}${selected?' qb-selected':''}" aria-selected="${cursor?'true':'false'}" data-q-row="${uid}" title="点击查看题目">${cell('select',`<input type="checkbox" class="qb-row-check" data-qb-uid="${uid}" ${selected?'checked':''} aria-label="选择">`)}${cell('main',`<strong>${escapeHtml(item.uid)}</strong><div class="q-row-meta">${escapeHtml(item.subject||'')} · ${escapeHtml(item.category||'')}${item.is_leech?' · <span style="color:var(--yellow)">顽固</span>':''}</div>`)}${cell('labels',`<span class="q-label-cell" data-lbl-target="${uid}">${labels}</span>`)}${cell('mastery',masteryBarHtml(item))}${cell('due',formatDueInfo(getDueDays(item)))}${cell('status',statusTagHtml(item))}${['difficulty','decayed','attempts','last_review','ef'].map(key=>cell(key,extra[key])).join('')}${cell('actions',renderQuestionMoreMenu(item.uid))}</tr>`}).join('');if(!items.length){tbody.innerHTML=`<tr><td colspan="${columns.size}" style="text-align:center;color:var(--fg3);padding:28px">暂无匹配题目 · 试试放宽筛选条件</td></tr>`}}
// 画廊卡：精简优先。默认只出「标识 / 题面 / 脚注」三层，元数据（科目 / 上次复习 / 衰减后 / 知识点）
// 收进「列 / 密度」菜单里的「画廊显示元数据」开关（QB_GALLERY_DETAIL，默认关）。
function qbGalleryDetail(){return typeof QB_GALLERY_DETAIL!=='undefined'&&!!QB_GALLERY_DETAIL}
// UID 形如「物质分类与变化13」= 分类 + 序号；拆开显示，避免分类名在一张卡里重复三遍
function galleryIdHtml(item){
  const uid=String(item.uid||'');const category=String(item.category||'');
  if(category&&uid.startsWith(category)){
    const rest=uid.slice(category.length).replace(/^[-_·\s]+/,'');
    return `<span class="gc-cat">${escapeHtml(category)}</span>${rest?`<span class="gc-num">${escapeHtml(rest)}</span>`:''}`;
  }
  return `<span class="gc-num">${escapeHtml(uid)}</span>`;
}
// 只有「异常」才亮标：逾期 / 今日到期 / 顽固 / 停用。全库同值的「待攻克」不再逐卡重复
function galleryFlagsHtml(item,detail){
  const flags=[];
  if(item.suspended)flags.push('<span class="gc-flag muted">停用</span>');
  else{
    const days=getDueDays(item);
    if(days!=null&&days<0)flags.push(`<span class="gc-flag red">逾期 ${Math.abs(days)} 天</span>`);
    else if(days===0)flags.push('<span class="gc-flag yellow">今日</span>');
    else if(detail&&days!=null)flags.push(`<span class="gc-flag">${days} 天后</span>`);
  }
  if(item.is_leech)flags.push('<span class="gc-flag yellow">顽固</span>');
  return flags.join('');
}
function galleryFootHtml(item){
  const mastery=asNumber(item.mastery,0);
  const bits=[];
  bits.push(mastery>0?`<span class="gc-stat">${masteryBarHtml(item,36)}</span>`:'<span class="gc-stat muted">未练习</span>');
  if(item.difficulty!=null&&item.difficulty!=='')bits.push(`<span class="gc-stat muted">难度 ${escapeHtml(item.difficulty)}</span>`);
  const attempts=asNumber(item.attempts,0);
  if(attempts)bits.push(`<span class="gc-stat muted">${attempts} 次</span>`);
  return bits.join('');
}
function renderQuestionGallery(items){
  qvSetContext('q',items.map(item=>item.uid));
  const box=document.getElementById('q-gallery-wrap');
  if(!box)return;
  if(!items.length){box.innerHTML='<div class="picker-box"><div class="empty-inline">暂无匹配题目 · 试试放宽筛选条件</div></div>';return}
  const detail=qbGalleryDetail();
  const cardOpts=qbGalleryCardOpts();
  box.classList.toggle('is-detail',detail);
  box.dataset.cols=(typeof QB_GALLERY_COLS!=='undefined'&&QB_GALLERY_COLS)?String(QB_GALLERY_COLS):'auto';
  box.innerHTML=`<div class="gallery-grid">${items.map(item=>{
    const uid=escapeAttr(item.uid);
    const selected=typeof QB_SELECTED!=='undefined'&&QB_SELECTED.has(item.uid);
    const cached=QUESTION_CACHE[item.uid];
    const previewHtml=cached?qvHtml(cached,item,cardOpts):'<div class="preview-placeholder">正在加载题目预览…</div>';
    // 知识点与分类同名的那条是重复信息，去掉；剩下为空就整行不渲染
    const knowledgeTags=(item.knowledge_tags||[]).filter(tag=>tag&&tag!==item.category);
    const metaLine=detail?`<div class="gc-meta">${escapeHtml(item.subject||'')} · 上次复习 ${escapeHtml(item.last_review||'—')} · 衰减后 ${(asNumber(item.decayed_mastery,0)*100).toFixed(0)}%${knowledgeTags.length?` · ${knowledgeTags.map(tag=>escapeHtml(tag)).join(' / ')}`:''}</div>`:'';
    return `<div class="gallery-card ${item.suspended?'q-card-suspended':''} ${selected?'selected':''}" data-q-row="${uid}">
      <div class="gallery-head">
        <label class="gc-pick"><input type="checkbox" class="qb-row-check" data-qb-uid="${uid}" ${selected?'checked':''} aria-label="选择"></label>
        <span class="gc-id">${galleryIdHtml(item)}</span>
        <span class="gc-flags">${galleryFlagsHtml(item,detail)}</span>
        <span class="gc-more">${renderQuestionMoreMenu(item.uid)}</span>
      </div>
      ${metaLine}
      <div class="gallery-preview question-gallery-preview" data-question-preview-uid="${uid}">${previewHtml}</div>
      <div class="gc-foot">
        ${galleryFootHtml(item)}
        <span class="q-label-cell gc-labels" data-lbl-target="${uid}">${lblChips(item.labels||[],{add:true,max:3})}</span>
      </div>
    </div>`;
  }).join('')}</div>`;
}
// 画廊缩略卡也走 qview（bare + clamp），与 Modal / 反馈台共用同一套题面渲染
// 画廊缩略卡也走 qview（bare + clamp），与 Modal / 反馈台共用同一套题面渲染
const QV_CARD_OPTS={layout:'stack',showMeta:false,showAnswer:false,showNotes:false,showHistory:false,actions:[],bare:true,clamp:5};
const QV_CARD_OPTS_DETAIL={...QV_CARD_OPTS,clamp:8};
// 截断行数跟着密度走：紧凑模式下少截两行，和 CSS 里的 max-height 一起收窄卡片
function qbGalleryCardOpts(){
  const detail=qbGalleryDetail();
  const compact=typeof QB_DENSITY!=='undefined'&&QB_DENSITY==='compact';
  const base=detail?QV_CARD_OPTS_DETAIL:QV_CARD_OPTS;
  return compact?{...base,clamp:detail?6:3}:base;
}
// 拉完详情再量一次高度：真正被截断的卡才加 is-clipped（底部渐隐），短题不会平白糊一块
async function hydrateQuestionGalleryPreviews(){
  const cardOpts=qbGalleryCardOpts();
  const nodes=[...document.querySelectorAll('.question-gallery-preview[data-question-preview-uid]')];
  await Promise.all(nodes.map(async node=>{
    const uid=node.dataset.questionPreviewUid;
    if(!uid)return;
    const q=await ensureQuestionDetail(uid);
    if(node.dataset.questionPreviewUid!==uid)return;
    node.innerHTML=qvHtml(q,getItemByUid(uid)||{uid},cardOpts);
    node.classList.toggle('is-clipped',node.scrollHeight-node.clientHeight>4);
  }));
}
function setQView(view){Q_VIEW=view;try{localStorage.setItem('omrs-q-view',view)}catch(e){}renderQ()}
function renderQ(){if(!document.getElementById('q-tbody'))return;const filters=getFilterState('q');let items=filterItems(getItems(),filters);if(typeof qbPostFilter==='function')items=qbPostFilter(items);const tableWrap=document.getElementById('q-table-wrap');const galleryWrap=document.getElementById('q-gallery-wrap');document.getElementById('q-view-table')?.classList.toggle('active',Q_VIEW==='table');document.getElementById('q-view-gallery')?.classList.toggle('active',Q_VIEW==='gallery');if(Q_VIEW==='gallery'){tableWrap.style.display='none';galleryWrap.style.display='block';renderQuestionGallery(items);hydrateQuestionGalleryPreviews()}else{tableWrap.style.display='block';galleryWrap.style.display='none';renderQuestionTable(items)}if(typeof qbRenderSummary==='function'){qbRenderSummary(items,filters);qbRenderChips(filters);qbUpdateBatchBar();qbRenderDensity();qbRenderControls()}}
function filterQ(){if(typeof QB_QUICK!=='undefined'&&QB_QUICK&&QB_QUICK!=='leech')QB_QUICK='';renderQ()}
try{const savedView=localStorage.getItem('omrs-q-view');if(savedView==='gallery')Q_VIEW='gallery'}catch(e){}
function normalizeImageName(raw){return String(raw??'').trim().split('/').pop().split('\\').pop()}
function renderInlineImage(name,alt,width){const imageName=normalizeImageName(name);const capped=width?Math.min(asNumber(width,0),600):0;const style=`${capped?`max-width:${capped}px;`:'max-width:100%;'}height:auto;display:block;margin:8px 0;border-radius:4px`;const safeName=escapeHtml(imageName);return `<img src="/api/image?name=${encodeURIComponent(imageName)}" alt="${escapeAttr(alt||imageName)}" style="${style}" onerror="this.outerHTML='&lt;span style=&quot;color:var(--red);font-size:.8rem&quot;&gt;[图片缺失: ${safeName}]&lt;/span&gt;'">`}
function renderLatexSegment(source,display){const latex=String(source??'');if(window.katex&&typeof window.katex.renderToString==='function'){try{return window.katex.renderToString(latex,{displayMode:!!display,throwOnError:false,strict:'ignore',trust:false,output:'html'})}catch(error){}}return `<span class="math ${display?'display':''}">${escapeHtml(latex)}</span>`}
function renderMdInline(text=''){const source=String(text??'');const tokenRe=/(!\[\[[^\]]+?\]\]|!\[[^\]]*\]\([^)]+\)|\$\$[\s\S]+?\$\$|\$[^$\n]+\$)/g;let html='',last=0,match;while((match=tokenRe.exec(source))){html+=escapeHtml(source.slice(last,match.index));const token=match[0];let parsed=token.match(/^!\[\[([^\]|]+?)(?:\|(\d+))?\]\]$/);if(parsed){html+=renderInlineImage(parsed[1],parsed[1],parsed[2]||'');last=tokenRe.lastIndex;continue}parsed=token.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);if(parsed){const imageName=normalizeImageName(parsed[2]);html+=renderInlineImage(imageName,parsed[1]||imageName,'');last=tokenRe.lastIndex;continue}if(token.startsWith('$$')&&token.endsWith('$$')){html+=renderLatexSegment(token.slice(2,-2),true)}else if(token.startsWith('$')&&token.endsWith('$')){html+=renderLatexSegment(token.slice(1,-1),false)}last=tokenRe.lastIndex}return html+escapeHtml(source.slice(last))}
function splitMdTableRow(line){const source=String(line??'').trim().replace(/^\|/,'').replace(/\|$/,'');const cells=[];let cell='';for(let index=0;index<source.length;index++){const ch=source[index];if(ch==='\\'&&source[index+1]==='|'){cell+='|';index++}else if(ch==='|'){cells.push(cell.trim());cell=''}else{cell+=ch}}cells.push(cell.trim());return cells}
function isMdTableSeparator(line){const cells=splitMdTableRow(line);return cells.length>0&&cells.every(cell=>/^:?-{3,}:?$/.test(cell))}
function renderMdTable(header,rows){const headings=splitMdTableRow(header);const body=rows.map(row=>{const cells=splitMdTableRow(row);return `<tr>${headings.map((_,index)=>`<td>${renderMdInline(cells[index]||'')}</td>`).join('')}</tr>`}).join('');return `<div class="md-table-wrap"><table class="md-table"><thead><tr>${headings.map(cell=>`<th>${renderMdInline(cell)}</th>`).join('')}</tr></thead><tbody>${body}</tbody></table></div>`}
function countDisplayMathDelimiters(line=''){const source=String(line??'');let count=0;for(let index=0;index<source.length-1;index++){if(source[index]==='$'&&source[index+1]==='$'&&(index===0||source[index-1]!=='\\')){count++;index++}}return count}
function findDisplayMathEnd(lines,start){let delimiters=0;for(let index=start;index<lines.length;index++){delimiters+=countDisplayMathDelimiters(lines[index]);if(delimiters&&delimiters%2===0)return index}return -1}
// 题面换行模式。lean（默认）= 单个换行当作原文里偶然的软换行，接续显示；
// full = 原文每一处换行都保留成一行。两种模式下空行都只算「分段」，
// 段间距交给 CSS 的 .md-p（约 .5em），而不是像以前那样吐出一整行空白。
function mdLineBreakMode(){return (typeof QB_MD_MODE!=='undefined'&&QB_MD_MODE==='full')?'full':'lean'}
function renderMdContent(text='',mode){
  // 逐行渲染。空行以前译成 <br><br>，等于原样吐出一整行空白（.q-md 行距 1.8，
  // 一次就是 25px），题面还没读到就被顶下去，画廊缩略卡也白白少截几行。
  // 改成 <p class="md-p">：连续多个空行仍只算一段，间距由样式表统一收窄。
  const soft=(mode||mdLineBreakMode())!=='full';   // soft = 忽略单个换行
  const lines=String(text??'').split(/\r?\n/);
  const blocks=[];
  let para='',pendingSoftJoin=false;
  // 段尾多出来的 <br> 一律削掉，免得「硬换行 / 完整模式 + 紧跟空行」叠出多余空行
  const flush=()=>{const body=para.replace(/(?:<br>)+$/,'');if(body)blocks.push(`<p class="md-p">${body}</p>`);para='';pendingSoftJoin=false};
  for(let index=0;index<lines.length;){
    if(index+1<lines.length&&lines[index].includes('|')&&isMdTableSeparator(lines[index+1])){
      const header=lines[index],rows=[];
      index+=2;
      while(index<lines.length&&lines[index].includes('|')&&lines[index].trim()){rows.push(lines[index]);index++}
      flush();
      blocks.push(renderMdTable(header,rows));
      continue
    }
    if(lines[index].trim()===''){
      flush();
      index++;
      while(index<lines.length&&lines[index].trim()==='')index++;
      continue
    }
    let source=lines[index],end=index;
    if(countDisplayMathDelimiters(source)%2===1){
      const close=findDisplayMathEnd(lines,index);
      if(close>=index){source=lines.slice(index,close+1).join(String.fromCharCode(10));end=close}
    }
    const hardBreak=/ {2,}$/.test(source);
    if(hardBreak)source=source.replace(/ +$/,'');
    if(pendingSoftJoin)para+=' ';
    para+=renderMdInline(source);
    pendingSoftJoin=false;
    if(end<lines.length-1){
      if(hardBreak||!soft)para+='<br>';
      else pendingSoftJoin=true;
    }
    index=end+1
  }
  flush();
  return blocks.join('')
}
async function ensureQuestionDetail(uid){if(QUESTION_CACHE[uid])return QUESTION_CACHE[uid];if(QUESTION_PENDING[uid])return QUESTION_PENDING[uid];QUESTION_PENDING[uid]=(async()=>{try{const detail=await api(`/api/question?uid=${encodeURIComponent(uid)}`);if(detail?.error)throw new Error(detail.error);QUESTION_CACHE[uid]=detail;return detail}catch(error){const fallback=getItemByUid(uid)||{};QUESTION_CACHE[uid]={uid,subject:fallback.subject||'',category:fallback.category||'',difficulty:fallback.difficulty||'',question:'（无法加载题目预览）',notes:'',answer:'',history:'',tag:fallback.tag||'',knowledge_tags:fallback.knowledge_tags||[],_fallback:true};return QUESTION_CACHE[uid]}finally{delete QUESTION_PENDING[uid]}})();return QUESTION_PENDING[uid]}
// 题目 Modal：内容全部交给 qview 渲染（双栏 + 就地操作）。第二个参数是可选的翻页上下文，
// 可传 uid 数组，或传 qvSetContext() 登记过的上下文名（如 'q' / 'export'）；不传就退化成单题。
async function viewQ(uid,context){const list=Array.isArray(context)?context:(typeof context==='string'?qvContext(context):null);if(list&&list.length&&list.indexOf(uid)>=0)QV_NAV={list:[...list],index:list.indexOf(uid)};else if(QV_NAV.list.indexOf(uid)<0)QV_NAV={list:[uid],index:0};else QV_NAV.index=QV_NAV.list.indexOf(uid);document.getElementById('modal').classList.add('open');qvNavRender();await qvRender('#modal-stage',uid,{layout:'split',actions:['edit','board','labels','suspend','delete']})}
function closeModal(){const modal=document.getElementById('modal');if(modal)modal.classList.remove('open');const stage=document.getElementById('modal-stage');if(stage&&typeof QV_MOUNTS!=='undefined')QV_MOUNTS.delete(stage)}
function toggleQuestionEditMenu(event,uid){event.stopPropagation();document.querySelectorAll('.q-edit-wrap.open').forEach(node=>{if(node.dataset.editUid!==uid)node.classList.remove('open')});const box=event.currentTarget?.closest?.('.q-edit-wrap')||event.target.closest('.q-edit-wrap');if(box)box.classList.toggle('open')}
document.addEventListener('click',event=>{if(!event.target.closest?.('.q-edit-wrap'))document.querySelectorAll('.q-edit-wrap.open').forEach(node=>node.classList.remove('open'))});
document.addEventListener('click', event => {
  const more = event.target.closest?.('[data-q-more]');
  if (more) { toggleQuestionEditMenu(event, more.dataset.qMore); return; }
  const action = event.target.closest?.('[data-q-action]');
  if (action) {
    event.stopPropagation();
    const uid = action.dataset.qUid;
    document.querySelectorAll('.q-edit-wrap.open').forEach(node => node.classList.remove('open'));
    const kind = action.dataset.qAction;
    const context = action.closest('#panel-questions') ? 'q' : undefined;
    if (kind === 'view') viewQ(uid, context);
    else if (kind === 'board' && typeof boardQuickAdd === 'function') boardQuickAdd(uid);
    else if (kind === 'labels') openLabelPicker(uid, action);
    else if (kind === 'edit') openMarkdownEditor(uid);
    else if (kind === 'move') moveQuestionPrompt(uid);
    else if (kind === 'suspend') suspendQuestion(uid);
    else if (kind === 'resume') resumeQuestion(uid);
    else if (kind === 'delete') deleteQuestion(uid);
    return;
  }
  const row = event.target.closest?.('#panel-questions [data-q-row]');
  if (row && !event.target.closest('button,input,label,a,[data-lbl-target],.q-edit-wrap')) {
    if (typeof QB_CURSOR_UID !== 'undefined') QB_CURSOR_UID = row.dataset.qRow;
    viewQ(row.dataset.qRow, 'q');
  }
});
document.addEventListener('change', event => {
  const check = event.target.closest?.('[data-qb-uid]');
  if (check && typeof qbSelect === 'function') { qbSelect(check.dataset.qbUid, check.checked); check.closest('[data-q-row]')?.classList.toggle('selected', check.checked); }
});
async function moveQuestionPrompt(uid){const item=getItemByUid(uid)||{};const subjects=[...new Set(getItems().map(i=>i.subject).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));const categories=[...new Set(getItems().map(i=>i.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));const res=await uiDialog({title:`迁移「${uid}」到其他分类`,okText:'迁移',hint:'迁移会改名（UID 按目标分类重新编号）并保留 question_id 与全部历史；展示板引用按 question_id 自动跟随。',body:`<div class="label-edit"><div class="label-edit-row"><label>科目</label><input class="input" id="mv-subject" list="mv-subject-list" value="${escapeAttr(item.subject||'')}"><datalist id="mv-subject-list">${subjects.map(s=>`<option value="${escapeAttr(s)}">`).join('')}</datalist></div><div class="label-edit-row"><label>分类</label><input class="input" id="mv-category" list="mv-category-list" value="${escapeAttr(item.category||'')}" placeholder="目标分类"><datalist id="mv-category-list">${categories.map(c=>`<option value="${escapeAttr(c)}">`).join('')}</datalist></div></div>`,focus:'#mv-category'});if(!res.ok)return;const subject=String(res.values['mv-subject']||'').trim()||item.subject;const category=String(res.values['mv-category']||'').trim();if(!category){uiToast('目标分类不能为空',{kind:'warn'});return}if(subject===item.subject&&category===item.category)return;try{const result=await api('/api/question/move',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid,subject,category})});delete QUESTION_CACHE[uid];await reloadData();if(typeof loadHist==='function')loadHist();uiToast(`${uid} 已迁移为 ${result.uid}`)}catch(error){uiToast(`迁移失败: ${error.message}`,{kind:'error'})}}
async function suspendQuestion(uid){const ok=await uiConfirm(`停用题目「${uid}」？`,{hint:'停用后不会进入复习调度、统计或数据分析；题目正文和历史记录会保留，可随时恢复。',okText:'停用'});if(!ok)return;try{await api('/api/question/suspend',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});await reloadData();if(typeof qvInvalidate==='function')await qvInvalidate(uid);if(typeof loadHist==='function')loadHist();uiToast(`${uid} 已停用`)}catch(error){uiToast(`停用失败: ${error.message}`,{kind:'error'})}}
async function resumeQuestion(uid){try{await api('/api/question/resume',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});await reloadData();if(typeof qvInvalidate==='function')await qvInvalidate(uid);if(typeof loadHist==='function')loadHist();uiToast(`${uid} 已恢复`)}catch(error){uiToast(`恢复失败: ${error.message}`,{kind:'error'})}}
async function deleteQuestion(uid){const ok=await uiConfirm(`删除题目「${uid}」？`,{hint:'这会删除题目的 Markdown 正文，并在 Ledger 中追加归档记录。历史反馈仍会保留，但题目正文无法通过 Ledger 恢复；附件图片不会删除。',okText:'删除',danger:true});if(!ok)return;try{await api('/api/question/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid})});delete QUESTION_CACHE[uid];if(typeof closeModal==='function')closeModal();await reloadData();if(typeof loadHist==='function')loadHist();uiToast(`${uid} 已删除`)}catch(error){uiToast(`删除失败: ${error.message}`,{kind:'error'})}}
async function openMarkdownEditor(uid){try{const result=await api(`/api/question/raw?uid=${encodeURIComponent(uid)}`);document.getElementById('md-edit-uid').textContent=result.uid;document.getElementById('md-edit-path').textContent=result.file_path||'';document.getElementById('md-edit-text').value=result.markdown||'';document.getElementById('md-edit-status').textContent='';document.getElementById('md-editor').dataset.uid=result.uid;document.getElementById('md-editor').classList.add('open')}catch(error){alert(`无法打开 Markdown: ${error.message}`)}}
function closeMarkdownEditor(){document.getElementById('md-editor').classList.remove('open')}
async function saveMarkdownEditor(){const modal=document.getElementById('md-editor');const uid=modal.dataset.uid;const markdown=document.getElementById('md-edit-text').value;const status=document.getElementById('md-edit-status');status.textContent='保存中...';try{await api('/api/question/markdown',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({uid,markdown})});delete QUESTION_CACHE[uid];status.innerHTML='<span style="color:var(--green)">已保存</span>';await reloadData();if(typeof qvInvalidate==='function')await qvInvalidate(uid);setTimeout(closeMarkdownEditor,350)}catch(error){status.innerHTML=`<span style="color:var(--red)">${escapeHtml(error.message)}</span>`}}

if(typeof module!=='undefined')module.exports={
  renderMdContent,renderMdInline,renderMdTable,splitMdTableRow,isMdTableSeparator,mdLineBreakMode,
};
