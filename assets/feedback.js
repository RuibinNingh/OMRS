// === assets/feedback.js — 反馈录入工作台：题目列表 / 题目视图 / 判定面板 ===
// 布局与即时练习的 .inst-work 同源：左列表、中题目、右判定。题目内容交给 qview 渲染，
// 因此录反馈时可以直接看题、就地编辑，不必来回切页。
// 提交契约不变：仍是 {uid, sub_score, is_correct, note}。

let FB_CURSOR = 0;        // 当前选中的 rail 条目下标
let FB_STAGE_UID = '';    // 舞台上正在显示的 uid，用来避免重复重绘题目

function sessionUniqueUids(session){const seen=new Set();return (session?.uids||[]).map(uid=>String(uid||'').trim()).filter(uid=>uid&&!seen.has(uid)&&seen.add(uid))}
function fbSessionProgress(session){const all=sessionUniqueUids(session);const available=new Set((session?.feedback_uids||[]).map(uid=>String(uid||'').trim()));const feedback_uids=all.filter(uid=>available.has(uid));const pending_uids=all.filter(uid=>!available.has(uid));return {total:all.length,feedback_uids,pending_uids,feedback_count:feedback_uids.length,pending_count:pending_uids.length,complete:all.length>0&&pending_uids.length===0}}
function fbSessionPositions(session){return new Map(sessionUniqueUids(session).map((uid,index)=>[uid,index+1]))}
function fbRowsForSession(session){const positions=fbSessionPositions(session);return fbSessionProgress(session).pending_uids.map((uid,index)=>({id:Date.now()+index,uid,number:positions.get(uid)||index+1,score:5,correct:null,note:'',scoreTouched:false}))}
function fbRowsForSubmit(rows){const ready=[];const pending=[];(rows||[]).forEach(row=>row?.correct===true||row?.correct===false?ready.push(row):pending.push(row));return {ready,pending}}

// rail 条目：Session 模式下显示「全部题目」（含已录入），序号沿用 Session 原始顺序；
// 手动 / 导入模式下就是 fbRows 本身。recorded=true 的条目只读。
function fbRailEntries(session,rows){
  const list=rows||[];
  const rowIndexByUid=new Map();
  list.forEach((row,index)=>{const uid=String(row?.uid||'').trim();if(uid&&!rowIndexByUid.has(uid))rowIndexByUid.set(uid,index)});
  if(!session){
    return list.map((row,index)=>({uid:String(row?.uid||'').trim(),number:asNumber(row?.number,0)||index+1,recorded:false,index}));
  }
  const positions=fbSessionPositions(session);
  const recorded=new Set(fbSessionProgress(session).feedback_uids);
  const entries=sessionUniqueUids(session).map(uid=>({
    uid,
    number:positions.get(uid)||0,
    recorded:recorded.has(uid),
    index:rowIndexByUid.has(uid)?rowIndexByUid.get(uid):-1,
  }));
  // 导入或手动添加、但不属于本 Session 的行仍要出现在列表末尾
  list.forEach((row,index)=>{
    const uid=String(row?.uid||'').trim();
    if(uid&&positions.has(uid))return;
    entries.push({uid,number:entries.length+1,recorded:false,index,extra:true});
  });
  return entries;
}

function fbActiveSession(){return ACTIVE_FB_SESSION&&Array.isArray(SESSIONS)?SESSIONS.find(session=>session.session_id===ACTIVE_FB_SESSION)||null:null}
function fbEntries(){return fbRailEntries(fbActiveSession(),fbRows)}
function fbFirstOpenIndex(entries){const at=entries.findIndex(entry=>!entry.recorded&&entry.index>=0&&fbRows[entry.index]?.correct==null);return at>=0?at:entries.findIndex(entry=>!entry.recorded)}
function fbSetCursor(index){const entries=fbEntries();if(!entries.length){FB_CURSOR=0;return}FB_CURSOR=Math.max(0,Math.min(entries.length-1,asNumber(index,0)))}
function fbGo(index){fbSetCursor(index);fbRenderRail();fbRenderPanel();fbRenderStage()}
function fbStep(delta){if(!fbEntries().length)return;fbGo(FB_CURSOR+delta)}
function fbNextOpen(){const entries=fbEntries();if(!entries.length)return;for(let step=1;step<=entries.length;step++){const at=(FB_CURSOR+step)%entries.length;const entry=entries[at];if(!entry.recorded&&entry.index>=0&&fbRows[entry.index]?.correct==null){fbGo(at);return}}}
function fbCurrentRow(){const entry=fbEntries()[FB_CURSOR];return entry&&!entry.recorded&&entry.index>=0&&fbRows[entry.index]?{entry,index:entry.index,row:fbRows[entry.index]}:null}

async function onFbSessionChange(clearResults=true){
  const sessionId=document.getElementById('fb-session-picker').value;
  ACTIVE_FB_SESSION=sessionId;
  const session=sessionId?SESSIONS.find(item=>item.session_id===sessionId):null;
  fbRows=session?fbRowsForSession(session):[];
  FB_CURSOR=0;FB_STAGE_UID='';
  fbRenderSessionInfo();
  const open=fbFirstOpenIndex(fbEntries());
  fbGo(open>=0?open:0);
  if(clearResults)fbClearResults();
}

function fbRenderSessionInfo(){
  const info=document.getElementById('fb-session-info');
  if(!info)return;
  const session=fbActiveSession();
  if(!session){info.textContent=ACTIVE_FB_SESSION?`已导入 ${fbRows.length} 题（Session ${ACTIVE_FB_SESSION} 不在列表中）`:'';return}
  const progress=fbSessionProgress(session);
  info.innerHTML=`<strong>${progress.feedback_count}/${progress.total}</strong> 已录入 · ${progress.pending_count?`还剩 <strong>${progress.pending_count}</strong> 题待录入`:'本 Session 已全部录入'}`;
}

function addFbRow(uid=''){
  fbRows.push({id:Date.now()+Math.random(),uid,score:5,correct:null,note:'',scoreTouched:false});
  const at=fbEntries().findIndex(entry=>entry.index===fbRows.length-1);
  fbGo(at>=0?at:0);
}

// === 渲染层拆三块：点「对 / 错」只重绘列表行与判定面板，题目 DOM 与 KaTeX 不动 ===
function fbMarkHtml(entry){
  if(entry.recorded)return '<span class="fb-mk done">✔</span>';
  const row=entry.index>=0?fbRows[entry.index]:null;
  if(row?.correct===true)return '<span class="fb-mk ok">✓</span>';
  if(row?.correct===false)return '<span class="fb-mk no">✗</span>';
  return '<span class="fb-mk up"></span>';
}
function fbRailRowClass(entry,at){
  const classes=['fb-railrow'];
  if(at===FB_CURSOR)classes.push('is-current');
  if(entry.recorded)classes.push('is-done');
  else{
    const row=entry.index>=0?fbRows[entry.index]:null;
    if(row?.correct===true)classes.push('ok');
    else if(row?.correct===false)classes.push('no');
  }
  return classes.join(' ');
}

function fbRenderRail(){
  const rail=document.getElementById('fb-rail');
  if(!rail)return;
  const entries=fbEntries();
  fbSetCursor(FB_CURSOR);
  if(!entries.length){
    rail.innerHTML=`<div class="empty-inline">${ACTIVE_FB_SESSION?'本 Session 已全部录入。':'点「＋ 添加行」或先选择一个 Session。'}</div>`;
    return;
  }
  const items=(typeof getItems==='function')?getItems():[];
  const metaOf=uid=>{const q=items.find(x=>x.uid===uid);return q?`${q.subject||''} · ${q.category||''}`:'—'};
  rail.innerHTML=entries.map((entry,at)=>`<button type="button" class="${fbRailRowClass(entry,at)}" data-fb-go="${at}" data-fb-uid="${escapeAttr(entry.uid)}">
    <span class="fb-index">${entry.number||at+1}</span>
    <span class="fb-railmain"><strong>${escapeHtml(entry.uid||'（待填 UID）')}</strong><small>${escapeHtml(entry.uid?metaOf(entry.uid):'新增行')}</small></span>
    ${fbMarkHtml(entry)}
  </button>`).join('');
  const current=rail.querySelector('.fb-railrow.is-current');
  if(current&&typeof current.scrollIntoView==='function')current.scrollIntoView({block:'nearest'});
}

// 只补一行的状态，避免整块 innerHTML（滑杆焦点与滚动位置都保得住）
function fbPatchRailRow(at){
  const node=document.querySelector(`#fb-rail .fb-railrow[data-fb-go="${at}"]`);
  const entry=fbEntries()[at];
  if(!node||!entry){fbRenderRail();return}
  node.className=fbRailRowClass(entry,at);
  const mark=node.querySelector('.fb-mk');
  if(mark)mark.outerHTML=fbMarkHtml(entry);
}

function fbTallyHtml(){
  const total=fbRows.length;
  if(!total)return '';
  const ok=fbRows.filter(row=>row.correct===true).length;
  const no=fbRows.filter(row=>row.correct===false).length;
  return `<div class="fb-tally2">
    <div class="fb-tally-st"><span class="g">对 ${ok}</span><span class="r">错 ${no}</span><span class="u">未判 ${total-ok-no}</span></div>
    <div class="fb-tally-bar"><div style="width:${ok/total*100}%;background:var(--green)"></div><div style="width:${no/total*100}%;background:var(--red)"></div></div>
    <div class="fb-tally-sub">本批共 ${total} 题</div>
  </div>`;
}

function fbCurrentQuestion(row){
  return row&&typeof getItemByUid==='function'?getItemByUid(String(row.uid||'').trim()):null;
}
function fbLabelControlsHtml(row){
  const item=fbCurrentQuestion(row);
  if(!item)return'<div class="fb-labels-hint">填写有效 UID 后可编辑标记。</div>';
  const current=new Set(item.labels||[]);
  const recent=(Array.isArray(LABELS)?LABELS:[]).slice(0,4);
  const quick=recent.map(label=>`<button type="button" class="fb-label-quick ${current.has(label.name)?'on':''}" data-fb-act="label" data-fb-label="${escapeAttr(label.name)}">${lblChip(label)}</button>`).join('');
  return`<div class="fb-labels"><div class="fb-labels-head"><span>标记</span><button type="button" class="btn sm ghost" data-fb-act="labels">＋ 编辑标记</button></div><div class="fb-labels-list">${lblChips(item.labels||[],{lg:true})||'<span class="hint">暂无标记</span>'}</div>${quick?`<div class="fb-labels-quick">${quick}<span class="hint">最近标记，点击切换</span></div>`:''}</div>`;
}

function fbRenderPanel(){
  const panel=document.getElementById('fb-panel');
  if(!panel)return;
  const entries=fbEntries();
  fbSetCursor(FB_CURSOR);
  const entry=entries[FB_CURSOR];
  const submit='<button class="btn primary fb-submit" id="fb-submit" data-fb-act="submit">提交反馈</button>';
  const hint='<div class="fb-keyhint">J/K 切题 · 1 对 2 错 · 0–9 给分 · E 编辑 · ⌘/Ctrl+V 读答题卡 · ⌘/Ctrl+↵ 提交</div>';
  if(!entry){
    panel.innerHTML=`<div class="fb-panel-head">判定</div><div class="empty-inline">没有待判定的题目。</div>${fbTallyHtml()}${submit}${hint}`;
    return;
  }
  const head=`<div class="fb-panel-head">第 ${entry.number||FB_CURSOR+1} 题<span class="fb-panel-uid">${escapeHtml(entry.uid||'待填 UID')}</span></div>`;
  if(entry.recorded){
    panel.innerHTML=`${head}<div class="fb-readonly">本题已录入反馈。如需修正请到「数据复盘 → 历史记录」操作，不要重复提交。</div>${fbTallyHtml()}${submit}${hint}`;
    return;
  }
  const row=entry.index>=0?fbRows[entry.index]:null;
  if(!row){panel.innerHTML=`${head}<div class="empty-inline">这一行已被移除。</div>${fbTallyHtml()}${submit}${hint}`;return}
  const uidField=(!fbActiveSession()||entry.extra||!entry.uid)
    ? `<label class="fb-field"><span>UID</span><input class="input" list="uid-list" value="${escapeAttr(row.uid)}" data-fb-act="uid" placeholder="输入或选择 UID"></label>`
    : '';
  panel.innerHTML=`${head}
    ${uidField}
    <div class="fb-toggle fb-toggle-wide">
      <span class="${row.correct===true?'active-correct':''}" data-fb-act="verdict" data-fb-value="1">✓ 对</span>
      <span class="${row.correct===false?'active-wrong':''}" data-fb-act="verdict" data-fb-value="0">✗ 错</span>
    </div>
    <div class="fb-score"><span>主观分</span><input type="range" min="0" max="10" value="${row.score}" data-fb-act="score"><b id="fb-score-val">${row.score}</b></div>
    <label class="fb-field"><span>备注</span><input class="input" value="${escapeAttr(row.note)}" data-fb-act="note" placeholder="页码 / 错因（可选）"></label>
    ${fbLabelControlsHtml(row)}
    ${row.correct===false&&row.uid?'<button class="btn sm fb-board-add" data-fb-act="board" data-board-hint>📋 加入展示板</button>':''}
    <button class="btn sm danger fb-drop" data-fb-act="drop">移除此行</button>
    ${fbTallyHtml()}${submit}${hint}`;
}

async function fbToggleLabel(name){
  const current=fbCurrentRow();
  const item=fbCurrentQuestion(current?.row);
  if(!item||!name)return;
  const labels=new Set(item.labels||[]);
  labels.has(name)?labels.delete(name):labels.add(name);
  await saveQuestionLabels(item.uid,[...labels]);
  fbRenderPanel();
}
function fbOpenLabels(){
  const current=fbCurrentRow();
  const item=fbCurrentQuestion(current?.row);
  if(item&&typeof openLabelPicker==='function')openLabelPicker(item.uid,document.querySelector('[data-fb-act="labels"]'));
}

async function fbRenderStage(){
  const stage=document.getElementById('fb-stage');
  if(!stage)return;
  const entries=fbEntries();
  const uid=entries[FB_CURSOR]?.uid||'';
  if(!uid){
    FB_STAGE_UID='';
    stage.innerHTML=`<div class="empty-inline">${entries.length?'先填写这一行的 UID，就能在这里看到题目。':'选择一个 Session 或添加一行后，这里显示题面与答案。'}</div>`;
    return;
  }
  if(uid===FB_STAGE_UID&&stage.querySelector('.qv'))return;
  FB_STAGE_UID=uid;
  await qvRender(stage,uid,{layout:'split',actions:['edit','board','labels','suspend','open']});
}

// 保留 renderFb 这个名字：onFbSessionChange / importFeedbackJson / addFbRow / submitFb 都在调它
function renderFb(){fbRenderRail();fbRenderPanel();fbRenderStage()}

function fbSetVerdict(index,correct){
  const row=fbRows[index];
  if(!row)return;
  row.correct=correct;
  if(!row.scoreTouched)row.score=correct?9:4;   // 与 importFeedbackJson 的 correct?10:4 同一心智
  fbPatchRailRow(FB_CURSOR);
  fbRenderPanel();                              // 注意：不重绘 stage
}
function fbSetScore(index,value){
  const row=fbRows[index];
  if(!row)return;
  row.score=Math.round(clampNumber(value,0,10,5));
  row.scoreTouched=true;
  const label=document.getElementById('fb-score-val');
  if(label)label.textContent=row.score;
}

function fbBindPanel(){
  const panel=document.getElementById('panel-feedback');
  if(!panel||panel.dataset.fbBound==='1')return;
  panel.dataset.fbBound='1';
  panel.addEventListener('click',event=>{
    const go=event.target.closest('[data-fb-go]');
    if(go){fbGo(asNumber(go.dataset.fbGo,0));return}
    const control=event.target.closest('[data-fb-act]');
    if(!control)return;
    const action=control.dataset.fbAct;
    if(action==='submit'){submitFb();return}
    const current=fbCurrentRow();
    if(action==='labels'){fbOpenLabels();return}
    if(action==='label'){fbToggleLabel(control.dataset.fbLabel);return}
    if(action==='board'){if(current?.row?.uid&&typeof boardQuickAdd==='function')boardQuickAdd(current.row.uid,{anchor:button,direct:event.shiftKey});return}
    if(!current)return;
    if(action==='verdict')fbSetVerdict(current.index,control.dataset.fbValue==='1');
    else if(action==='drop'){fbRows.splice(current.index,1);FB_STAGE_UID='';renderFb()}
  });
  panel.addEventListener('input',event=>{
    const control=event.target.closest('[data-fb-act]');
    if(!control)return;
    const current=fbCurrentRow();
    if(!current)return;
    if(control.dataset.fbAct==='score')fbSetScore(current.index,control.value);
    else if(control.dataset.fbAct==='note')current.row.note=control.value;
  });
  panel.addEventListener('change',event=>{
    if(!event.target.closest('[data-fb-act="uid"]'))return;
    const current=fbCurrentRow();
    if(!current)return;
    current.row.uid=event.target.value.trim();
    FB_STAGE_UID='';
    renderFb();
  });
}

// 键盘流：这个页面每天用，值得配快捷键。全部在焦点不在输入控件时才生效。
function fbHandleKey(event){
  const panel=document.getElementById('panel-feedback');
  if(!panel||!panel.classList.contains('active'))return;
  // 结果弹窗盖在上面时只认 Escape，别让 J/K/1/2 打到后面的判定面板
  if(document.getElementById('fb-result-modal')?.classList.contains('open')){
    if(event.key==='Escape'){event.preventDefault();fbCloseResults()}
    return;
  }
  if(document.getElementById('modal')?.classList.contains('open'))return;
  if(document.getElementById('md-editor')?.classList.contains('open'))return;
  if((event.metaKey||event.ctrlKey)&&event.key==='Enter'){event.preventDefault();submitFb();return}
  if(event.metaKey||event.ctrlKey||event.altKey)return;
  if(event.target.closest?.('input,textarea,select'))return;
  const key=event.key;
  const current=fbCurrentRow();
  if(key==='j'||key==='J'||key==='ArrowDown'){event.preventDefault();fbStep(1)}
  else if(key==='k'||key==='K'||key==='ArrowUp'){event.preventDefault();fbStep(-1)}
  else if(key==='1'&&current){event.preventDefault();fbSetVerdict(current.index,true)}
  else if(key==='2'&&current){event.preventDefault();fbSetVerdict(current.index,false)}
  else if(/^[0-9]$/.test(key)&&current&&current.row.correct!=null){event.preventDefault();fbSetScore(current.index,Number(key));fbRenderPanel()}
  else if(key==='Enter'){event.preventDefault();fbNextOpen()}
  else if((key==='e'||key==='E')&&current&&current.row.uid&&typeof openMarkdownEditor==='function'){event.preventDefault();openMarkdownEditor(current.row.uid)}
}

function resetFeedbackForm(){fbRows=[];ACTIVE_FB_SESSION='';FB_CURSOR=0;FB_STAGE_UID='';const picker=document.getElementById('fb-session-picker');if(picker)picker.value='';const info=document.getElementById('fb-session-info');if(info)info.textContent='';renderFb()}
function buildFeedbackAiPrompt(){const selectedRows=fbRows.filter(row=>(row.uid||'').trim());const sessionLine=ACTIVE_FB_SESSION?`当前 Session_ID：${ACTIVE_FB_SESSION}`:'当前未选择 Session；如果我没有另行说明，请输出空 session_id。';const scoped=selectedRows.length?selectedRows.map((row,i)=>`${i+1}. ${row.uid}`).join('\n'):getItems().slice(0,200).map((item,i)=>`${i+1}. ${item.uid}（${item.subject||''}/${item.category||''}）`).join('\n');return ['你是 OMRS 错题复习反馈整理助手。我会给你一份纸面批改结果、口述复盘、表格或截图内容。请只把它整理成 OMRS 可导入的反馈 JSON，不要解释。','','规则：','1. 每条反馈必须对应一个准确 UID；如果无法确定 UID，就不要输出该条。','2. is_correct 只能是 true 或 false。答对/全对/正确=true；答错/错误/不会/漏做=false。','3. sub_score 是 0-10 的整数。未给分时：答对默认 10，答错默认 4；明显完全不会可给 0-2。','4. note 写简短备注，如页码、错因、计算失误；没有就空字符串。','5. 只输出一个 JSON 对象，可被 JSON.parse 直接解析。不要 Markdown 代码块，不要多余文字。','',sessionLine,'','可用 UID 清单：',scoped||'（暂无预置 UID；请按我提供的 UID 输出）','','输出格式：','{"type":"omrs-feedback","version":1,"session_id":"","items":[{"uid":"","is_correct":true,"sub_score":10,"note":""}]}'].join('\n')}
async function copyFeedbackAiPrompt(){const ok=await copyTextToClipboard(buildFeedbackAiPrompt());const st=document.getElementById('fb-prompt-status');if(st)st.innerHTML=ok?'<span style="color:var(--green)">✓ 已复制。把批改结果发给 AI，要求它只返回反馈 JSON。</span>':'<span style="color:var(--red)">✕ 复制失败，请检查剪贴板权限</span>'}
// ════════════════════════════════════════════════════════════════════
// 答题卡扫描（OMR）JSON → 自动填写（v1.11.0）
//
// 流程：OMR 扫完答题卡 → 在详情页复制 /api/v1/recognitions/{id}/result JSON →
//       本页「读剪贴板填写」（或直接 Ctrl/⌘+V）→ 逐题落到判定面板上。
// 只接受 result 端点的顶层协议：recognition_id/template_id/mode/status/questions/unresolved；
// 明确拒绝原始识别记录 items、裸数组和任何包装层，避免前端重复解释机器证据。
//
// 答题卡上只有题号，没有 UID。题号 → UID 的唯一依据是**当前 Session 的题目顺序**，
// 与 exporting.py 打印「第 N 题 [UID]」时用的 `enumerate(questions, 1)` 同一口径，
// 因此导入前必须先选中 Session。注意：导出后又把某道题停用，会让它之后的题号整体前移，
// 此时纸面题号与 Session 顺序不再对齐——填完务必对着中栏题面核一遍再提交。
//
// 判定原则与 OMR 项目一致：**不做静默降级**。`unresolved` 命中的题一律不猜，
// 字段与状态写进备注，留给三栏工作台人工处理。
// ════════════════════════════════════════════════════════════════════

// Anki 版式四档 → OMRS 的 (is_correct, sub_score)。按 SM-2 口径：Again 是失败，
// Hard/Good/Easy 都算答出来了，只是分数递减。high_score_threshold 默认 7，
// 所以 G=8 计入「高分答对」，H=5 落在「磨合中」。
const OMR_ANKI_GRADES={E:{correct:true,score:10},G:{correct:true,score:8},H:{correct:true,score:5},A:{correct:false,score:1}};
const OMR_NOTE_PREFIX='OMR：';

// 本段刻意不用 core.js 的 asNumber：解析器要能在 node 侧单独 require 出来测。
function omrInt(value,fallback){const n=Number(value);return Number.isFinite(n)?Math.round(n):fallback}
function omrScore(value){const n=Number(value);return Number.isFinite(n)?Math.max(0,Math.min(10,Math.round(n))):5}

// 正式复制入口：GET /api/v1/recognitions/{id}/result 的顶层结论协议。
function omrIsResultProtocol(data){
  return !!data&&typeof data==='object'&&!Array.isArray(data)
    &&Object.prototype.hasOwnProperty.call(data,'recognition_id')
    &&Object.prototype.hasOwnProperty.call(data,'template_id')
    &&Object.prototype.hasOwnProperty.call(data,'mode')
    &&Object.prototype.hasOwnProperty.call(data,'status')
    &&Array.isArray(data.questions)&&Array.isArray(data.unresolved);
}
function omrReadResultProtocol(record){
  const status=String(record.status||'').trim().toLowerCase();
  if(status==='failed')return {error:'这次识别是失败的，不导入。请回 OMR 查看识别详情。'};
  if(['uploaded','queued','processing'].includes(status))return {error:`这份扫描还没识别完（当前状态 ${status}），等 OMR 跑完后重新复制 /result JSON。`};
  const mode=String(record.mode||'').trim().toLowerCase();
  const unresolvedBySeq=new Map();
  record.unresolved.forEach(entry=>{
    const number=omrInt(entry?.seq,0);
    if(!(number>0))return;
    if(!unresolvedBySeq.has(number))unresolvedBySeq.set(number,[]);
    unresolvedBySeq.get(number).push(entry);
  });
  const questions=record.questions.map(entry=>{
    const number=omrInt(entry?.seq,0);
    const out={number,correct:null,score:null,scored:false,reason:'',note:''};
    const unresolved=unresolvedBySeq.get(number)||[];
    if(unresolved.length){
      out.reason=`待人工处理：${unresolved.map(item=>`${String(item?.field||`q${number}`)}（${String(item?.status||'unresolved')}）`).join('、')}`;
      return out;
    }
    if(mode==='omrs'){
      const result=String(entry?.result??'').trim().toUpperCase();
      if(result==='C')out.correct=true;
      else if(result==='W')out.correct=false;
      else out.reason=result?`对错结论「${result}」既不是 C 也不是 W`:'没有对错结论';
      if(entry?.level!=null&&String(entry.level).trim()!==''){
        out.score=omrScore(entry.level);out.scored=true;
      }
    }else if(mode==='anki'){
      const answer=String(entry?.answer??'').trim().toUpperCase();
      const grade=OMR_ANKI_GRADES[answer];
      if(grade){out.correct=grade.correct;out.score=grade.score;out.scored=true}
      else out.reason=answer?`读出「${answer}」，不是 E / G / H / A`:'没有 Anki 档位结论';
    }
    return out;
  }).filter(question=>question.number>0).sort((a,b)=>a.number-b.number);
  return {mode,status,questions,record};
}

// 一整张（或一叠）答题卡 → 逐题结论。只接受 OMR /result 顶层协议。
function omrReadSheet(data){
  if(!omrIsResultProtocol(data))return {error:'OMR 剪贴板导入只接受 /api/v1/recognitions/{id}/result 顶层协议（recognition_id/template_id/mode/status/questions/unresolved）；不接受旧 raw/items、裸数组或包装层协议。'};
  return omrReadResultProtocol(data);
}

function omrMergeNote(existing,text){
  const base=String(existing||'').trim();
  const add=`${OMR_NOTE_PREFIX}${text}`;
  if(!text)return base;
  if(base.includes(add))return base;
  return base?`${base} · ${add}`:add;
}

// 把逐题结论按 Session 顺序落到反馈行上。rows 是 fbRowsForSession() 的待录入行，
// 扫描没覆盖到的题原样留着（correct 仍为 null，submitFb 不会提交它们）。
function omrApplyToRows(rows,questions,sessionUids,recordedUids){
  const uids=(sessionUids||[]).map(uid=>String(uid||'').trim());
  const recorded=recordedUids instanceof Set?recordedUids:new Set(recordedUids||[]);
  const rowByUid=new Map();
  (rows||[]).forEach((row,index)=>{const uid=String(row?.uid||'').trim();if(uid&&!rowByUid.has(uid))rowByUid.set(uid,index)});
  const report={total:(questions||[]).length,filled:0,correct:0,wrong:0,manual:[],skippedRecorded:0,outOfRange:[],missingRow:[]};
  (questions||[]).forEach(question=>{
    const uid=uids[question.number-1]||'';
    if(!uid){report.outOfRange.push(question.number);return}
    if(recorded.has(uid)){report.skippedRecorded++;return}
    const index=rowByUid.get(uid);
    if(index==null){report.missingRow.push(question.number);return}
    const row=rows[index];
    if(question.correct==null){
      report.manual.push({number:question.number,uid,reason:question.reason||'需要人工判定'});
      row.note=omrMergeNote(row.note,question.reason);
      return;
    }
    row.correct=question.correct;
    row.score=question.scored?question.score:(question.correct?10:4);
    row.scoreTouched=true;
    if(question.note)row.note=omrMergeNote(row.note,question.note);
    report.filled++;
    if(question.correct)report.correct++;else report.wrong++;
  });
  return report;
}

function omrReportHtml(sheet,report,sessionCount){
  const headColor=report.filled?'var(--green)':'var(--yellow)';
  const headMark=report.filled?'✓':'⚠';
  const tail=report.filled?'。请对着中栏题面核一遍再提交。':'——没有一题能自动判定，看下面的原因。';
  const lines=[`<span style="color:${headColor}">${headMark} 读入答题卡 ${report.total} 题，自动填写 <strong>${report.filled}</strong> 题（对 ${report.correct} · 错 ${report.wrong}）${tail}</span>`];
  if(report.total&&report.outOfRange.length===report.total)lines.push(`<span style="color:var(--red)">这张卡上的题号没有一个落在本 Session（共 ${sessionCount} 题）里，多半是 Session 选错了，或者这张卡属于另一次导出。</span>`);
  if(report.missingRow.length)lines.push(`<span style="color:var(--fg3)">第 ${report.missingRow.join('、')} 题在本 Session 里找不到对应的待录入行，已忽略。</span>`);
  if(report.manual.length){
    const detail=report.manual.slice(0,8).map(entry=>`第 ${entry.number} 题（${escapeHtml(entry.uid)}）${escapeHtml(entry.reason)}`).join('；');
    const more=report.manual.length>8?`……共 ${report.manual.length} 题`:'';
    lines.push(`<span style="color:var(--yellow)">⚠ ${report.manual.length} 题没有自动判定，原因已写进各自的备注：${detail}${more}</span>`);
  }
  if(report.skippedRecorded)lines.push(`<span style="color:var(--fg3)">跳过 ${report.skippedRecorded} 题：本 Session 里已经录过反馈。</span>`);
  if(report.outOfRange.length)lines.push(`<span style="color:var(--yellow)">⚠ 第 ${report.outOfRange.join('、')} 题超出了本 Session 的题目数（共 ${sessionCount} 题），已忽略。答题卡的行数比 Session 多是正常的；如果不是，检查是不是选错了 Session。</span>`);
  if(sheet.status==='needs_review')lines.push('<span style="color:var(--fg3)">这次扫描在 OMR 侧仍是「待复核」。unresolved 题已留给人工；也可先在 OMR 纠错，再重新复制 /result JSON。</span>');
  if(sheet.mode==='custom')lines.push('<span style="color:var(--yellow)">这是通用（A/B/C/D）答题卡，纸面只有选项、没有对错，因此一题也无法自动判定。要自动填对错，请用 OMRS 版式的答题卡。</span>');
  return lines.map(line=>`<div style="margin-top:4px">${line}</div>`).join('');
}

// === 导入入口 =======================================================
// 三个入口共用一套解析：① 顶栏「读剪贴板填写」按钮 ② 反馈页里直接 Ctrl/⌘+V
// ③ 粘贴框 +「导入 JSON」。三者都同时接受答题卡扫描 JSON 和反馈 JSON。
function fbPayloadKind(data){
  if(data&&data.type==='omrs-questions')return 'questions';
  if(data&&Array.isArray(data.questions)&&data.questions.some(entry=>entry&&(entry.uid!=null||entry.question!=null)))return 'questions';
  if(data&&data.type==='omrs-feedback')return 'feedback';
  const list=Array.isArray(data)?data:(Array.isArray(data?.items)?data.items:(Array.isArray(data?.feedbacks)?data.feedbacks:null));
  if(Array.isArray(list)&&list.some(entry=>entry&&typeof entry==='object'&&(entry.uid!=null||entry.UID!=null)&&(entry.is_correct!==undefined||entry.correct!==undefined)))return 'feedback';
  return 'omr';
}

function fbImportOmrScan(data){
  const sheet=omrReadSheet(data);
  if(sheet.error)return {ok:false,message:`<span style="color:var(--red)">✕ ${escapeHtml(sheet.error)}</span>`};
  const session=fbActiveSession();
  if(!session)return {ok:false,message:'<span style="color:var(--yellow)">请先在上面选中这张答题卡对应的 Session：答题卡上只有题号，要靠 Session 的题目顺序才能对上 UID。</span>'};
  const sessionUids=sessionUniqueUids(session);
  const rows=fbRowsForSession(session);
  const report=omrApplyToRows(rows,sheet.questions,sessionUids,new Set(fbSessionProgress(session).feedback_uids));
  fbRows=rows;FB_CURSOR=0;FB_STAGE_UID='';
  const open=fbFirstOpenIndex(fbEntries());
  fbGo(open>=0?open:0);
  fbClearResults();
  fbRenderSessionInfo();
  return {ok:true,message:omrReportHtml(sheet,report,sessionUids.length)};
}

function fbImportAnyJson(data){
  const kind=fbPayloadKind(data);
  if(kind==='questions')return {ok:false,message:'<span style="color:var(--yellow)">这是题目 JSON；题目录入页已不再提供题目 JSON 队列导入。</span>'};
  if(kind==='feedback')return fbImportFeedbackPayload(data);
  return fbImportOmrScan(data);
}

function fbImportText(text,options){
  const status=document.getElementById('fb-json-status');
  const show=html=>{if(status)status.innerHTML=html};
  let data;
  try{data=parseLooseJson(text)}
  catch(error){show(`<span style="color:var(--red)">✕ ${options&&options.from==='clipboard'?'剪贴板里不是 JSON':'JSON 解析失败'}：${escapeHtml(error.message)}</span>`);return false}
  const result=fbImportAnyJson(data);
  show(result.message);
  if(result.ok&&options&&options.clearBox){const box=document.getElementById('fb-json');if(box)box.value=''}
  return result.ok;
}

async function fbReadClipboardAndFill(){
  const status=document.getElementById('fb-json-status');
  const details=document.querySelector('#panel-feedback .fb-import');
  if(details&&!details.open)details.open=true;      // 把状态行露出来，否则提示藏在折叠面板里
  if(!navigator.clipboard||!navigator.clipboard.readText){
    if(status)status.innerHTML='<span style="color:var(--yellow)">这个浏览器不允许直接读剪贴板（非 HTTPS / 非 localhost 打开时通常如此）。请在本页空白处直接按 Ctrl / ⌘ + V，或粘到下面的框里再点「导入 JSON」。</span>';
    return;
  }
  let text='';
  try{text=await navigator.clipboard.readText()}
  catch(error){
    if(status)status.innerHTML=`<span style="color:var(--red)">✕ 读剪贴板失败：${escapeHtml((error&&error.message)||String(error))}。可能需要在浏览器里允许「剪贴板」权限，或直接按 Ctrl / ⌘ + V。</span>`;
    return;
  }
  if(!String(text||'').trim()){
    if(status)status.innerHTML='<span style="color:var(--yellow)">剪贴板是空的。先在 OMR 的识别结果页复制 JSON 再回来。</span>';
    return;
  }
  fbImportText(text,{from:'clipboard'});
}

// 反馈页内直接 Ctrl/⌘+V：不需要剪贴板读权限，局域网 http 下也能用。
function fbHandlePaste(event){
  const panel=document.getElementById('panel-feedback');
  if(!panel||!panel.classList.contains('active'))return;
  if(event.target.closest?.('input,textarea,select'))return;          // 输入框里的粘贴照常
  if(document.getElementById('modal')?.classList.contains('open'))return;
  if(document.getElementById('md-editor')?.classList.contains('open'))return;
  if(document.getElementById('fb-result-modal')?.classList.contains('open'))return;
  const text=event.clipboardData?.getData('text/plain')||'';
  if(!String(text).trim())return;
  event.preventDefault();
  const details=panel.querySelector('.fb-import');
  if(details&&!details.open)details.open=true;
  fbImportText(text,{from:'clipboard'});
}

// === 从屏幕版或 AI 导入反馈 JSON（{type:"omrs-feedback", session_id, items:[{uid,is_correct,sub_score}]}）===
function importFeedbackJson(){const box=document.getElementById('fb-json');fbImportText(box?.value,{clearBox:true})}
function fbImportFeedbackPayload(data){
  const rawItems=Array.isArray(data)?data:(Array.isArray(data?.items)?data.items:(Array.isArray(data?.feedbacks)?data.feedbacks:[]));
  let rows=[];let skipped=0;
  rawItems.forEach((it,i)=>{const uid=it&&(it.uid??it.UID)!=null?String(it.uid??it.UID).trim():'';const correct=looseBool(it?.is_correct??it?.correct);if(!uid||correct===null){skipped++;return}rows.push({id:Date.now()+i,uid,score:Math.max(0,Math.min(10,Math.round(asNumber(it.sub_score??it.score,correct?10:4)))),correct,note:String(it?.note??'').trim(),scoreTouched:true})});
  const sid=String(data?.session_id||'').trim();const picker=document.getElementById('fb-session-picker');const info=document.getElementById('fb-session-info');let skippedRecorded=0;
  const matchedSession=sid&&SESSIONS.find(s=>s.session_id===sid);
  if(matchedSession){const pending=new Set(fbSessionProgress(matchedSession).pending_uids);const before=rows.length;rows=rows.filter(row=>pending.has(row.uid));skippedRecorded=before-rows.length;ACTIVE_FB_SESSION=sid;if(picker)picker.value=sid;if(info)info.innerHTML=`已导入 ${rows.length} 题 · 本 Session 还剩 ${pending.size} 题待录入`}
  else if(sid){ACTIVE_FB_SESSION=sid;if(picker)picker.value='';if(info)info.textContent=`已导入 ${rows.length} 题（该 Session 不在列表中，提交时仍按此 ID 写入历史）`}
  else{ACTIVE_FB_SESSION='';if(picker)picker.value='';if(info)info.textContent=`已导入 ${rows.length} 条作答（未关联 Session）`}
  if(!rows.length)return {ok:false,message:`<span style="color:var(--yellow)">${skippedRecorded?'导入内容中的题目已全部录入，无需重复提交。':'没有可导入的作答条目（需要 items: [{uid, is_correct, sub_score}]）'}</span>`};
  fbRows=rows;FB_CURSOR=0;FB_STAGE_UID='';fbGo(0);
  fbClearResults();
  return {ok:true,message:`<span style="color:var(--green)">✓ 已导入 ${rows.length} 条作答${skipped?`，跳过 ${skipped} 条无效`:''}${skippedRecorded?`，自动跳过 ${skippedRecorded} 条已录入`:''}。请核对后点「提交反馈」。</span>`};
}
// ════════════════════════════════════════════════════════════════════
// 提交结果：弹窗展示
//
// 以前直接写进页内 #fb-results。宽屏下 .panel.active 是整屏 flex 列，明细一多
// 就把三栏工作台挤矮，而且没有任何关闭入口，只能靠切 Session 才消失。现在明细
// 进 #fb-result-modal，页内只留一行状态和一个「查看本次结果」按钮。
// ════════════════════════════════════════════════════════════════════
let FB_LAST_RESULT=null;      // {rows, okCount, total, sessionId, at}

function fbResultRowsHtml(rows){
  if(!rows||!rows.length)return '<div class="empty-inline">这次没有返回任何处理结果。</div>';
  return rows.map(row=>{
    const ok=row.status==='ok';
    const labelClass=row.label==='已击杀'?'kill':row.label==='真不会'?'attack':'trap';
    const masterySummary=ok?`${(asNumber(row.old_mastery,0)*100).toFixed(0)}% → ${(asNumber(row.new_mastery,0)*100).toFixed(0)}%`:escapeHtml(row.msg||'失败');
    const sm2Info=ok&&row.new_interval!=null?` · Interval=${row.new_interval}d · Due=${row.new_due_date||'?'}`:'';
    const sourceInfo=ok&&row.source?` [${row.source==='due'?'到期':'熟练度'}]`:'';
    return `<div class="result-row ${ok?'ok':'err'}"><span style="font-weight:700;color:var(--accent2)">${escapeHtml(row.uid)}${sourceInfo}</span><span class="tag ${labelClass}">${escapeHtml(row.label||'')}</span><span style="font-family:'JetBrains Mono','Noto Sans SC',monospace;font-size:.76rem">${masterySummary}${sm2Info}</span></div>`;
  }).join('');
}

function fbResultMetaText(payload){
  if(!payload)return '';
  const parts=[`${payload.okCount}/${payload.total} 条写入成功`];
  const failed=asNumber(payload.total,0)-asNumber(payload.okCount,0);
  if(failed>0)parts.push(`${failed} 条失败`);
  if(payload.sessionId)parts.push(`Session ${payload.sessionId}`);
  if(payload.at)parts.push(payload.at);
  return parts.join(' · ');
}

// 传 payload = 记住这批新结果并弹出；不传 = 重新打开上一次的结果（状态行的按钮走这条）
function fbOpenResults(payload){
  if(payload)FB_LAST_RESULT=payload;
  const overlay=document.getElementById('fb-result-modal');
  const list=document.getElementById('fb-results');
  if(!overlay||!list||!FB_LAST_RESULT){fbSyncResultReopen();return}
  list.innerHTML=fbResultRowsHtml(FB_LAST_RESULT.rows);
  list.scrollTop=0;
  const meta=document.getElementById('fb-result-meta');
  if(meta)meta.textContent=fbResultMetaText(FB_LAST_RESULT);
  overlay.classList.add('open');
  fbSyncResultReopen();
  const okButton=document.getElementById('fb-result-ok');
  if(okButton&&typeof okButton.focus==='function')okButton.focus();
}

function fbCloseResults(){
  document.getElementById('fb-result-modal')?.classList.remove('open');
  fbSyncResultReopen();
}

// 换 Session / 重新导入：上一批结果已经不对应当前这批题了，连重开按钮一起收掉
function fbClearResults(){
  FB_LAST_RESULT=null;
  const list=document.getElementById('fb-results');
  if(list)list.innerHTML='';
  fbCloseResults();
}

function fbSyncResultReopen(){
  const button=document.getElementById('fb-result-reopen');
  if(button)button.hidden=!FB_LAST_RESULT;
}

async function submitFb(){if(!fbRows.length){uiToast(ACTIVE_FB_SESSION?'当前 Session 已没有待录入题目':'请先添加反馈条目',{kind:'warn'});return}const {ready:readyRows,pending:pendingRows}=fbRowsForSubmit(fbRows);if(!readyRows.length){uiToast(fbRows.length?'当前批次还没有完成判定，请至少点选一道题的「对」或「错」。':'请先添加反馈条目',{kind:'warn'});return}const seen=new Set();const duplicate=readyRows.find(row=>{const uid=(row.uid||'').trim();if(!uid||seen.has(uid))return true;seen.add(uid);return false});if(duplicate){uiToast(`UID「${duplicate.uid||'空白'}」重复或为空，请检查后再提交。`,{kind:'warn'});return}const currentSession=ACTIVE_FB_SESSION?SESSIONS.find(session=>session.session_id===ACTIVE_FB_SESSION):null;const alreadySubmitted=new Set(currentSession?.feedback_uids||[]);const repeat=readyRows.find(row=>alreadySubmitted.has((row.uid||'').trim()));if(repeat){uiToast(`题目「${repeat.uid}」已经录入过反馈，请不要重复提交。若要修正，请到「历史记录」中操作。`,{kind:'warn'});return}const feedbacks=readyRows.map(row=>({uid:row.uid,sub_score:row.score,is_correct:row.correct,note:row.note}));const button=document.getElementById('fb-submit');if(button){button.disabled=true;button.textContent='提交中...'}const sessionId=ACTIVE_FB_SESSION;let result;try{result=await api('/api/feedback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({feedbacks,session_id:sessionId||''})})}catch(error){const btn=document.getElementById('fb-submit');if(btn){btn.disabled=false;btn.textContent='提交反馈'}document.getElementById('fb-status').innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`;return}const okCount=(result.results||[]).filter(row=>row.status==='ok').length;document.getElementById('fb-status').innerHTML='<span style="color:var(--yellow)">✓ 提交成功，正在刷新 Session 进度…</span>';fbOpenResults({rows:result.results||[],okCount,total:feedbacks.length,sessionId,at:new Date().toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})});await reloadData();if(typeof qvInvalidateMany==='function')await qvInvalidateMany(feedbacks.map(row=>row.uid));await refreshSessions();if(sessionId){const picker=document.getElementById('fb-session-picker');if(picker)picker.value=sessionId;const updated=SESSIONS.find(session=>session.session_id===sessionId);const remaining=updated?fbSessionProgress(updated).pending_count:0;const nextInfo=remaining?`下次选择同一 Session 可继续剩余 ${remaining} 题`:'本 Session 已全部录入';document.getElementById('fb-status').innerHTML=`<span style="color:var(--green)">✓ 本次已提交 ${okCount}/${feedbacks.length} 条，${nextInfo}</span>`;await onFbSessionChange(false)}else{fbRows=pendingRows;FB_CURSOR=0;FB_STAGE_UID='';fbGo(0);const pendingInfo=pendingRows.length?`，${pendingRows.length} 道未判定题已保留`:'';document.getElementById('fb-status').innerHTML=`<span style="color:var(--green)">✓ 本次已提交 ${okCount}/${feedbacks.length} 条${pendingInfo}</span>`}}

if(typeof document!=='undefined'){
  document.addEventListener('keydown',fbHandleKey);
  document.addEventListener('paste',fbHandlePaste);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',fbBindPanel);
  else fbBindPanel();
}
if(typeof module!=='undefined')module.exports={
  sessionUniqueUids,fbSessionProgress,fbRowsForSession,fbRowsForSubmit,fbRailEntries,
  omrReadSheet,omrApplyToRows,omrMergeNote,fbPayloadKind,
};
