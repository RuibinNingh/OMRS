// === assets/core.js — 全局状态、api()、通用工具/筛选/Markdown 渲染 ===
let DATA=null,ALL_UIDS=[],SESSIONS=[],ACTIVE_FB_SESSION='';
// 题目详情缓存 QUESTION_CACHE / QUESTION_PENDING 归 assets/app/domain/question/mount.js（P6 起），旧代码经过渡桥读同名只读全局。

const LEDGER_TIME_ZONE_KEY='omrs-ledger-time-zone';

function ledgerTimeZone(){
  try{return localStorage.getItem(LEDGER_TIME_ZONE_KEY)||'local'}catch(e){return'local'}
}
function formatLedgerTime(value){
  const raw=String(value||'').trim();
  if(!raw)return'';
  // 旧记录没有时区偏移时无法可靠转换；保留其原有的本地墙上时间。
  if(!/(?:Z|[+-]\d{2}:\d{2})$/i.test(raw))return raw.replace('T',' ').slice(0,19);
  const date=new Date(raw);
  if(Number.isNaN(date.getTime()))return raw.replace('T',' ').slice(0,19);
  const options={year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'};
  const zone=ledgerTimeZone();
  if(zone!=='local')options.timeZone=zone;
  try{
    const parts=new Intl.DateTimeFormat('zh-CN',options).formatToParts(date);
    const values=Object.fromEntries(parts.filter(part=>part.type!=='literal').map(part=>[part.type,part.value]));
    return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
  }catch(e){return raw.replace('T',' ').slice(0,19)}
}

function parseLooseJson(text){let t=String(text??'').trim();const fence=t.match(/^```[a-zA-Z0-9]*\s*\n?([\s\S]*?)\n?```$/);if(fence)t=fence[1].trim();if(!t)throw new Error('内容为空');return JSON.parse(t)}
async function copyTextToClipboard(text){try{if(navigator.clipboard&&navigator.clipboard.writeText){await navigator.clipboard.writeText(text);return true}}catch(e){}try{const ta=document.createElement('textarea');ta.value=text;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.focus();ta.select();const ok=document.execCommand('copy');document.body.removeChild(ta);return ok}catch(e){return false}}
function looseBool(v){if(v===true||v===1||v==='1')return true;if(v===false||v===0||v==='0')return false;const s=String(v??'').trim().toLowerCase();if(['true','yes','y','对','correct','right'].includes(s))return true;if(['false','no','n','错','incorrect','wrong'].includes(s))return false;return null}

async function api(path,options){const response=await fetch(path,options);const isJson=(response.headers.get('Content-Type')||'').includes('application/json');const payload=isJson?await response.json():null;if(response.status===401&&typeof location!=='undefined'){location.assign('/login?next='+encodeURIComponent(location.pathname+location.search))}if(!response.ok){throw new Error(payload?.msg||payload?.error||`HTTP ${response.status}`)}return payload}
// Only actual user input refreshes a remote PIN session; background polling does not.
// Capture phase: scroll does not bubble, and workbench pages scroll inside inner containers.
if(typeof fetch==='function')fetch('/api/auth/session').then(r=>r.json()).then(state=>{if(!state.remote||!state.authenticated)return;let last=0;const active=()=>{const now=Date.now();if(now-last<60000)return;last=now;fetch('/api/auth/activity',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}).catch(()=>{})};['pointerdown','keydown','touchstart','wheel','scroll'].forEach(name=>document.addEventListener(name,active,{passive:true,capture:true}))}).catch(()=>{});

function escapeHtml(value){return String(value??'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;')}
function escapeAttr(value){return escapeHtml(value).replace(/`/g,'&#96;')}
function jsArg(value){return escapeHtml(JSON.stringify(String(value??'')))}
function asNumber(value,fallback=0){const n=Number(value);return Number.isFinite(n)?n:fallback}
function getItems(){return[...(DATA?.items||[])]}
function getItemByUid(uid){return getItems().find(item=>item.uid===uid)||null}
function clampNumber(value,min,max,fallback=0){const n=asNumber(value,fallback);return Math.max(min,Math.min(max,n))}
function parseReviewDate(value){if(!value)return null;const text=String(value).trim();const parts=text.includes('/')?text.split('/'):text.split('-');if(parts.length!==3)return null;const y=Number(parts[0]),m=Number(parts[1]),d=Number(parts[2]);if(!Number.isInteger(y)||!Number.isInteger(m)||!Number.isInteger(d))return null;const date=new Date(y,m-1,d);return date.getFullYear()===y&&date.getMonth()===m-1&&date.getDate()===d?date:null}
function daysSinceReview(value,fallback=30){const date=parseReviewDate(value);if(!date)return fallback;const today=new Date();const todayUtc=Date.UTC(today.getFullYear(),today.getMonth(),today.getDate());const dateUtc=Date.UTC(date.getFullYear(),date.getMonth(),date.getDate());return Math.max(0,Math.floor((todayUtc-dateUtc)/86400000))}
function decayMastery(mastery,days){const m=clampNumber(mastery,0,1,0);const d=Math.max(0,Math.floor(asNumber(days,0)));return m<=0?0:m*Math.exp(-d/(m*30+5))}
function isKilledItem(item){return asNumber(item.mastery,0)>=1||(item.tag||'').includes('已击杀')}
function getActiveSessionUidSet(){const active=new Set();(SESSIONS||[]).forEach(session=>{if((session.status||'active')!=='active')return;(session.uids||[]).forEach(uid=>active.add(uid))});return active}
function scoreScheduleCandidate(item){const mastery=clampNumber(item.mastery,0,1,0);const difficulty=clampNumber(item.difficulty,1,10,5);const days=daysSinceReview(item.last_review,30);const decayed=decayMastery(mastery,days);let priority=(1-decayed)*(difficulty/10)+(days/60)*.3;if((item.tag||'').includes('待攻克')&&mastery<.3)priority+=.5;return{item,priority,days,decayed}}
function setSelectOptions(id,values,placeholder){const el=document.getElementById(id);if(!el)return;const current=el.value;el.innerHTML=`<option value="">${placeholder}</option>`+values.map(value=>`<option value="${escapeAttr(value)}">${escapeHtml(value)}</option>`).join('');if(values.includes(current))el.value=current}
function updateUidList(){ALL_UIDS=getItems().map(item=>item.uid);document.getElementById('uid-list').innerHTML=ALL_UIDS.map(uid=>`<option value="${escapeAttr(uid)}">`).join('')}
function populateFilterOptions(){const items=getItems();const subjects=[...new Set(items.map(item=>item.subject).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));const categories=[...new Set(items.map(item=>item.category).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));const knowledgeTags=[...new Set(items.flatMap(item=>item.knowledge_tags||[]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'zh-CN'));['pick-subject','rec-subject'].forEach(id=>setSelectOptions(id,subjects,'全部科目'));['pick-category','rec-filter-category'].forEach(id=>setSelectOptions(id,categories,'全部分类'));['pick-ktag','rec-filter-ktag'].forEach(id=>setSelectOptions(id,knowledgeTags,'全部知识点'));if(typeof renderLabelFilterOptions==='function')renderLabelFilterOptions()}
function getFieldValue(ids){for(const id of ids){const el=document.getElementById(id);if(el)return el.value}return''}
function getFilterState(prefix){const text=(getFieldValue([`${prefix}-search`,`${prefix}-filter-search`])||'').trim().toLowerCase();const subject=getFieldValue([`${prefix}-subject`,`${prefix}-filter-subj`]);const category=getFieldValue([`${prefix}-category`,`${prefix}-filter-category`]);const tag=getFieldValue([`${prefix}-tag`,`${prefix}-filter-tag`]);const knowledgeTag=getFieldValue([`${prefix}-ktag`,`${prefix}-filter-ktag`]);const labels=typeof selectedLabelNamesFor==='function'?selectedLabelNamesFor(prefix):String(getFieldValue([`${prefix}-filter-labels`,`${prefix}-labels`])||'').split('|').map(v=>v.trim()).filter(Boolean);const labelMode=getFieldValue([`${prefix}-label-mode`])||'any';const difficultyMin=asNumber(getFieldValue([`${prefix}-diff-min`,`${prefix}-filter-diff-min`]),0);const difficultyMax=asNumber(getFieldValue([`${prefix}-diff-max`,`${prefix}-filter-diff-max`]),10)||10;const masteryMinRaw=getFieldValue([`${prefix}-mastery-min`,`${prefix}-filter-mastery-min`]);const masteryMaxRaw=getFieldValue([`${prefix}-mastery-max`,`${prefix}-filter-mastery-max`]);const masteryMin=masteryMinRaw===''||masteryMinRaw==null?null:Math.max(0,Math.min(100,asNumber(masteryMinRaw,0)))/100;const masteryMax=masteryMaxRaw===''||masteryMaxRaw==null?null:Math.max(0,Math.min(100,asNumber(masteryMaxRaw,100)))/100;const dueFilter=getFieldValue([`${prefix}-filter-due`,`${prefix}-due`]);const suspended=getFieldValue([`${prefix}-filter-suspended`]);const sort=getFieldValue([`${prefix}-sort`,`${prefix}-filter-sort`])||'mastery-asc';return{text,subject,category,tag,knowledgeTag,labels,labelMode,difficultyMin,difficultyMax,masteryMin,masteryMax,dueFilter,suspended,sort}}
function getDueDays(item){const dueDate=item.due_date;if(!dueDate)return null;const d=parseReviewDate(dueDate);if(!d)return null;const today=new Date();const todayUtc=Date.UTC(today.getFullYear(),today.getMonth(),today.getDate());const dueUtc=Date.UTC(d.getFullYear(),d.getMonth(),d.getDate());return Math.floor((dueUtc-todayUtc)/86400000)}
function formatDueInfo(dueDays){if(dueDays===null||dueDays===undefined)return'<span style="color:var(--fg3)">—</span>';if(dueDays<0)return`<span style="color:var(--red);font-weight:600">逾期${Math.abs(dueDays)}天</span>`;if(dueDays===0)return`<span style="color:var(--yellow);font-weight:600">今日到期</span>`;if(dueDays<=3)return`<span style="color:var(--yellow)">${dueDays}天后</span>`;if(dueDays<=7)return`<span style="color:var(--blue)">${dueDays}天后</span>`;return`<span style="color:var(--fg3)">${dueDays}天后</span>`}function filterItems(items,filters){let result=[...items];if(filters.suspended!=='all'&&filters.suspended!=='suspended')result=result.filter(item=>!item.suspended);else if(filters.suspended==='suspended')result=result.filter(item=>item.suspended);if(filters.text){result=result.filter(item=>[item.uid,item.subject,item.category,item.tag,...(item.knowledge_tags||[]),...(item.labels||[])].join(' ').toLowerCase().includes(filters.text))}if(filters.subject)result=result.filter(item=>item.subject===filters.subject);if(filters.category)result=result.filter(item=>item.category===filters.category);if(filters.tag)result=result.filter(item=>(item.tag||'').includes(filters.tag));if(filters.knowledgeTag)result=result.filter(item=>(item.knowledge_tags||[]).includes(filters.knowledgeTag));if(filters.labels?.length){result=result.filter(item=>{const values=new Set(item.labels||[]);return filters.labelMode==='all'?filters.labels.every(label=>values.has(label)):filters.labels.some(label=>values.has(label))})}result=result.filter(item=>asNumber(item.difficulty,0)>=filters.difficultyMin&&asNumber(item.difficulty,0)<=(filters.difficultyMax||10));if(filters.masteryMin!=null)result=result.filter(item=>asNumber(item.mastery,0)>=filters.masteryMin);if(filters.masteryMax!=null)result=result.filter(item=>asNumber(item.mastery,0)<=filters.masteryMax);if(filters.dueFilter){result=result.filter(item=>{const dueDays=getDueDays(item);if(dueDays===null)return false;switch(filters.dueFilter){case'overdue':return dueDays<0;case'today':return dueDays===0;case'3days':return dueDays>=0&&dueDays<=3;case'7days':return dueDays>=0&&dueDays<=7;case'future':return dueDays>0;default:return true}})}switch(filters.sort){case'mastery-desc':result.sort((a,b)=>asNumber(b.mastery,0)-asNumber(a.mastery,0));break;case'diff-desc':result.sort((a,b)=>asNumber(b.difficulty,0)-asNumber(a.difficulty,0));break;case'diff-asc':result.sort((a,b)=>asNumber(a.difficulty,0)-asNumber(b.difficulty,0));break;case'date-desc':result.sort((a,b)=>(b.last_review||'').localeCompare(a.last_review||''));break;case'due-asc':result.sort((a,b)=>(getDueDays(a)??999)-(getDueDays(b)??999));break;case'due-desc':result.sort((a,b)=>(getDueDays(b)??-999)-(getDueDays(a)??-999));break;default:result.sort((a,b)=>asNumber(a.mastery,0)-asNumber(b.mastery,0))}return result}

// 练习记录（parseQHistory / qRecordsFromDetail / qHistoryStats / qStreakHtml）已迁到 assets/app/domain/question/records.js（P5），
// 旧代码经过渡桥拿到同名全局。

// === 轻量 UI：toast / 对话框 / 输入框 / 确认框（替代 alert / prompt / confirm；v1.14.0）===
// v1.20.0 起转调 assets/app/ui/（全站唯一一套，见 assets/app/legacy-bridge.js）；模块脚本晚于经典脚本执行，
// 桥装好之前的调用先进 globalThis.__omrsUiPending 队列，装好后按顺序补发。签名与返回值不变。
// uiToast(text, {kind:'ok'|'warn'|'error'|'info', actions:[{label, onClick}], duration})；不传 kind 为成功样式
// uiDialog({title, hint, body(html), okText, cancelText, danger, focus}) → Promise<{ok, values:{id:value}}>
function uiBridge(run){const ui=globalThis.__omrsUi;if(ui)return run(ui);return new Promise(resolve=>{(globalThis.__omrsUiPending||(globalThis.__omrsUiPending=[])).push(u=>resolve(run(u)))})}
function uiToast(text,options={}){uiBridge(ui=>ui.toast(text,options))}
function uiDialog(spec={}){return uiBridge(ui=>ui.dialog(spec))}
function uiPrompt(title,value='',options={}){return uiBridge(ui=>ui.prompt(title,value,options))}
function uiConfirm(title,options={}){return uiBridge(ui=>ui.confirm(title,options))}

if(typeof module!=='undefined')module.exports={parseReviewDate};
