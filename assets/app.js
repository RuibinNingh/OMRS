// === assets/app.js — 旧页面的数据刷新链 / 设置 / init()：最后一个经典脚本；init() 由 assets/app/main.js 在全部脚本就绪后调用 ===
let OPT_SUMMARY=null,OPT_SCAN=null,OPT_BACKUP_TOKEN='',OPT_JOB_TIMER=null;
// 切页（v1.21.0 起）：hash 路由 assets/app/core/router.js 接管，标题、工作台布局与进入各页的初始化登记在 assets/app/legacy-pages.js
function switchTab(name){window.__omrs?.router.go(name)}
// 数据加载与快照归 assets/app/domain/data.js（P6 起）；它写好旧 DATA 镜像后调本函数刷新旧页面，再经 bus 发 'data'。
// 全局 reloadData() 由过渡桥 installDataBridge 挂上。
async function legacyDataRefresh(){updateUidList();populateFilterOptions();populateCreateLists();renderQ();if(typeof loadLabels==='function')await loadLabels();if(typeof boardReloadData==='function')await boardReloadData();if(document.getElementById('panel-catalog')?.classList.contains('active')&&typeof renderCatalog==='function'&&CATALOG_TREE)renderCatalog()}
// === 设置：分区导航与访问状态 ===
const SETTINGS_SECTIONS = ['appearance', 'access', 'ai', 'data', 'service'];
const SETTINGS_SECTION_KEY = 'omrs-settings-section';
let ST_STATE = { cfg: null, auth: null, status: null };

function currentSettingsSection() {
  let saved = '';
  try { saved = localStorage.getItem(SETTINGS_SECTION_KEY) || ''; } catch (_) {}
  return SETTINGS_SECTIONS.includes(saved) ? saved : SETTINGS_SECTIONS[0];
}

function openSettingsSection(name, { focus = false } = {}) {
  const section = SETTINGS_SECTIONS.includes(name) ? name : SETTINGS_SECTIONS[0];
  try { localStorage.setItem(SETTINGS_SECTION_KEY, section); } catch (_) {}
  document.querySelectorAll('#panel-settings .st-nav-item').forEach(tab => {
    const on = tab.dataset.stSection === section;
    tab.setAttribute('aria-selected', on ? 'true' : 'false');
    tab.tabIndex = on ? 0 : -1;
    if (on && focus) tab.focus();
  });
  document.querySelectorAll('#panel-settings .st-section').forEach(panel => {
    panel.classList.toggle('active', panel.id === `st-sec-${section}`);
  });
  return section;
}

function settingsNavKey(event) {
  const step = { ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1 }[event.key];
  if (!step && event.key !== 'Home' && event.key !== 'End') return;
  event.preventDefault();
  const n = SETTINGS_SECTIONS.length;
  const i = SETTINGS_SECTIONS.indexOf(currentSettingsSection());
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? n - 1 : (i + step + n) % n;
  openSettingsSection(SETTINGS_SECTIONS[next], { focus: true });
}

function setSettingsStatus(id, text, tone = 'ok') {
  const el = document.getElementById(id);
  if (!el) return;
  const color = { ok: 'var(--green)', err: 'var(--red)', busy: 'var(--yellow)' }[tone] || 'var(--fg2)';
  el.innerHTML = text ? `<span style="color:${color}">${escapeHtml(text)}</span>` : '';
}

function parseLanCidrs(text) {
  return String(text || '').split(/[,，\n]/).map(v => v.trim()).filter(Boolean);
}

// The service only changes its listen address on restart, so compare with what
// is actually running (GET /api/status listen_external), not the saved config.
function runningListenExternal(state = ST_STATE) {
  return typeof state.status?.listen_external === 'boolean'
    ? state.status.listen_external : !!state.cfg?.allow_external;
}

function networkNeedsRestart(allowExternal, state = ST_STATE) {
  return !!allowExternal !== runningListenExternal(state);
}

function describeAccess(state = ST_STATE) {
  const { cfg, auth } = state;
  if (!cfg) {
    return { level: 'error', summary: '无法读取访问配置。请刷新页面；仍失败时检查服务日志。',
      listen: '—', listenNote: '', pin: '—', cidrs: '—', you: '—' };
  }
  const cidrs = Array.isArray(cfg.lan_pin_exempt_cidrs) ? cfg.lan_pin_exempt_cidrs : [];
  const pin = !!cfg.pin_configured;
  const configured = !!cfg.allow_external;
  const running = runningListenExternal(state);
  let level = 'guarded';
  let summary;
  if (!running) {
    level = 'local';
    summary = '现在只有这台电脑能打开 OMRS。';
  } else if (cidrs.length && pin) {
    level = 'open';
    summary = `局域网设备可以访问：${cidrs.join('、')} 内的设备直连免 PIN，其他设备须输入 PIN。`;
  } else if (cidrs.length) {
    level = 'open';
    summary = `局域网设备可以访问：只有 ${cidrs.join('、')} 内的设备能直连（免 PIN），其他设备会被拒绝。`;
  } else if (pin) {
    summary = '局域网设备可以访问，但必须先输入 PIN。';
  } else {
    summary = '服务已监听局域网，但还没有设置 PIN，其他设备都会被拒绝。';
  }
  let listenNote = '';
  if (running !== configured) {
    summary += configured ? '已保存「允许局域网访问」，重启服务后生效。' : '已关闭局域网访问，重启服务后生效。';
    listenNote = configured ? '重启后改为所有网卡' : '重启后改为仅本机';
  }
  const you = !auth ? '未知'
    : !auth.remote ? '本机直连，免 PIN'
    : auth.lan_pin_exempt ? '免 PIN 网段直连'
    : auth.authenticated ? '远端，已用 PIN 登录' : '远端，未登录';
  return {
    level, summary, listenNote, you,
    listen: running ? '所有网卡（局域网可达）' : '仅本机 127.0.0.1',
    pin: pin ? `已设置，空闲 ${asNumber(cfg.idle_minutes, 30)} 分钟后需重新登录` : '未设置',
    cidrs: cidrs.length ? cidrs.join('、') : '未设置',
  };
}

function renderAccessOverview() {
  const info = describeAccess();
  const box = document.getElementById('st-access-overview');
  if (box) box.dataset.level = info.level;
  const set = (id, html) => { const el = document.getElementById(id); if (el) el.innerHTML = html; };
  set('st-access-summary', escapeHtml(info.summary));
  set('st-fact-listen', escapeHtml(info.listen) + (info.listenNote ? `<small>${escapeHtml(info.listenNote)}</small>` : ''));
  set('st-fact-pin', escapeHtml(info.pin));
  set('st-fact-cidrs', escapeHtml(info.cidrs));
  set('st-fact-you', escapeHtml(info.you));
}

function pinControlState(state = ST_STATE) {
  const { cfg, auth } = state;
  const configured = !!cfg?.pin_configured;
  const remote = !!auth?.remote;
  const cidrs = Array.isArray(cfg?.lan_pin_exempt_cidrs) ? cfg.lan_pin_exempt_cidrs : [];
  const disableBlocked = !configured ? ''
    : remote ? '只能在本机上停用 PIN。'
    : cfg?.allow_external ? '先关闭局域网访问后才能停用 PIN。' : '';
  let statusText = configured ? 'PIN 已设置。' : cidrs.length
    ? 'PIN 尚未设置；目前只有免 PIN 网段内的设备能从其他电脑或手机访问。'
    : 'PIN 尚未设置。开启局域网访问前，请先设置 PIN 或填写免 PIN 网段。';
  if (disableBlocked) statusText += disableBlocked;
  return {
    configured, remote, disableBlocked, statusText,
    needCurrent: remote && configured,
    showLogout: remote && !auth?.lan_pin_exempt && !!auth?.authenticated,
    showDisable: configured && !remote,
    newLabel: configured ? '新 PIN' : '设置 PIN',
    newHint: configured
      ? '留空则只更新空闲时间。更换 PIN 后，所有远端设备都要重新登录。'
      : '4 到 12 位数字。设置后，不在免 PIN 网段内的设备须输入它才能访问。',
  };
}

function renderPinControls() {
  const st = pinControlState();
  const el = id => document.getElementById(id);
  if (el('st-pin-status')) el('st-pin-status').textContent = st.statusText;
  if (el('st-pin-current-row')) el('st-pin-current-row').hidden = !st.needCurrent;
  if (el('st-pin-new-label')) el('st-pin-new-label').textContent = st.newLabel;
  if (el('st-pin-new-hint')) el('st-pin-new-hint').textContent = st.newHint;
  if (el('st-pin-logout')) el('st-pin-logout').hidden = !st.showLogout;
  const disable = el('st-pin-disable');
  if (disable) {
    disable.hidden = !st.showDisable;
    disable.disabled = !!st.disableBlocked;
    disable.title = st.disableBlocked;
  }
}

function settingsNetworkChanged() {
  const hint = document.getElementById('st-net-hint');
  const allow = !!document.getElementById('st-allow-external')?.checked;
  const cidrs = parseLanCidrs(document.getElementById('st-lan-pin-exempt-cidrs')?.value);
  if (!hint) return;
  if (allow && ST_STATE.cfg && !ST_STATE.cfg.pin_configured && !cidrs.length) {
    hint.textContent = '开启前请先在上方设置 PIN，或填写免 PIN 网段。';
  } else if (networkNeedsRestart(allow)) {
    hint.textContent = allow ? '保存后会重启服务，开始监听局域网。' : '保存后会重启服务，之后只有本机能访问。';
  } else {
    hint.textContent = '保存后立即生效，不需要重启。';
  }
}

function fillSettingsForm(cfg) {
  const el = id => document.getElementById(id);
  if (el('st-allow-external')) el('st-allow-external').checked = !!cfg.allow_external;
  if (el('st-lan-pin-exempt-cidrs')) el('st-lan-pin-exempt-cidrs').value = (Array.isArray(cfg.lan_pin_exempt_cidrs) ? cfg.lan_pin_exempt_cidrs : []).join(', ');
  if (el('st-ai-base')) el('st-ai-base').value = cfg.ai_base_url || '';
  const key = el('st-ai-key');
  if (key) { key.value = ''; key.placeholder = cfg.ai_api_key_configured ? '已配置；留空表示保留现有密钥' : '输入新密钥'; }
  if (el('st-ai-key-state')) el('st-ai-key-state').textContent = cfg.ai_api_key_configured ? '已配置密钥（不会从服务器回显）' : '尚未配置密钥';
  if (el('st-ai-model')) el('st-ai-model').value = cfg.ai_model || '';
  if (el('st-ai-restrict')) el('st-ai-restrict').checked = cfg.ai_restrict_tags !== false;
  ['detect', 'extract', 'classify'].forEach(k => { const input = el('st-ai-model-' + k); if (input) input.value = cfg['ai_model_' + k] || ''; });
  if (el('st-pin-idle')) el('st-pin-idle').value = asNumber(cfg.idle_minutes, 30) || 30;
}

async function loadSettings() {
  openSettingsSection(currentSettingsSection());
  syncThemeControls();
  syncLedgerTimeZoneControl();
  loadOptimizeSummary();
  const [cfgResult, auth, status] = await Promise.all([
    api('/api/config').then(cfg => ({ cfg }), error => ({ error })),
    api('/api/auth/session', { cache: 'no-store' }).catch(() => null),
    loadRuntimeStatus(),
  ]);
  ST_STATE = { cfg: cfgResult.cfg || null, auth, status };
  if (cfgResult.cfg) fillSettingsForm(cfgResult.cfg);
  renderAccessOverview();
  renderPinControls();
  settingsNetworkChanged();
  if (cfgResult.error) setSettingsStatus('st-pin-action-status', `无法读取配置：${cfgResult.error.message}`, 'err');
}
function setThemeMode(mode){const t=mode==='dark'?'dark':'light';try{localStorage.setItem('omrs-theme',t)}catch(e){}document.documentElement.setAttribute('data-theme',t);syncThemeControls()}
function setDensity(mode){const d=mode==='comfortable'?'comfortable':'compact';try{localStorage.setItem('omrs-density',d)}catch(e){}document.documentElement.setAttribute('data-density',d);syncThemeControls()}
function setInvertImg(on){try{localStorage.setItem('omrs-invert-img',on?'1':'0')}catch(e){}document.documentElement.setAttribute('data-invert-img',on?'1':'0')}
function syncThemeControls(){const t=document.documentElement.getAttribute('data-theme')||'light';document.querySelectorAll('#st-theme-switch .theme-opt').forEach(b=>b.classList.toggle('active',b.dataset.theme===t));const inv=document.getElementById('st-invert-img');if(inv)inv.checked=document.documentElement.getAttribute('data-invert-img')==='1';const dn=document.documentElement.getAttribute('data-density')||'compact';document.querySelectorAll('#st-density-switch .theme-opt').forEach(b=>b.classList.toggle('active',b.dataset.density===dn))}
function syncLedgerTimeZoneControl(){const select=document.getElementById('st-ledger-time-zone');if(select)select.value=ledgerTimeZone()}
function setLedgerTimeZone(value){const zone=value||'local';try{localStorage.setItem(LEDGER_TIME_ZONE_KEY,zone)}catch(e){}syncLedgerTimeZoneControl();window.__omrs?.emit('ledger:tz')}
async function saveSettings() {
  const allowExternal = !!document.getElementById('st-allow-external')?.checked;
  const lanCidrs = parseLanCidrs(document.getElementById('st-lan-pin-exempt-cidrs')?.value);
  const needRestart = networkNeedsRestart(allowExternal);
  if (needRestart && !allowExternal && ST_STATE.auth?.remote && !await uiConfirm('关闭局域网访问？', {
    hint: '服务重启后只接受本机访问，你当前这台设备将无法再打开 OMRS。',
    okText: '关闭并重启', danger: true,
  })) return;
  setSettingsStatus('st-net-status', '正在保存…', 'busy');
  try {
    await api('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ allow_external: allowExternal, lan_pin_exempt_cidrs: lanCidrs }),
    });
    if (needRestart) {
      setSettingsStatus('st-net-status', '已保存，正在重启服务以应用新的监听范围…', 'busy');
      await doRestart(false, {}, 'st-net-status');
      return;
    }
    setSettingsStatus('st-net-status', '已保存，立即生效。');
    await loadSettings();
  } catch (error) {
    setSettingsStatus('st-net-status', `保存失败：${error.message}`, 'err');
  }
}
const RESTART_READY_TIMEOUT_MS = 90_000;

// Poll GET /api/auth/session until it reports an instance_id different from the
// pre-restart one. Network errors/aborts mean "not ready yet"; bounded by timeoutMs.
async function waitForRestartReady(previousInstanceId, {
  timeoutMs = RESTART_READY_TIMEOUT_MS,
  intervalMs = 500,
  probeTimeoutMs = 1_500,
  request = api,
  now = () => Date.now(),
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
} = {}) {
  if (!previousInstanceId) return false;
  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    const controller = new AbortController();
    const abortTimer = setTimeout(() => controller.abort(), probeTimeoutMs);
    try {
      const state = await request('/api/auth/session', {
        cache: 'no-store',
        signal: controller.signal,
      });
      if (state?.status === 'ok' && state.instance_id &&
          state.instance_id !== previousInstanceId) return true;
    } catch (_) {
      // Connection refusal/abort is expected while the listener restarts.
    } finally {
      clearTimeout(abortTimer);
    }
    const remaining = deadline - now();
    if (remaining <= 0) break;
    await sleep(Math.min(intervalMs, remaining));
  }
  return false;
}

async function doRestart(showStatus = true, readyOptions = {}, statusId = 'st-status') {
  const status = document.getElementById(statusId);
  const setStatus = (text, color = 'var(--yellow)') => {
    if (status) status.innerHTML = `<span style="color:${color}">${text}</span>`;
  };
  if (showStatus) setStatus('正在读取当前服务实例…');
  try {
    const before = await api('/api/auth/session', { cache: 'no-store' });
    if (!before?.instance_id) throw new Error('无法读取当前服务实例 ID');
    await api('/api/restart', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    setStatus('重启指令已发出，等待新服务就绪…');
    if (await waitForRestartReady(before.instance_id, readyOptions)) {
      window.location.reload();
      return;
    }
    setStatus('90 秒内未检测到新服务实例。请勿连续点击重启，检查 omrs.service 状态和日志。', 'var(--red)');
  } catch (error) {
    setStatus(`重启未完成：${escapeHtml(error.message || '请求失败')}`, 'var(--red)');
  }
}

// === 录入题目：AI 设置 ===
function toggleAiKey(){const input=document.getElementById('st-ai-key');const button=document.getElementById('st-ai-key-toggle');if(!input)return;if(input.type==='password'){input.type='text';if(button)button.textContent='隐藏'}else{input.type='password';if(button)button.textContent='显示'}}
async function saveAiSettings(){const base=(document.getElementById('st-ai-base')?.value||'').trim();const key=(document.getElementById('st-ai-key')?.value||'').trim();const model=(document.getElementById('st-ai-model')?.value||'').trim();const restrictEl=document.getElementById('st-ai-restrict');const restrict=restrictEl?!!restrictEl.checked:true;const status=document.getElementById('st-ai-settings-status');const payload={ai_base_url:base,ai_model:model,ai_restrict_tags:restrict,ai_model_detect:(document.getElementById('st-ai-model-detect')?.value||'').trim(),ai_model_extract:(document.getElementById('st-ai-model-extract')?.value||'').trim(),ai_model_classify:(document.getElementById('st-ai-model-classify')?.value||'').trim()};if(key)payload.ai_api_key=key;try{await api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(status)status.innerHTML='<span style="color:var(--green)">✓ AI 配置已保存（立即生效，无需重启）</span>';await loadSettings()}catch(error){if(status)status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`}}
async function clearAiKey(){if(!await uiConfirm('清除已保存的 AI 密钥？',{okText:'清除',danger:true}))return;const status=document.getElementById('st-ai-settings-status');try{await api('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({clear_ai_api_key:true})});await loadSettings();if(status)status.textContent='AI 密钥已清除'}catch(error){if(status)status.textContent='清除失败：'+error.message}}
async function savePinSettings() {
  const el = id => document.getElementById(id);
  const pin = (el('st-pin-new')?.value || '').trim();
  const current = (el('st-pin-current')?.value || '').trim();
  const idle = Number(el('st-pin-idle')?.value);
  const st = pinControlState();
  const fail = text => setSettingsStatus('st-pin-action-status', text, 'err');
  if (pin && !/^\d{4,12}$/.test(pin)) return fail('PIN 必须是 4 到 12 位数字。');
  if (!Number.isInteger(idle) || idle < 5 || idle > 240) return fail('空闲时间须为 5 到 240 之间的整数分钟。');
  if (!pin && !st.configured) return fail('请先输入要设置的 PIN。');
  if (st.needCurrent && !current) return fail('从其他设备修改时，请先输入当前 PIN。');
  setSettingsStatus('st-pin-action-status', '正在保存…', 'busy');
  try {
    await api('/api/auth/pin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin, current_pin: current, idle_minutes: idle }),
    });
    if (el('st-pin-new')) el('st-pin-new').value = '';
    if (el('st-pin-current')) el('st-pin-current').value = '';
    // Changing the PIN revokes every remote session, including this one.
    if (pin && st.showLogout) { location.assign('/login'); return; }
    const done = !pin ? `空闲时间已改为 ${idle} 分钟。`
      : st.configured ? 'PIN 已更换，所有远端设备需要重新登录。' : 'PIN 已设置。';
    await loadSettings();
    setSettingsStatus('st-pin-action-status', done);
  } catch (error) {
    fail(`保存失败：${error.message}`);
  }
}
async function disablePin() {
  const st = pinControlState();
  if (st.disableBlocked) { setSettingsStatus('st-pin-action-status', st.disableBlocked, 'err'); return; }
  if (!await uiConfirm('停用远端 PIN？', {
    hint: '所有远端登录会立即失效。之后开启局域网访问前，必须重新设置 PIN 或填写免 PIN 网段。',
    okText: '停用 PIN', danger: true,
  })) return;
  try {
    await api('/api/auth/disable', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    await loadSettings();
    setSettingsStatus('st-pin-action-status', 'PIN 已停用。');
  } catch (error) {
    setSettingsStatus('st-pin-action-status', `停用失败：${error.message}`, 'err');
  }
}
async function logoutRemote() {
  try {
    await api('/api/auth/logout', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
  } catch (_) {
    // An expired session is already logged out; go to the login page either way.
  }
  location.assign('/login');
}


// === 录入题目：图片粘贴 / 拖拽 / 选择（'q'=题目图，'a'=答案图） ===
let CR_PASTE_TARGET='q';
function crImageArray(kind){return kind==='a'?CR_A_IMAGES:CR_Q_IMAGES}
function crSetPasteTarget(kind){CR_PASTE_TARGET=kind==='a'?'a':'q';['q','a'].forEach(k=>{const z=document.getElementById('cr-'+k+'-paste');if(z)z.classList.toggle('paste-active',k===CR_PASTE_TARGET)})}
async function crReadClipboard(kind){crSetPasteTarget(kind);if(!navigator.clipboard||!navigator.clipboard.read){uiToast('当前浏览器不支持直接读取剪贴板，请改用 Ctrl / ⌘ + V 粘贴',{kind:'error'});return}try{const items=await navigator.clipboard.read();let found=0;for(const item of items){const type=(item.types||[]).find(t=>t&&t.startsWith('image/'));if(type){const blob=await item.getType(type);crAddBlob(blob,kind);found++}}if(!found)uiToast('剪贴板里没有图片。请先截图或复制一张图片，再点此按钮。',{kind:'warn'})}catch(error){uiToast('读取剪贴板失败：'+((error&&error.message)||error)+'。可能需要在浏览器允许“剪贴板”权限，或改用 Ctrl / ⌘ + V 粘贴。',{kind:'error',duration:6000})}}
function crPickFiles(kind){crSetPasteTarget(kind);const input=document.getElementById(`cr-${kind}-file`);if(input)input.click()}
function crFileInput(event,kind){const files=event.target.files;if(files&&files.length)crAddFiles(files,kind);event.target.value=''}
function crDragOver(event,kind){event.preventDefault();const zone=document.getElementById(`cr-${kind}-paste`);if(zone)zone.classList.add('dragover')}
function crDragLeave(event,kind){const zone=document.getElementById(`cr-${kind}-paste`);if(zone)zone.classList.remove('dragover')}
function crHandleDrop(event,kind){event.preventDefault();const zone=document.getElementById(`cr-${kind}-paste`);if(zone)zone.classList.remove('dragover');const files=event.dataTransfer&&event.dataTransfer.files;if(files&&files.length)crAddFiles(files,kind)}
function crAddFiles(fileList,kind){[...fileList].filter(file=>file&&file.type&&file.type.startsWith('image/')).forEach(file=>crAddBlob(file,kind))}
function crAddBlob(blob,kind){const reader=new FileReader();reader.onload=()=>{crImageArray(kind).push({id:++CR_IMG_SEQ,dataUrl:reader.result});crRenderImages(kind)};reader.readAsDataURL(blob)}
function crRemoveImage(kind,id){const arr=crImageArray(kind);const idx=arr.findIndex(img=>img.id===id);if(idx>=0)arr.splice(idx,1);crRenderImages(kind)}
function crRenderImages(kind){const box=document.getElementById(`cr-${kind}-images`);const arr=crImageArray(kind);if(box)box.innerHTML=arr.map((img,index)=>`<div class="img-thumb"><img src="${img.dataUrl}" alt="图片${index+1}"><button type="button" class="img-del" title="移除" onclick="crRemoveImage('${kind}',${img.id})">✕</button><span class="img-idx">${index+1}</span></div>`).join('');const ids=kind==='a'?['cr-extract-btn']:['cr-classify-btn','cr-question-text-btn'];ids.forEach(id=>{const btn=document.getElementById(id);if(btn)btn.disabled=arr.length===0})}
function crHandlePaste(event){const panel=document.getElementById('panel-create');if(!panel||!panel.classList.contains('active'))return;if(typeof IB!=='undefined'&&IB.stage!=='quick')return;const items=event.clipboardData&&event.clipboardData.items;if(!items)return;const active=document.activeElement;const kind=(active&&active.id==='cr-a-paste')?'a':(active&&active.id==='cr-q-paste')?'q':CR_PASTE_TARGET;let consumed=false;[...items].forEach(item=>{if(item.kind==='file'&&item.type&&item.type.startsWith('image/')){const blob=item.getAsFile();if(blob){crAddBlob(blob,kind);consumed=true}}});if(consumed)event.preventDefault()}

// === 录入题目：提取并填充信息（科目/分类/难度，读第 1 张题目图和第 1 张答案图） ===
async function crClassify(){if(!CR_Q_IMAGES.length){uiToast('请先粘贴或选择题目图片',{kind:'warn'});return}const status=document.getElementById('cr-classify-status');const button=document.getElementById('cr-classify-btn');const questionImage=CR_Q_IMAGES[0].dataUrl;const answerImage=CR_A_IMAGES.length>0?CR_A_IMAGES[0].dataUrl:null;const curSubject=(document.getElementById('cr-subject')?.value||'').trim();const curCategory=(document.getElementById('cr-category')?.value||'').trim();if(status){status.className='ai-status busy';status.textContent='识别中…（同时分析题目和答案，可能需要十几秒）'}if(button)button.disabled=true;try{const payload={question_image:questionImage,mode:'classify',subject:curSubject,category:curCategory};if(answerImage)payload.answer_image=answerImage;const result=await api('/api/ai-recognize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const fillIfEmpty=(id,val)=>{const el=document.getElementById(id);if(el&&val!=null&&String(val).trim()!==''&&el.value.trim()==='')el.value=val};fillIfEmpty('cr-subject',result.subject);fillIfEmpty('cr-category',result.category);if(result.difficulty){const diff=document.getElementById('cr-diff');if(diff)diff.value=result.difficulty;const diffVal=document.getElementById('cr-diff-val');if(diffVal)diffVal.textContent=result.difficulty}if(result.knowledge_tags&&result.knowledge_tags.length){const relEl=document.getElementById('cr-related');const merged=(relEl?.value||'').split(/[,，]/).map(t=>t.trim()).filter(Boolean);result.knowledge_tags.forEach(tag=>{if(tag&&!merged.includes(tag))merged.push(tag)});if(relEl)relEl.value=merged.join(', ')}if(result.labels&&result.labels.length){const labelIds=result.labels.map(name=>String(name).trim()).filter(Boolean);if(labelIds.length&&typeof setCreateLabels==='function')setCreateLabels(labelIds)}const kept=(curSubject||curCategory)?'（已保留你填写的科目/分类）':'';const labelHint=result.labels&&result.labels.length?` · 已生成${result.labels.length}个标记`:'';if(status){status.className='ai-status ok';status.textContent='✓ 已填充，请核对'+kept+labelHint}}catch(error){if(status){status.className='ai-status err';status.textContent='✕ '+error.message}}if(button)button.disabled=CR_Q_IMAGES.length===0}

// === 录入题目：提取题目正文（读第 1 张题目图，转成文本填入题目框） ===
async function crExtractQuestionText(){if(!CR_Q_IMAGES.length){uiToast('请先粘贴或选择题目图片',{kind:'warn'});return}const status=document.getElementById('cr-classify-status');const button=document.getElementById('cr-question-text-btn');const image=CR_Q_IMAGES[0].dataUrl;if(status){status.className='ai-status busy';status.textContent='提取题目文本中…（可能需要十几秒）'}if(button)button.disabled=true;try{const result=await api('/api/ai-recognize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image,mode:'question_text'})});const text=(result.question_text||'').trim();if(result.mode&&result.mode!=='question_text')throw new Error(`后端返回了 ${result.mode} 模式，请重启服务后再试`);if(!text)throw new Error('模型没有返回题目正文，请换一张更清晰的题图或稍后重试');const questionEl=document.getElementById('cr-question');if(questionEl)questionEl.value=text;if(status){status.className='ai-status ok';status.textContent='✓ 已提取题目文本，请核对'}}catch(error){if(status){status.className='ai-status err';status.textContent='✕ '+error.message}}if(button)button.disabled=CR_Q_IMAGES.length===0}

// === 录入题目：提取答案（读第 1 张答案图，转成文本填入答案框） ===
async function crExtractAnswer(){if(!CR_A_IMAGES.length){uiToast('请先粘贴或选择答案图片',{kind:'warn'});return}const status=document.getElementById('cr-extract-status');const button=document.getElementById('cr-extract-btn');const image=CR_A_IMAGES[0].dataUrl;if(status){status.className='ai-status busy';status.textContent='识别中…（可能需要十几秒）'}if(button)button.disabled=true;try{const result=await api('/api/ai-recognize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image,mode:'answer'})});const answerEl=document.getElementById('cr-answer');if(answerEl&&result.answer&&result.answer.trim())answerEl.value=result.answer;if(status){status.className='ai-status ok';status.textContent='✓ 已提取答案文本，请核对'}}catch(error){if(status){status.className='ai-status err';status.textContent='✕ '+error.message}}if(button)button.disabled=CR_A_IMAGES.length===0}

// === 设置：运行状态 ===
function formatUptime(seconds){let s=Math.max(0,Math.floor(asNumber(seconds,0)));const d=Math.floor(s/86400);s%=86400;const h=Math.floor(s/3600);s%=3600;const m=Math.floor(s/60);if(d)return`${d}天 ${h}小时`;if(h)return`${h}小时 ${m}分钟`;return`${m}分钟`}
async function loadRuntimeStatus(){const state=document.getElementById('st-runtime-state');if(state)state.textContent='加载中';try{const info=await api('/api/status');const set=(id,text)=>{const el=document.getElementById(id);if(el)el.textContent=text};set('st-runtime-version',info.version||'—');set('st-runtime-uptime',formatUptime(info.uptime_seconds));set('st-runtime-count',`${asNumber(info.question_count,0)} 题`);set('st-runtime-state',info.status==='ok'?'运行中':info.status||'未知');const vault=document.getElementById('st-runtime-vault');if(vault)vault.innerHTML=`Vault: <code>${escapeHtml(info.vault_path||'')}</code>`;return info}catch(error){if(state)state.textContent='无法读取';const vault=document.getElementById('st-runtime-vault');if(vault)vault.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`;return null}}

// === 设置：优化 / 备份 / 图片压缩 ===
function formatBytes(bytes){const n=Math.max(0,asNumber(bytes,0));if(n>=1024*1024*1024)return`${(n/1024/1024/1024).toFixed(2)} GB`;if(n>=1024*1024)return`${(n/1024/1024).toFixed(2)} MB`;if(n>=1024)return`${(n/1024).toFixed(1)} KB`;return`${Math.round(n)} B`}
function optStatus(html){const el=document.getElementById('opt-status');if(el)el.innerHTML=html||''}
function svcBackupStatus(html){const el=document.getElementById('svc-backup-status');if(el)el.innerHTML=html||''}
function setOptimizeProgress(visible,mode='idle',text='准备中',percent='0%',file=''){const box=document.getElementById('opt-progress');if(box){box.style.display=visible?'block':'none';box.classList.toggle('scanning',mode==='scanning');const textEl=document.getElementById('opt-progress-text');if(textEl)textEl.textContent=text;const pctEl=document.getElementById('opt-progress-percent');if(pctEl)pctEl.textContent=percent;const fill=document.getElementById('opt-progress-fill');if(fill){fill.style.transform='';fill.style.width=mode==='scanning'?'45%':percent}const fileEl=document.getElementById('opt-progress-file');if(fileEl)fileEl.textContent=file}}
function optValues(summary,scan=null,job=null){const sizes=summary?.sizes||{};const data=asNumber(sizes.data_chain?.bytes,0);const files=asNumber(sizes.question_files?.bytes,0);const images=asNumber(sizes.question_images?.bytes,0);if(scan){const exact=scan.exact!==false;const label=exact?'可压缩大小':'待深扫图片';const baseBytes=exact?asNumber(scan.compressible_bytes,0):asNumber(scan.potential_bytes,0);const remaining=Math.max(0,baseBytes-asNumber(job?.checked_bytes||job?.saved_bytes,0));const center=job?`已节省 ${formatBytes(job.saved_bytes)}`:(exact?`可压缩 ${formatBytes(scan.compressible_bytes)}`:`待深扫 ${scan.candidate_count||0} 张`);return{center,items:[{label:'数据链',bytes:data,files:sizes.data_chain?.files||0,color:'var(--accent)'},{label:'题目文件',bytes:files,files:sizes.question_files?.files||0,color:'var(--green)'},{label,bytes:remaining,files:scan.candidate_count||0,color:'var(--blue)',note:`原题图 ${formatBytes(images)}`}]}}return{center:formatBytes(data+files+images),items:[{label:'数据链',bytes:data,files:sizes.data_chain?.files||0,color:'var(--accent)'},{label:'题目文件',bytes:files,files:sizes.question_files?.files||0,color:'var(--green)'},{label:'题目图片',bytes:images,files:sizes.question_images?.files||0,color:'var(--blue)'}]}}
function renderOptimizeChart(summary=OPT_SUMMARY,scan=OPT_SCAN,job=null){if(!summary)return;const spec=optValues(summary,scan,job);const items=spec.items;const total=Math.max(1,items.reduce((sum,item)=>sum+asNumber(item.bytes,0),0));const totalEl=document.getElementById('opt-total');if(totalEl)totalEl.textContent=spec.center;const keys=['data','files','images'];items.forEach((item,i)=>{const k=keys[i];if(!k)return;const pct=Math.round(asNumber(item.bytes,0)/total*100);const labelEl=document.getElementById('opt-l-'+k);if(labelEl)labelEl.textContent=item.label;const valEl=document.getElementById('opt-v-'+k);if(valEl)valEl.textContent=formatBytes(item.bytes);const detEl=document.getElementById('opt-d-'+k);if(detEl)detEl.textContent=`${asNumber(item.files,0)} 个文件${item.note?` · ${item.note}`:''}`;const barEl=document.getElementById('opt-b-'+k);if(barEl){barEl.style.width=pct+'%';barEl.style.background=item.color}const segEl=document.getElementById('opt-seg-'+k);if(segEl)segEl.style.width=pct+'%'});const deps=summary.dependencies||{};const pillow=deps.pillow||{};const jpeg=deps.jpegtran||{};const depEl=document.getElementById('opt-deps');if(depEl){depEl.innerHTML=`<span class="opt-pill ${pillow.available?'ok':'no'}">${pillow.available?'✓':'✕'} Pillow ${pillow.available?escapeHtml(pillow.version||'已安装'):'未安装'}</span><span class="opt-pill ${jpeg.available?'ok':'no'}">${jpeg.available?'✓':'✕'} jpegtran ${jpeg.available?'已可用':'未安装'}</span><span class="opt-pill muted">题图 ${formatBytes(summary.images?.bytes||0)} · ${summary.images?.count||0} 张</span>`}updateOptimizeControls()}
function updateOptimizeControls(){const pillowOk=!!OPT_SUMMARY?.dependencies?.pillow?.available;const scanDone=!!(OPT_SCAN&&asNumber(OPT_SCAN.candidate_count,0)>0);const busy=!!OPT_JOB_TIMER;const scanCard=document.getElementById('opt-a-scan');if(scanCard){scanCard.classList.toggle('disabled',!pillowOk);scanCard.classList.toggle('busy',busy)}const compressCard=document.getElementById('opt-a-compress');if(compressCard){compressCard.classList.toggle('disabled',!(pillowOk&&scanDone));compressCard.classList.toggle('busy',busy)}const hint=document.getElementById('opt-compress-hint');if(hint){if(!pillowOk)hint.textContent='需要安装 Pillow 才能压缩';else if(!OPT_SCAN)hint.textContent='扫描图片后可压缩';else if(!scanDone)hint.textContent='没有可压缩的图片';else hint.textContent=`${asNumber(OPT_SCAN.candidate_count,0)} 张候选，约 ${formatBytes(OPT_SCAN.potential_bytes||0)}`}const imgMetric=document.getElementById('opt-m-images');if(imgMetric)imgMetric.classList.toggle('scanning',busy);const subEl=document.getElementById('opt-head-sub');if(subEl&&OPT_SUMMARY)subEl.textContent=busy?(OPT_SCAN?'压缩中…':'扫描中…'):(scanDone?'快扫完成':'刚刚更新')}
async function loadOptimizeSummary(){try{OPT_SUMMARY=await api('/api/optimize/summary');renderOptimizeChart(OPT_SUMMARY,OPT_SCAN);if(!OPT_SUMMARY.dependencies?.pillow?.available)optStatus('<span style="color:var(--yellow)">Pillow 不可用，图片压缩功能已禁用；服务启动时会尝试弹窗提示安装。</span>')}catch(error){optStatus(`<span style="color:var(--red)">✕ 无法读取优化状态：${escapeHtml(error.message)}</span>`)}}
async function exportOptimizeBackup(){svcBackupStatus('<span style="color:var(--yellow)">正在打包错题备份...</span>');try{const response=await fetch('/api/backup/export',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});if(!response.ok){let message='导出备份失败';try{message=(await response.json()).msg||message}catch(e){}throw new Error(message)}OPT_BACKUP_TOKEN=response.headers.get('X-OMRS-Backup-Token')||'';await downloadExportResponse(response,`OMRS-backup-${new Date().toISOString().slice(0,19).replace(/[-:T]/g,'')}.zip`,'svc-backup-status')}catch(error){svcBackupStatus(`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`)}}
async function exportSanitizedSource(){const status=document.getElementById('svc-source-status');const button=document.querySelector('[onclick="exportSanitizedSource()"]');if(status)status.innerHTML='<span style="color:var(--yellow)">正在生成脱敏源码包...</span>';if(button)button.disabled=true;try{const response=await fetch('/api/source/export');if(!response.ok){let message='下载脱敏源码失败';try{message=(await response.json()).msg||message}catch(e){}throw new Error(message)}await downloadExportResponse(response,'OMRS-source-sanitized.zip','svc-source-status');if(status)status.innerHTML='<span style="color:var(--green)">✓ 已下载。包内含 SOURCE_EXPORT_MANIFEST.txt，可核对排除范围。</span>'}catch(error){if(status)status.innerHTML=`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`}finally{if(button)button.disabled=false}}

async function importOptimizeBackup(event){const input=event.target;const file=input.files&&input.files[0];input.value='';if(!file)return;if(!await uiConfirm(`导入备份 ${file.name}？`,{hint:'会先校验，随后可选择恢复并覆盖当前错题目录。',okText:'继续导入'}))return;svcBackupStatus('<span style="color:var(--yellow)">正在上传并校验备份...</span>');try{const form=new FormData();form.append('file',file,file.name);const prepared=await api('/api/backup/import',{method:'POST',body:form});const p=prepared.preview||{};const message=`备份校验通过：${p.files||0} 个文件，${formatBytes(p.bytes||0)}，Markdown ${p.md_files||0}，图片 ${p.image_files||0}。\n\n恢复会覆盖当前“错题”目录，且不可在页面内撤销。确认恢复？`;if(!await uiConfirm('恢复备份并覆盖当前错题目录？',{hint:message.replace(/\n+/g,' '),okText:'恢复',danger:true})){svcBackupStatus('<span style="color:var(--fg3)">已取消恢复，当前数据未改变。</span>');return}const restored=await api('/api/backup/restore',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({restore_id:prepared.restore_id,confirm:true})});svcBackupStatus(`<span style="color:var(--green)">✓ 已恢复备份，当前索引 ${restored.question_count||0} 题。建议刷新页面。</span>`);await reloadData();OPT_SCAN=null;OPT_BACKUP_TOKEN='';await loadOptimizeSummary()}catch(error){svcBackupStatus(`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`)}}
async function scanOptimizeImages(){OPT_SCAN=null;setOptimizeProgress(true,'scanning','快扫中','0%','正在统计图片格式和可深扫范围');optStatus('<span style="color:var(--yellow)">正在快扫图片，不会生成优化副本...</span>');try{const result=await api('/api/optimize/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});startOptimizeScanPolling(result.job.job_id)}catch(error){setOptimizeProgress(false);optStatus(`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`);updateOptimizeControls()}}
function startOptimizeScanPolling(jobId){if(OPT_JOB_TIMER)clearInterval(OPT_JOB_TIMER);OPT_JOB_TIMER=setInterval(()=>pollOptimizeScanJob(jobId),500);updateOptimizeControls();pollOptimizeScanJob(jobId)}
async function pollOptimizeScanJob(jobId){try{const result=await api(`/api/optimize/job?id=${encodeURIComponent(jobId)}`);const job=result.job||{};const total=Math.max(1,asNumber(job.total,1));const pct=Math.min(100,Math.round(asNumber(job.processed,0)/total*100));setOptimizeProgress(true,job.done?'idle':'scanning',job.done?'快扫完成':'快扫中',`${pct}%`,job.current_file?`当前：${job.current_file}`:`已扫描 ${asNumber(job.processed,0)} / ${asNumber(job.total,0)} 个图片文件`);if(job.done){clearInterval(OPT_JOB_TIMER);OPT_JOB_TIMER=null;OPT_SCAN=job.result||null;renderOptimizeChart(OPT_SUMMARY,OPT_SCAN);const skipped=Object.entries(OPT_SCAN?.skipped||{}).map(([k,v])=>`${escapeHtml(k)}：${v}`).join('；');const note=asNumber(OPT_SCAN?.candidate_count,0)>0?'可点「确认压缩」开始；如需保险可先在「设置 → 数据与存储」导出备份。':'没有可压缩的图片。';optStatus(`<span style="color:var(--green)">✓ 快扫完成：${OPT_SCAN?.candidate_count||0} 张图片可进入深扫压缩，范围 ${formatBytes(OPT_SCAN?.potential_bytes||0)}。</span><div class="hint">${escapeHtml(note)}${skipped?` 跳过：${skipped}`:''}</div>`);updateOptimizeControls()}}catch(error){if(OPT_JOB_TIMER)clearInterval(OPT_JOB_TIMER);OPT_JOB_TIMER=null;setOptimizeProgress(false);optStatus(`<span style="color:var(--red)">✕ 读取快扫进度失败：${escapeHtml(error.message)}</span>`);updateOptimizeControls()}}
async function confirmOptimizeCompression(){if(!OPT_SCAN){optStatus('<span style="color:var(--red)">请先扫描图片。</span>');return}if(!(asNumber(OPT_SCAN.candidate_count,0)>0)){optStatus('<span style="color:var(--red)">没有可压缩的图片。</span>');return}const text=`即将深扫并无损压缩 ${OPT_SCAN.candidate_count||0} 张候选图片（约 ${formatBytes(OPT_SCAN.potential_bytes||0)}）。\n\n压缩会逐张生成优化副本、校验像素，只替换更小的文件——原则上无损，但仍会改写图片文件。如需保险，可先到「设置 → 数据与存储」导出一份。\n\n确认开始压缩？`;if(!await uiConfirm('确认开始压缩？',{hint:text.replace(/\n+/g,' '),okText:'开始压缩'}))return;try{const result=await api('/api/optimize/compress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scan_id:OPT_SCAN.scan_id,backup_token:OPT_BACKUP_TOKEN||'',confirm:true})});startOptimizeJobPolling(result.job.job_id)}catch(error){optStatus(`<span style="color:var(--red)">✕ ${escapeHtml(error.message)}</span>`)}}
function startOptimizeJobPolling(jobId){if(OPT_JOB_TIMER)clearInterval(OPT_JOB_TIMER);setOptimizeProgress(true,'idle','准备压缩','0%','');OPT_JOB_TIMER=setInterval(()=>pollOptimizeJob(jobId),900);updateOptimizeControls();pollOptimizeJob(jobId)}
async function pollOptimizeJob(jobId){try{const result=await api(`/api/optimize/job?id=${encodeURIComponent(jobId)}`);const job=result.job||{};const total=Math.max(1,asNumber(job.total,1));const pct=Math.min(100,Math.round(asNumber(job.processed,0)/total*100));document.getElementById('opt-progress-text').textContent=job.status==='running'?'深扫压缩中':job.status||'准备中';document.getElementById('opt-progress-percent').textContent=`${pct}%`;document.getElementById('opt-progress-fill').style.width=`${pct}%`;document.getElementById('opt-progress-file').textContent=job.current_file?`当前：${job.current_file}`:`已检查 ${asNumber(job.processed,0)} / ${asNumber(job.total,0)}，已压缩 ${asNumber(job.candidate_count,0)} 张，节省 ${formatBytes(job.saved_bytes||0)}`;renderOptimizeChart(OPT_SUMMARY,OPT_SCAN,job);if(job.done){clearInterval(OPT_JOB_TIMER);OPT_JOB_TIMER=null;const errors=(job.errors||[]).length?`，有 ${job.errors.length} 个错误`:'。';optStatus(`<span style="color:var(--green)">✓ 深扫压缩完成：实际压缩 ${asNumber(job.candidate_count,0)} 张，节省 ${formatBytes(job.saved_bytes||0)}${escapeHtml(errors)}</span>`);OPT_SCAN=null;OPT_BACKUP_TOKEN='';await loadOptimizeSummary()}}catch(error){if(OPT_JOB_TIMER)clearInterval(OPT_JOB_TIMER);OPT_JOB_TIMER=null;optStatus(`<span style="color:var(--red)">✕ 读取压缩进度失败：${escapeHtml(error.message)}</span>`)}}

async function setSidebarVersion(){try{const s=await api('/api/status');const el=document.getElementById('sidebar-foot');if(el&&s&&s.version)el.textContent=`${s.version} · 本地服务`}catch(e){}}
function toggleSidebar(){const c=localStorage.getItem('omrs-sidebar-collapsed')==='1';localStorage.setItem('omrs-sidebar-collapsed',c?'0':'1');document.documentElement.setAttribute('data-sidebar',c?'':'collapsed')}
function openDrawer(){document.body.classList.add('drawer-open')}
function closeDrawer(){document.body.classList.remove('drawer-open')}
function toggleDrawer(){document.body.classList.toggle('drawer-open')}
document.addEventListener('click',function(e){if(e.target.closest('.sidebar-nav .tab')&&window.matchMedia('(max-width:860px)').matches)closeDrawer()});
document.addEventListener('keydown',function(e){if(e.key==='Escape')closeDrawer()});
async function init(){setSidebarVersion();await loadLabels();await reloadData();await refreshSessions();if(typeof boardInit==='function')boardInit();if(typeof crSetPasteTarget==='function')crSetPasteTarget(CR_PASTE_TARGET)}
// Esc 关题目弹窗：由过渡桥登记到 core/keys.js（assets/app/legacy-bridge.js 的 installEscapeBridge；P5 起），不再在 document 上另挂
document.addEventListener('paste',crHandlePaste);
// 不再自调用 init()：模块入口 assets/app/main.js 装好过渡桥与路由后调用它（v1.21.0 起）
