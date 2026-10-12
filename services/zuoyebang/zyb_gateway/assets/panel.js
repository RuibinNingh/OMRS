/* 不持久化管理员密码、调用密钥或设备凭据。 */
'use strict';
const $ = id => document.getElementById(id);
let csrf = '', flow = '', pageNumber = 1, hasMore = false;
const text = (tag, value, className='') => {const el=document.createElement(tag);el.textContent=String(value);if(className)el.className=className;return el;};
const when = value => value ? new Date(value*1000).toLocaleString('zh-CN', {hour12:false}) : '—';
function notice(message, error=false){$('notice').hidden=false;$('notice').textContent=message;$('notice').dataset.error=String(error);}
async function api(path, body){
  const options={credentials:'same-origin',headers:{'Accept':'application/json'},cache:'no-store'};
  if(body!==undefined){options.method='POST';options.headers['Content-Type']='application/json';options.headers['X-CSRF-Token']=csrf;options.body=JSON.stringify(body);}
  const response=await fetch('api/admin/'+path, options);
  const data=await response.json();
  if(!response.ok||data.status!=='ok'){
    if(response.status===401&&path!=='login')lock();
    throw new Error(data.msg||'请求失败');
  }
  return data;
}
async function run(button, task){button.disabled=true;try{await task();}catch(e){notice(e.message||'无法连接网关',true);}finally{button.disabled=['poll-qr','cancel-qr'].includes(button.id)&&!flow;}}
function lock(){csrf='';flow='';$('dashboard').hidden=true;$('logout').hidden=true;$('login-view').hidden=false;$('admin-password').value='';$('profile-json').value='';$('account-credential').value='';dismissKey();clearQr();$('key-list').replaceChildren();$('history-rows').replaceChildren();}
function dismissKey(){$('new-key-secret').value='';$('new-key').hidden=true;}
function clearQr(){$('qr-image').removeAttribute('src');$('qr-image').hidden=true;$('qr-box').hidden=true;flow='';}
function chooseTab(name){for(const node of document.querySelectorAll('[data-tab]'))node.classList.toggle('active',node.dataset.tab===name);for(const node of document.querySelectorAll('.tab-panel'))node.hidden=node.id!=='tab-'+name;}
function renderAccount(account){
  $('account-state').textContent=account.local_session_ready?(account.has_account_credential?'设备已配置 · 有账号凭据':'设备已配置 · 缺账号凭据'):'未配置';
  const stateName={valid:'已验证',invalid:'已确认失效',unknown:'未核对'};
  const kindName={ok:'成功',network:'网络失败（不是失效）',protocol:'协议错误',login_required:'账号失效',signing_session:'签名失效',upstream:'官方错误'};
  const obs=account.observations;const lines=[];
  for(const [key,label] of [['account','账号'],['signing','签名']]){
    const part=obs[key]||{};lines.push(label+'：'+(stateName[part.state]||'未知'));lines.push('最后成功：'+when(part.last_success_at));
    if(part.first_invalid_at)lines.push('首次失效：'+when(part.first_invalid_at)+'；此前成功：'+when(part.valid_until_after));
  }
  if(obs.events.length)lines.push('最近观察：\n'+obs.events.slice(-5).reverse().map(e=>when(e.at)+' / '+e.event+' / '+(kindName[e.kind]||e.kind)).join('\n'));
  $('observations').textContent=lines.join('\n');
}
async function loadAccount(){renderAccount((await api('account')).account);}
async function loadSettings(){const data=await api('settings');$('allow-external').checked=data.allow_external;$('access-state').textContent=data.allow_external?'已允许外部 · 鉴权必需':'仅本机 · 鉴权必需';const l=data.limits;$('limits').textContent=`每密钥 API ${l.api_per_minute} 次/分钟 · 搜题 ${l.search_per_minute} 次/分钟 · 全服务 ${l.search_daily_budget} 次/UTC日 · 搜题并发 ${l.search_concurrency}`;}
async function loadKeys(){
  const data=await api('keys');$('key-list').replaceChildren();const selected=$('history-key').value;$('history-key').replaceChildren();const all=text('option','全部密钥');all.value='';$('history-key').append(all);
  if(!data.keys.length)$('key-list').append(text('p','暂无调用密钥。先生成一个，再配置到客户端。','muted'));
  for(const key of data.keys){
    const row=text('article','','card key-row'), detail=text('div','');detail.append(text('strong',key.name),text('p',`${key.state==='active'?'有效':'已吊销'} · ${key.prefix}… · 指纹 ${key.fingerprint}`),text('code','ID '+key.id),text('p','创建 '+when(key.created_at)+' · 最近使用 '+when(key.last_used_at)));
    row.append(detail);if(key.state==='active'){const button=text('button','吊销');button.dataset.revoke=key.id;button.addEventListener('click',()=>run(button,async()=>{if(!confirm('吊销后客户端将立即无法使用，确认继续？'))return;await api('keys/revoke',{id:key.id});await loadKeys();notice('调用密钥已吊销');}));row.append(button);} $('key-list').append(row);
    const option=text('option',key.name+' / '+key.id);option.value=key.id;$('history-key').append(option);
  }
  $('history-key').value=selected;
}
async function loadHistory(){
  const query=new URLSearchParams({page:String(pageNumber),page_size:'20'});for(const [id,key] of [['history-source','source'],['history-result','result'],['history-key','key_id']])if($(id).value)query.set(key,$(id).value);
  const data=await api('history?'+query);hasMore=data.has_more;$('history-rows').replaceChildren();
  for(const row of data.items){const tr=document.createElement('tr');const values=[[when(row.time),row.action],[row.source==='local'?'本机 / local':'外部 / external','客户端 '+row.client_ip,'对端 '+row.peer_ip],[row.key_id||'—',row.method+' '+row.path],[row.result+' / '+row.http_status,row.latency_ms.toFixed(1)+' ms']];for(const lines of values){const td=document.createElement('td');for(const line of lines)td.append(text('div',line));tr.append(td);}$('history-rows').append(tr);}
  if(!data.items.length){const tr=document.createElement('tr'),td=text('td','没有匹配的请求记录');td.colSpan=4;tr.append(td);$('history-rows').append(tr);}
  $('history-page').textContent=`第 ${data.page} 页 · 共 ${data.total} 条`;$('previous-page').disabled=pageNumber<=1;$('next-page').disabled=!hasMore;
}
async function unlock(session){csrf=session.csrf_token;$('admin-password').value='';$('login-view').hidden=true;$('dashboard').hidden=false;$('logout').hidden=false;chooseTab('account');await Promise.all([loadAccount(),loadKeys(),loadSettings()]);await loadHistory();}
$('login-form').addEventListener('submit',event=>{event.preventDefault();run($('login-submit'),async()=>{const password=$('admin-password').value;try{await unlock(await api('login',{password}));$('notice').hidden=true;}finally{$('admin-password').value='';}});});
$('logout').addEventListener('click',()=>run($('logout'),async()=>{await api('logout',{});lock();notice('已退出管理会话');}));
for(const button of document.querySelectorAll('[data-tab]'))button.addEventListener('click',()=>{chooseTab(button.dataset.tab);if(button.dataset.tab==='history')run(button,loadHistory);});
$('profile-file').addEventListener('change',()=>run($('import-profile'),async()=>{const file=$('profile-file').files[0];if(!file)return;if(file.size>256*1024)throw new Error('设备会话超过 256 KiB');$('profile-json').value=await file.text();}));
$('import-profile').addEventListener('click',()=>run($('import-profile'),async()=>{let profile;try{profile=JSON.parse($('profile-json').value);}catch(e){throw new Error('设备会话 JSON 不合法');}const data=await api('profile',{profile});$('profile-json').value='';$('profile-file').value='';clearQr();renderAccount(data.account);notice('设备会话已导入，尚未核对官方有效性');}));
$('import-credential').addEventListener('click',()=>run($('import-credential'),async()=>{const data=await api('credential',{credential:$('account-credential').value});$('account-credential').value='';clearQr();renderAccount(data.account);notice('账号凭据已导入，尚未核对官方有效性');}));
for(const [id,operation,label] of [['verify-account','verify','账号检查'],['refresh-account','refresh','账号刷新']])$(id).addEventListener('click',()=>run($(id),async()=>{try{const data=await api('account',{operation});renderAccount(data.account);notice(label+'完成');}finally{await loadAccount();}}));
function renderQr(result){flow=result.flow_id||flow;$('qr-box').hidden=false;$('qr-state').textContent=result.message||'等待 App 扫码确认';$('qr-expiry').textContent=result.expires_at?'本地流程截止 '+when(result.expires_at):'';if(result.qr_image){$('qr-image').src=result.qr_image;$('qr-image').hidden=false;}if(['authenticated','cancelled','expired','missing','replaced','session_changed'].includes(result.state)){$('qr-image').removeAttribute('src');$('qr-image').hidden=true;flow='';}$('poll-qr').disabled=!flow;$('cancel-qr').disabled=!flow;}
for(const [id,operation] of [['start-qr','qr_start'],['poll-qr','qr_poll'],['cancel-qr','qr_cancel']])$(id).addEventListener('click',()=>run($(id),async()=>{const data=await api('account',{operation,flow_id:flow});renderQr(data.result);renderAccount(data.account);}));
$('create-key').addEventListener('click',()=>run($('create-key'),async()=>{dismissKey();const data=await api('keys',{name:$('key-name').value});$('key-name').value='';$('new-key-secret').value=data.key;$('new-key').hidden=false;await loadKeys();notice('调用密钥已生成，仅当前页面显示这一次');}));
$('copy-key').addEventListener('click',()=>run($('copy-key'),async()=>{const key=$('new-key-secret').value;if(!key)return;try{await navigator.clipboard.writeText(key);}catch(e){$('new-key-secret').focus();$('new-key-secret').select();if(!document.execCommand('copy'))throw new Error('无法自动复制，请选择密钥手动复制');}notice('密钥已复制');}));
$('dismiss-key').addEventListener('click',dismissKey);
$('history-form').addEventListener('submit',event=>{event.preventDefault();pageNumber=1;run($('history-filter'),loadHistory);});
$('previous-page').addEventListener('click',()=>{if(pageNumber>1){pageNumber--;run($('previous-page'),loadHistory);}});
$('next-page').addEventListener('click',()=>{if(hasMore){pageNumber++;run($('next-page'),loadHistory);}});
$('save-settings').addEventListener('click',()=>run($('save-settings'),async()=>{const allow_external=$('allow-external').checked;if(allow_external&&!confirm('开启外部访问前，请确认 HTTPS、可信 Host 和反向代理已独立配置。不会自动修改防火墙。继续？')){await loadSettings();return;}await api('settings',{allow_external});await loadSettings();notice('访问设置已保存');}));
window.addEventListener('pagehide',()=>{dismissKey();$('admin-password').value='';$('profile-json').value='';$('account-credential').value='';});
(async()=>{try{await unlock(await api('session'));}catch(e){lock();}})();
