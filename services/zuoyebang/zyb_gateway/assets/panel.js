/* 不持久化管理员密码、设备凭据、二维码或完整调用密钥。 */
'use strict';
const $ = id => document.getElementById(id);
const text = (tag, value, className = '') => {
  const node = document.createElement(tag);
  node.textContent = String(value);
  if (className) node.className = className;
  return node;
};
const when = value => value ? new Date(value * 1000).toLocaleString('zh-CN', {hour12: false}) : '—';
const stateNames = {valid: '已验证', invalid: '已确认失效', unknown: '待核对'};
const kindNames = {ok: '成功', network: '网络失败 · 保留此前状态', protocol: '响应异常 · 保留此前状态', login_required: '账号已确认失效', signing_session: '签名已确认失效', upstream: '官方请求失败 · 保留此前状态'};
const eventNames = {profile_import: '导入设备或账号凭据', verify: '核对账号', refresh: '刷新账号', search: '客户端搜题', login: '扫码登录', qr_start: '创建登录二维码', qr_cancel: '取消扫码登录'};
const pageLabels = {
  overview: ['服务概览', '先看服务状态，再处理需要关注的事项。'],
  account: ['账号与会话', '管理设备配置、官方登录与有效期观察。'],
  keys: ['调用密钥', '为客户端分配独立权限，按需生成或吊销。'],
  history: ['请求记录', '查看调用来源、结果与耗时。'],
  settings: ['访问设置', '管理访问范围，查看服务资源预算。']
};
let csrf = '', epoch = 0, flow = '', pageNumber = 1, visiblePage = 1, hasMore = false, readAt = 0, logoutPending = false;
let model = emptyModel(), confirmResolve = null, pendingFocus = null;
const busy = new Set(), controllers = new Set();
const reads = {account: 0, keys: 0, settings: 0, history: 0};
const dialogVersions = { 'profile-dialog': 0, 'credential-dialog': 0, 'qr-dialog': 0, 'key-dialog': 0 };
const dialogOpeners = new Map();
class StaleRequest extends Error {}
function emptyModel() { return {account: null, keys: null, settings: null, accountError: '', keysError: '', settingsError: ''}; }
function ignored(error) { return error instanceof StaleRequest || error.name === 'AbortError'; }
function badge(id, label, state = '') { $(id).textContent = label; $(id).dataset.state = state; }
function notice(message, error = false) {
  $('notice').hidden = false;
  $('notice').textContent = message;
  $('notice').dataset.error = String(error);
  const dialog = document.querySelector('dialog[open]');
  if (dialog && dialog.id !== 'confirm-dialog') {
    const local = dialog.querySelector('.dialog-notice');
    local.textContent = message; local.dataset.error = String(error); local.hidden = false;
  }
}
async function api(path, body, surviveLock = false) {
  const started = epoch, controller = new AbortController();
  if (!surviveLock) controllers.add(controller);
  const options = {credentials: 'same-origin', headers: {Accept: 'application/json'}, cache: 'no-store', signal: controller.signal};
  if (body !== undefined) {
    options.method = 'POST'; options.headers['Content-Type'] = 'application/json';
    options.headers['X-CSRF-Token'] = csrf; options.body = JSON.stringify(body);
  }
  try {
    let response;
    try { response = await fetch('api/admin/' + path, options); }
    catch (error) { if (ignored(error)) throw error; throw new Error('无法连接服务，请稍后手动重试'); }
    let data;
    try { data = await response.json(); } catch (error) { throw new Error('服务响应无法读取，请稍后重试'); }
    if (!surviveLock && started !== epoch) throw new StaleRequest();
    if (!response.ok || data.status !== 'ok') {
      if (response.status === 401 && path !== 'login' && !surviveLock) { lock(); throw new StaleRequest(); }
      throw new Error(data.msg || '请求失败，请稍后重试');
    }
    return data;
  } finally { controllers.delete(controller); }
}
async function run(button, task, group) {
  if (group && busy.has(group)) return;
  const started = epoch;
  if (group) busy.add(group);
  if (button) { button.disabled = true; button.setAttribute('aria-busy', 'true'); }
  updateDisabled();
  try { await task(); }
  catch (error) { if (started === epoch && !ignored(error)) notice(error.message || '无法连接服务，请稍后重试', true); }
  finally {
    if (started === epoch) {
      if (group) busy.delete(group);
      if (button) { button.disabled = false; button.removeAttribute('aria-busy'); }
      updateDisabled();
    }
  }
}
function updateDisabled() {
  const accountBusy = busy.has('account'), snapshotBusy = busy.has('snapshot');
  const ready = !!model.account?.local_session_ready && !model.accountError;
  for (const button of document.querySelectorAll('[data-command]')) {
    const command = button.dataset.command;
    if (['profile', 'credential', 'qr', 'verify', 'refresh'].includes(command))
      button.disabled = !csrf || accountBusy || snapshotBusy || (command !== 'profile' && !ready);
    else if (command === 'new-key') button.disabled = !csrf || busy.has('keys');
    else button.disabled = !csrf;
  }
  $('import-profile').disabled = !csrf || accountBusy;
  $('import-credential').disabled = !csrf || accountBusy || !ready;
  $('poll-qr').disabled = !csrf || accountBusy || !flow;
  $('cancel-qr').disabled = !csrf || accountBusy || !flow;
  $('create-key').disabled = !csrf || busy.has('keys');
  $('copy-key').disabled = !csrf || !$('new-key-secret').value;
  $('reload-state').disabled = !csrf || [...busy].some(group => group !== 'history');
  $('save-settings').disabled = !csrf || !model.settings || !!model.settingsError || busy.has('settings') || snapshotBusy;
  $('allow-external').disabled = $('save-settings').disabled;
  $('history-filter').disabled = !csrf || busy.has('history');
  $('previous-page').disabled = !csrf || busy.has('history') || pageNumber <= 1;
  $('next-page').disabled = !csrf || busy.has('history') || !hasMore;
  for (const button of document.querySelectorAll('[data-revoke]')) button.disabled = !csrf || busy.has('keys');
  const heroCommand = $('hero-action').dataset.command;
  if (!heroCommand) $('hero-action').disabled = true;
  else if (heroCommand === 'reload') $('hero-action').disabled = !csrf || busy.size > 0;
  $('status-hero').setAttribute('aria-busy', String(accountBusy || snapshotBusy));
  $('login-submit').disabled = busy.has('login') || logoutPending;
  restoreFocus();
}
function chooseTab(name) {
  if (!pageLabels[name]) return;
  pendingFocus = null;
  $('notice').hidden = true;
  for (const button of document.querySelectorAll('[data-tab]')) {
    const active = button.dataset.tab === name;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  }
  for (const panel of document.querySelectorAll('.tab-panel')) panel.hidden = panel.id !== 'tab-' + name;
  $('page-title').textContent = pageLabels[name][0];
  $('breadcrumb-page').textContent = pageLabels[name][0];
  $('page-description').textContent = pageLabels[name][1];
}
function hero(state, title, description, action, command) {
  $('status-hero').dataset.state = state;
  $('hero-label').textContent = state === 'valid' ? '最近观察' : '服务状态';
  $('hero-title').textContent = title; $('hero-description').textContent = description;
  $('hero-action').textContent = action;
  if (command) $('hero-action').dataset.command = command; else delete $('hero-action').dataset.command;
}
function renderHero() {
  const account = model.account;
  if (model.accountError) hero('warning', '状态读取失败', '无法读取当前状态。此前记录保留，请刷新后再判断。', '重新读取', 'reload');
  else if (!account) hero('unknown', '正在读取服务状态', '只读取本地状态，不会主动联系官方。', '正在读取…', '');
  else if (!account.local_session_ready) hero('warning', '先配置设备会话', '导入已登记设备的会话后，再核对账号与签名状态。', '导入设备会话', 'profile');
  else {
    const observations = account.observations || {}, a = observations.account || {}, s = observations.signing || {};
    const latest = [...(observations.events || [])].reverse().find(event => ['verify', 'refresh', 'search', 'login'].includes(event.event));
    if (s.state === 'invalid') hero('invalid', '签名会话需要更新', '官方已确认签名失效，请重新导入更新后的设备会话。账号状态单独记录。', '更新设备会话', 'profile');
    else if (a.state === 'invalid') hero('invalid', '官方账号需要重新登录', '官方已确认账号失效。重新登录后再核对当前会话。', '扫码重新登录', 'qr');
    else if (!account.has_account_credential) hero('warning', '设备已配置，等待账号登录', '使用作业帮 App 扫码登录，或在账号与会话中导入新凭据。', '扫码登录', 'qr');
    else if (a.state !== 'valid' || s.state !== 'valid') hero('warning', '会话已导入，等待核对', '本地配置已保存，官方有效性尚未确认。点击核对获取真实结果。', '核对账号', 'verify');
    else if (latest && ['network', 'protocol', 'upstream'].includes(latest.kind)) hero('warning', '此前核对正常，最近请求失败', (kindNames[latest.kind] || '请求失败') + '。可稍后手动重试，当前记录不判为失效。', '重新核对', 'verify');
    else if (model.keysError) hero('warning', '账号已验证，密钥状态读取失败', '账号与签名的最近核对正常。请刷新以确认调用密钥状态。', '重新读取', 'reload');
    else if (!model.keys) hero('unknown', '账号与签名已验证', '正在读取客户端调用权限。', '正在读取…', '');
    else if (!model.keys.some(key => key.state === 'active')) hero('warning', '会话已核对，等待客户端配置', '为 OMRS 生成调用密钥，再填写服务地址。', '生成调用密钥', 'new-key');
    else hero('valid', '最近核对正常', '设备已配置，账号与签名最近均已验证。已有调用密钥，可在 OMRS 中测试连接。', '查看账号与会话', 'account');
  }
  updateDisabled();
}
function renderAccount(account) {
  reads.account++;
  model.account = account; model.accountError = ''; readAt = Date.now();
  const ready = account.local_session_ready, credential = account.has_account_credential;
  const observations = account.observations || {}, a = observations.account || {}, s = observations.signing || {};
  const state = part => ready ? (part.state || 'unknown') : '';
  badge('account-state', ready ? '设备已配置' : '未配置', ready ? 'valid' : 'unknown');
  badge('device-badge', ready ? '已配置' : '未配置', ready ? 'valid' : 'unknown');
  badge('account-badge', !ready ? '未配置' : !credential ? '待登录' : (stateNames[a.state] || '待核对'), state(a));
  badge('signing-badge', ready ? (stateNames[s.state] || '待核对') : '未配置', state(s));
  $('device-value').textContent = ready ? '本地信息已就绪' : '等待设备导入';
  $('device-detail').textContent = ready ? '配置已保存，官方有效性见签名状态。' : '需要已登记设备的会话文件。';
  $('account-value').textContent = !ready ? '等待设备配置' : !credential ? '等待账号登录' : (stateNames[a.state] || '待核对');
  $('signing-value').textContent = ready ? (stateNames[s.state] || '待核对') : '等待设备配置';
  for (const [id, part] of [['account-detail', a], ['signing-detail', s]]) {
    $(id).textContent = !ready ? '配置设备后才能核对。' : part.state === 'invalid' ? '首次确认失效：' + when(part.first_invalid_at) : part.last_success_at ? '最近成功：' + when(part.last_success_at) : '官方有效性尚未确认。';
  }
  $('summary-device').textContent = $('account-device-detail').textContent = ready ? '已配置' : '未配置';
  $('summary-credential').textContent = $('account-credential-detail').textContent = credential ? '已保存 · 不回显' : '未配置';
  $('summary-verified').textContent = when(a.last_success_at);
  $('last-read').textContent = '最近读取 ' + new Date(readAt).toLocaleTimeString('zh-CN', {hour12: false});
  $('observations').replaceChildren();
  for (const [part, label] of [[a, '官方账号'], [s, '签名会话']]) {
    const article = text('div', '', 'observation-item'), heading = text('h3', label);
    const mark = text('span', ready ? (stateNames[part.state] || '待核对') : '未配置', 'badge'); mark.dataset.state = state(part); heading.append(mark);
    article.append(heading, text('p', '最近成功：' + when(part.last_success_at)), text('p', '首次确认失效：' + when(part.first_invalid_at)));
    if (part.first_invalid_at) article.append(text('p', '此前成功至首次失效：' + when(part.valid_until_after) + ' → ' + when(part.first_invalid_at)));
    if (part.imported_at) article.append(text('p', '最近导入：' + when(part.imported_at)));
    $('observations').append(article);
  }
  $('recent-activity').replaceChildren();
  for (const event of (observations.events || []).slice(-5).reverse()) {
    const li = text('li', ''), dot = text('span', '', 'activity-dot'), copy = text('div', '', 'activity-copy');
    dot.dataset.state = event.event === 'profile_import' ? 'warning' : event.kind === 'ok' ? 'valid' : ['login_required', 'signing_session'].includes(event.kind) ? 'invalid' : 'warning';
    dot.setAttribute('aria-hidden', 'true');
    copy.append(text('strong', eventNames[event.event] || '服务观察'), text('span', event.event === 'profile_import' ? '已保存 · 等待核对' : (kindNames[event.kind] || '结果未知')));
    const at = text('time', when(event.at)); if (event.at) at.dateTime = new Date(event.at * 1000).toISOString();
    li.append(dot, copy, at); $('recent-activity').append(li);
  }
  if (!(observations.events || []).length) $('recent-activity').append(text('li', '暂无活动。配置设备后，核对结果会记录在这里。', 'empty-state'));
  renderHero();
}
async function loadAccount() {
  const request = ++reads.account;
  try {
    const data = await api('account');
    if (request === reads.account) renderAccount(data.account);
  } catch (error) {
    if (!ignored(error) && request === reads.account) {
      model.accountError = error.message; $('last-read').textContent = readAt ? '读取失败 · 保留上次结果' : '读取失败'; renderHero();
    }
    throw error;
  }
}
function renderKeys() {
  $('key-list').replaceChildren();
  if (model.keysError) $('key-list').append(text('p', '密钥列表读取失败，请刷新重试。此前记录保留。', 'inline-error'));
  if (!model.keys) {
    if (!model.keysError) $('key-list').append(text('article', '正在读取调用密钥…', 'card empty-state'));
    badge('connection-badge', model.keysError ? '读取失败' : '读取中', 'warning');
  } else {
    const selected = $('history-key').value;
    $('history-key').replaceChildren(); const all = text('option', '全部密钥'); all.value = ''; $('history-key').append(all);
    if (!model.keys.length) $('key-list').append(text('article', '暂无调用密钥。生成一个后，将它配置到 OMRS。', 'card empty-state'));
    for (const key of model.keys) {
      const row = text('article', '', 'card key-row'), detail = text('div', ''), heading = text('div', '', 'key-name');
      const mark = text('span', key.state === 'active' ? '有效' : '已吊销', 'badge'); mark.dataset.state = key.state === 'active' ? 'valid' : '';
      heading.append(text('strong', key.name), mark);
      detail.append(heading, text('p', key.prefix + '… · 指纹 ' + key.fingerprint), text('code', 'ID ' + key.id), text('p', '创建 ' + when(key.created_at) + ' · 最近使用 ' + when(key.last_used_at)));
      row.append(detail);
      if (key.state === 'active') {
        const button = text('button', '吊销', 'danger'); button.dataset.revoke = key.id;
        button.addEventListener('click', () => run(button, async () => {
          const confirmed = await confirmAction('吊销调用密钥', '吊销“' + key.name + '”后，使用它的客户端将立即失去调用权限。', '确认吊销');
          if (!confirmed) return;
          await api('keys/revoke', {id: key.id});
          await loadKeys(); notice('调用密钥已吊销');
        }, 'keys'));
        row.append(button);
      }
      $('key-list').append(row);
      const option = text('option', key.name + ' / ' + key.id); option.value = key.id; $('history-key').append(option);
    }
    $('history-key').value = selected;
    const active = model.keys.filter(key => key.state === 'active');
    badge('connection-badge', model.keysError ? '保留上次结果' : active.length ? '已有调用密钥' : '待配置密钥', model.keysError || !active.length ? 'warning' : 'valid');
    $('active-key-summary').textContent = active.length + ' 个';
    const usedAt = Math.max(0, ...active.map(key => key.last_used_at || 0));
    $('key-last-used').textContent = usedAt ? when(usedAt) : '暂无使用记录';
  }
  renderHero();
}
async function loadKeys() {
  const request = ++reads.keys;
  try { const data = await api('keys'); if (request === reads.keys) { model.keys = data.keys; model.keysError = ''; renderKeys(); } }
  catch (error) { if (!ignored(error) && request === reads.keys) { model.keysError = error.message; renderKeys(); } throw error; }
}
function renderSettings() {
  const settings = model.settings;
  if (!settings || model.settingsError) {
    $('access-state').textContent = settings ? '读取失败 · 保留此前范围' : model.settingsError ? '访问范围读取失败' : '正在读取…';
    $('access-state').dataset.state = 'warning'; badge('settings-badge', '读取失败', 'warning');
  } else {
    $('allow-external').checked = settings.allow_external;
    $('access-state').textContent = settings.allow_external ? '允许外部 · 鉴权必需' : '仅本机 · 鉴权必需';
    $('access-state').dataset.state = settings.allow_external ? 'warning' : 'valid';
    badge('settings-badge', settings.allow_external ? '允许外部' : '仅本机', settings.allow_external ? 'warning' : 'valid');
    const limits = settings.limits; $('limits').replaceChildren();
    for (const [value, label] of [[limits.api_per_minute, 'API / 分钟 / 密钥'], [limits.search_per_minute, '搜题 / 分钟 / 密钥'], [limits.search_daily_budget, '搜题 / UTC 日 / 全服务'], [limits.search_concurrency, '搜题并发']]) {
      const item = text('div', '', 'budget-item'); item.append(text('strong', value), text('span', label)); $('limits').append(item);
    }
  }
  updateDisabled();
}
async function loadSettings() {
  const request = ++reads.settings;
  try { const data = await api('settings'); if (request === reads.settings) { model.settings = data; model.settingsError = ''; renderSettings(); } }
  catch (error) { if (!ignored(error) && request === reads.settings) { model.settingsError = error.message; renderSettings(); } throw error; }
}
async function loadHistory() {
  const request = ++reads.history;
  const query = new URLSearchParams({page: String(pageNumber), page_size: '20'});
  for (const [id, key] of [['history-source', 'source'], ['history-result', 'result'], ['history-key', 'key_id']]) if ($(id).value) query.set(key, $(id).value);
  try {
    const data = await api('history?' + query); if (request !== reads.history) return;
    visiblePage = pageNumber = data.page; hasMore = data.has_more; $('history-error').hidden = true; $('history-rows').replaceChildren();
    for (const row of data.items) {
      const tr = document.createElement('tr');
      const values = [[when(row.time), eventNames[row.action] || row.action], [row.source === 'local' ? '本机 / local' : '外部 / external', '客户端 ' + row.client_ip, '对端 ' + row.peer_ip], [row.key_id || '—', row.method + ' ' + row.path], [row.result + ' / ' + row.http_status, Number(row.latency_ms).toFixed(1) + ' ms']];
      for (const lines of values) { const td = document.createElement('td'); for (const line of lines) td.append(text('div', line)); tr.append(td); }
      $('history-rows').append(tr);
    }
    if (!data.items.length) { const tr = document.createElement('tr'), td = text('td', '没有匹配的请求记录', 'empty-state'); td.colSpan = 4; tr.append(td); $('history-rows').append(tr); }
    $('history-page').textContent = '第 ' + data.page + ' 页 · 共 ' + data.total + ' 条'; updateDisabled();
  } catch (error) {
    if (!ignored(error) && request === reads.history) { pageNumber = visiblePage; $('history-error').textContent = '记录读取失败，请重试。此前列表保留。'; $('history-error').hidden = false; }
    throw error;
  }
}
async function refreshAll() {
  const started = epoch;
  const results = await Promise.allSettled([loadAccount(), loadKeys(), loadSettings(), run(null, loadHistory, 'history')]);
  if (started !== epoch) return;
  if (results.some(result => result.status === 'rejected' && !ignored(result.reason))) notice('部分状态读取失败，请刷新重试。此前结果保留。', true);
}
function clearKey() { $('new-key-secret').value = ''; $('new-key').hidden = true; $('key-form').hidden = false; $('key-name').value = ''; $('key-title').textContent = '生成调用密钥'; }
function clearQr() { $('qr-image').removeAttribute('src'); $('qr-image').hidden = true; $('qr-expiry').textContent = ''; flow = ''; $('poll-qr').disabled = true; $('cancel-qr').disabled = true; }
function cleanupDialog(id) {
  if (id in dialogVersions) dialogVersions[id]++;
  const local = $(id).querySelector('.dialog-notice'); local.hidden = true; local.textContent = '';
  if (id === 'profile-dialog') { $('profile-file').value = ''; $('profile-json').value = ''; $('profile-paste').open = false; $('profile-file-note').textContent = '最多 256 KiB，包含 fields、headers 与 session_token。'; }
  if (id === 'credential-dialog') $('account-credential').value = '';
  if (id === 'key-dialog') clearKey();
  if (id === 'qr-dialog') {
    const closingFlow = flow; clearQr(); $('qr-state').textContent = ''; $('restart-qr').hidden = true;
    if (closingFlow && csrf) cancelClosedFlow(closingFlow);
  }
  if (id === 'confirm-dialog' && confirmResolve) { const resolve = confirmResolve; confirmResolve = null; resolve(false); }
}
function restoreFocus() {
  if (!pendingFocus) return;
  if (!pendingFocus.isConnected || !pendingFocus.checkVisibility()) { pendingFocus = null; return; }
  if (!pendingFocus.disabled) { pendingFocus.focus(); pendingFocus = null; }
}
function closeDialog(id) {
  const wasOpen = $(id).open;
  cleanupDialog(id);
  if (wasOpen) { $(id).close(); pendingFocus = dialogOpeners.get(id) || null; restoreFocus(); }
  dialogOpeners.delete(id);
}
function showDialog(id, opener = document.activeElement) {
  if (!csrf) return;
  pendingFocus = null;
  const local = $(id).querySelector('.dialog-notice'); local.hidden = true; local.textContent = '';
  if (id in dialogVersions) dialogVersions[id]++;
  if (!$(id).open) { dialogOpeners.set(id, opener); $(id).showModal(); }
}
function confirmAction(title, description, label) {
  $('confirm-title').textContent = title; $('confirm-description').textContent = description; $('confirm-submit').textContent = label;
  showDialog('confirm-dialog'); $('confirm-cancel').focus();
  return new Promise(resolve => { confirmResolve = resolve; });
}
async function cancelClosedFlow(id) {
  const started = epoch;
  try { await api('account', {operation: 'qr_cancel', flow_id: id}); if (started === epoch) await loadAccount(); }
  catch (error) { if (started === epoch && !ignored(error)) notice('二维码已从本页清除，但未确认服务端取消。该登录流程最多保留 5 分钟。', true); }
}
function renderQr(result) {
  flow = result.flow_id || flow;
  $('qr-state').textContent = result.message || '等待 App 扫码确认';
  $('qr-expiry').textContent = result.expires_at ? '本次登录流程截止 ' + when(result.expires_at) : '';
  if (result.qr_image) { $('qr-image').src = result.qr_image; $('qr-image').hidden = false; }
  if (['authenticated', 'cancelled', 'expired', 'missing', 'replaced', 'session_changed'].includes(result.state)) {
    clearQr(); $('restart-qr').hidden = false;
  } else $('restart-qr').hidden = !!flow;
  updateDisabled();
}
async function startQr(button) {
  await run(button, async () => {
    clearQr(); showDialog('qr-dialog', button); const version = dialogVersions['qr-dialog'];
    $('qr-state').textContent = '正在创建二维码…'; $('restart-qr').hidden = true;
    try {
      const data = await api('account', {operation: 'qr_start'}); renderAccount(data.account);
      if ($('qr-dialog').open && version === dialogVersions['qr-dialog']) renderQr(data.result);
      else if (data.result.flow_id) await cancelClosedFlow(data.result.flow_id);
    } catch (error) {
      if (version === dialogVersions['qr-dialog']) { $('qr-state').textContent = '二维码创建失败，请重试。'; $('restart-qr').hidden = false; }
      throw error;
    }
  }, 'account');
}
function lock() {
  epoch++; csrf = ''; busy.clear();
  for (const controller of controllers) controller.abort(); controllers.clear();
  model = emptyModel(); readAt = 0; visiblePage = pageNumber = 1; hasMore = false;
  for (const key of Object.keys(reads)) reads[key]++;
  for (const dialog of document.querySelectorAll('dialog')) closeDialog(dialog.id);
  document.body.classList.add('locked');
  for (const id of ['dashboard', 'management-nav', 'admin-footer', 'topbar']) $(id).hidden = true;
  $('login-view').hidden = false; $('admin-password').value = '';
  for (const button of document.querySelectorAll('[aria-busy]')) { button.removeAttribute('aria-busy'); button.disabled = false; }
  $('notice').hidden = true; $('notice').textContent = '';
  $('key-list').replaceChildren(); $('history-rows').replaceChildren(); $('observations').replaceChildren(); $('recent-activity').replaceChildren();
  $('history-form').reset(); $('history-key').replaceChildren(text('option', '全部密钥')); $('history-key').firstChild.value = '';
  $('history-error').hidden = true; $('allow-external').checked = false; $('limits').textContent = '正在读取…';
  $('history-page').textContent = '正在读取…'; $('last-read').textContent = '正在读取状态…';
  for (const id of ['summary-device', 'summary-credential', 'summary-verified', 'active-key-summary', 'key-last-used', 'account-device-detail', 'account-credential-detail', 'device-value', 'account-value', 'signing-value']) $(id).textContent = '—';
  for (const id of ['device-badge', 'account-badge', 'signing-badge', 'account-state', 'connection-badge', 'settings-badge']) badge(id, '读取中');
  for (const id of ['device-detail', 'account-detail', 'signing-detail', 'access-state']) $(id).textContent = '';
  renderHero();
}
async function unlock(session) {
  csrf = session.csrf_token; $('admin-password').value = ''; document.body.classList.remove('locked');
  $('login-view').hidden = true;
  for (const id of ['dashboard', 'management-nav', 'admin-footer', 'topbar']) $(id).hidden = false;
  chooseTab('overview'); renderHero(); await run(null, refreshAll, 'snapshot');
}
async function command(name, button) {
  if (pageLabels[name]) { chooseTab(name); if (name === 'history') await run($('history-filter'), loadHistory, 'history'); }
  else if (name === 'profile') showDialog('profile-dialog');
  else if (name === 'credential') showDialog('credential-dialog');
  else if (name === 'new-key') { clearKey(); showDialog('key-dialog'); }
  else if (name === 'qr') await startQr(button);
  else if (name === 'reload') await run($('reload-state'), refreshAll, 'snapshot');
  else if (['verify', 'refresh'].includes(name)) await run(button, async () => {
    notice(name === 'verify' ? '正在核对官方账号…' : '正在刷新官方账号…');
    try { const data = await api('account', {operation: name}); renderAccount(data.account); notice(name === 'verify' ? '账号核对完成' : '账号刷新完成'); }
    finally { try { await loadAccount(); } catch (error) { /* 保留官方结果与读取失败状态，由操作回执显示错误。 */ } }
  }, 'account');
}
for (const dialog of document.querySelectorAll('dialog')) {
  const local = text('div', '', 'notice dialog-notice'); local.hidden = true; local.setAttribute('role', 'status'); local.setAttribute('aria-live', 'polite');
  dialog.querySelector('.dialog-heading').after(local);
  dialog.addEventListener('cancel', event => { event.preventDefault(); closeDialog(dialog.id); });
  dialog.addEventListener('close', () => { if (!dialog.open) cleanupDialog(dialog.id); });
}
for (const button of document.querySelectorAll('[data-close]')) button.addEventListener('click', () => closeDialog(button.dataset.close));
for (const button of document.querySelectorAll('[data-tab]')) button.addEventListener('click', () => command(button.dataset.tab, button));
for (const button of document.querySelectorAll('[data-command], #hero-action')) button.addEventListener('click', () => command(button.dataset.command, button));
$('reload-state').addEventListener('click', () => command('reload', $('reload-state')));
$('login-form').addEventListener('submit', event => {
  event.preventDefault();
  if (busy.has('login') || logoutPending) return;
  const password = $('admin-password').value;
  // 用户开始登录时，旧的会话探测不得再锁住本次登录。
  epoch++; for (const controller of controllers) controller.abort(); controllers.clear();
  run($('login-submit'), async () => {
    try { const session = await api('login', {password}); $('notice').hidden = true; await unlock(session); }
    finally { $('admin-password').value = ''; }
  }, 'login');
});
$('logout').addEventListener('click', async () => {
  logoutPending = true;
  const request = api('logout', {}, true); lock(); const lockedEpoch = epoch;
  try { await request; if (epoch === lockedEpoch) notice('已退出管理会话'); }
  catch (error) { if (epoch === lockedEpoch) notice('本页敏感信息已清除，退出请求失败。请刷新后重新退出。', true); }
  finally { logoutPending = false; updateDisabled(); }
});
$('profile-file').addEventListener('change', () => {
  const file = $('profile-file').files[0];
  if (file?.size > 256 * 1024) { $('profile-file').value = ''; notice('设备会话超过 256 KiB，请选择较小的文件', true); return; }
  if (file) { $('profile-json').value = ''; $('profile-file-note').textContent = '已选择 ' + file.name + '，导入时使用该文件。'; }
});
$('profile-json').addEventListener('input', () => { $('profile-file').value = ''; $('profile-file-note').textContent = '将使用粘贴的 JSON 导入。'; });
$('profile-form').addEventListener('submit', event => {
  event.preventDefault(); run($('import-profile'), async () => {
    const started = epoch, version = dialogVersions['profile-dialog'];
    const file = $('profile-file').files[0]; const raw = file ? await file.text() : $('profile-json').value;
    if (started !== epoch || version !== dialogVersions['profile-dialog']) throw new StaleRequest();
    let profile; try { profile = JSON.parse(raw); } catch (error) { throw new Error('设备会话 JSON 不合法，请检查内容后重试'); }
    const data = await api('profile', {profile}); renderAccount(data.account);
    if (version === dialogVersions['profile-dialog']) closeDialog('profile-dialog');
    notice('设备会话已导入，等待核对官方有效性');
  }, 'account');
});
$('credential-form').addEventListener('submit', event => {
  event.preventDefault(); run($('import-credential'), async () => {
    const version = dialogVersions['credential-dialog']; const data = await api('credential', {credential: $('account-credential').value}); renderAccount(data.account);
    if (version === dialogVersions['credential-dialog']) closeDialog('credential-dialog'); notice('账号凭据已导入，等待核对官方有效性');
  }, 'account');
});
for (const [id, operation] of [['poll-qr', 'qr_poll'], ['cancel-qr', 'qr_cancel']]) $(id).addEventListener('click', () => run($(id), async () => {
  const version = dialogVersions['qr-dialog'];
  try { const data = await api('account', {operation, flow_id: flow}); renderAccount(data.account); if ($('qr-dialog').open && version === dialogVersions['qr-dialog']) renderQr(data.result); }
  finally { try { await loadAccount(); } catch (error) { /* 本地状态读取失败由概览提示，不能覆盖扫码回执。 */ } }
}, 'account'));
$('key-form').addEventListener('submit', event => {
  event.preventDefault(); run($('create-key'), async () => {
    const version = dialogVersions['key-dialog']; const data = await api('keys', {name: $('key-name').value});
    if ($('key-dialog').open && version === dialogVersions['key-dialog']) {
      $('key-name').value = ''; $('new-key-secret').value = data.key; $('new-key').hidden = false; $('key-form').hidden = true; $('key-title').textContent = '调用密钥已生成';
      updateDisabled(); $('copy-key').focus(); notice('密钥已生成，请复制保存。关闭后无法找回。');
    } else notice('密钥已生成，但窗口已关闭，完整值已丢弃。请在调用密钥中吊销后重新生成。', true);
    await loadKeys();
  }, 'keys');
});
async function copyValue(input, message) {
  const value = input.value; if (!value) return;
  const started = epoch;
  try { await navigator.clipboard.writeText(value); }
  catch (error) { if (started !== epoch) throw new StaleRequest(); input.focus(); input.select(); if (!document.execCommand('copy')) throw new Error('无法自动复制，请选中内容手动复制'); }
  if (started !== epoch) throw new StaleRequest(); notice(message);
}
$('copy-key').addEventListener('click', () => run($('copy-key'), () => copyValue($('new-key-secret'), '密钥已复制，请粘贴到客户端设置')));
$('copy-address').addEventListener('click', () => run($('copy-address'), () => copyValue($('service-address'), '服务地址已复制')));
$('dismiss-key').addEventListener('click', () => closeDialog('key-dialog'));
$('confirm-cancel').addEventListener('click', () => closeDialog('confirm-dialog'));
$('confirm-submit').addEventListener('click', () => { const resolve = confirmResolve; confirmResolve = null; closeDialog('confirm-dialog'); if (resolve) resolve(true); });
$('history-form').addEventListener('submit', event => { event.preventDefault(); pageNumber = 1; run($('history-filter'), loadHistory, 'history'); });
$('previous-page').addEventListener('click', () => { if (pageNumber > 1) { pageNumber--; run($('previous-page'), loadHistory, 'history'); } });
$('next-page').addEventListener('click', () => { if (hasMore) { pageNumber++; run($('next-page'), loadHistory, 'history'); } });
$('save-settings').addEventListener('click', () => run($('save-settings'), async () => {
  const allow_external = $('allow-external').checked;
  if (allow_external && !model.settings.allow_external) {
    if (!await confirmAction('允许外部访问', '开启前需完成 HTTPS、可信 Host 与反向代理配置。此操作不会修改监听地址或防火墙。', '确认开启')) { $('allow-external').checked = model.settings.allow_external; return; }
  }
  await api('settings', {allow_external}); await loadSettings(); notice('访问设置已保存');
}, 'settings'));
const address = new URL('./', window.location.href); address.search = ''; address.hash = '';
$('service-address').value = address.href.replace(/\/$/, '');
window.addEventListener('pagehide', lock);
async function restoreSession() { try { await unlock(await api('session')); } catch (error) { if (!ignored(error)) lock(); } }
window.addEventListener('pageshow', event => { if (event.persisted) restoreSession(); });
restoreSession();
