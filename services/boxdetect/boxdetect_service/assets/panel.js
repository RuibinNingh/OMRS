/** 独立框选面板；会话、密钥与图片只留在当前页面内存。 */
const $ = id => document.getElementById(id);
const titles = { overview: ['服务概览', '查看服务状态与最近的框选任务。'], test: ['框选测试', '上传一张图片，查看当前在线模型的实际框选效果。'], keys: ['调用密钥', '为每个客户端创建独立 Key，随时查看使用情况或吊销。'], history: ['请求历史', '回看每次上传的原图、框选结果和当时使用的模型。'], models: ['模型管理', '查看已登记模型，应用新模型或恢复上一模型。'], settings: ['服务设置', '管理对外访问、接单状态与记录留存。'] };
const labels = { running: '处理中', success: '成功', failure: '失败', interrupted: '已中断', done: '完成', failed: '失败', inbox: '收件箱', draft: '聊天草稿', test: '面板测试', api: 'API', legacy: '旧协议', admin: '管理员测试' };
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const date = value => value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'Asia/Shanghai' }).format(new Date(value * 1000)) : '—';
const id = () => [...crypto.getRandomValues(new Uint8Array(16))].map(v => v.toString(16).padStart(2, '0')).join('');
let csrf = '', page = 'overview', epoch = 0, keyEpoch = 0, detailEpoch = 0, modelRevision = 0, currentStatus = null, keyNames = [], active = true;
let imageURL = '', detailURL = '', filter = { page: 1, key_id: '', state: '', source: '', q: '' };
const pending = new Set();
function notice(message, error = false) { $('notice').innerHTML = message ? `<p class="notice${error ? ' error' : ''}">${esc(message)}</p>` : ''; }
function clearImage() { if (imageURL) URL.revokeObjectURL(imageURL); imageURL = ''; }
function closeDetail() { detailEpoch++; if (detailURL) URL.revokeObjectURL(detailURL); detailURL = ''; $('detail-content').replaceChildren(); $('detail-dialog').close(); }
function closeKey() { keyEpoch++; $('created-key').value = ''; $('key-name').value = ''; $('key-secret').hidden = true; $('key-form').hidden = false; $('key-error').textContent = ''; $('key-dialog').close(); }
function locked() {
  csrf = ''; epoch++; closeKey(); closeDetail(); clearImage(); testFile = null;
  $('logout').hidden = true; $('connection').textContent = '需要登录'; $('content').innerHTML = '<section class="card empty"><h2>管理会话已结束</h2><p>重新登录以查看服务信息。</p><button class="primary" data-action="login">管理员登录</button></section>';
}
async function request(path, body, { raw = false, unauthenticated = false } = {}) {
  const controller = new AbortController(); pending.add(controller);
  const timer = setTimeout(() => controller.abort(), body?.image ? 120000 : 45000);
  try {
    const response = await fetch(path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store', headers: body === undefined ? {} : { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal });
    if (response.status === 401 && !unauthenticated) locked();
    if (raw && response.ok) return response.blob();
    const data = await response.json();
    if (!response.ok || data.status === 'error') throw new Error(data.msg || '服务暂不可用');
    return data;
  } catch (error) { if (error.name === 'AbortError') throw new Error('请求等待已结束，请刷新核对服务端结果。'); throw error; }
  finally { clearTimeout(timer); pending.delete(controller); }
}
const fact = (name, value) => `<div class="fact"><span>${esc(name)}</span><strong>${esc(value)}</strong></div>`;
function table(items, compact = false) {
  if (!items.length) return '<div class="empty"><h2>还没有框选记录</h2><p>完成一次测试或客户端框选后，记录会显示在这里。</p></div>';
  return `<div class="table-wrap"><table><thead><tr><th>时间 / 请求编号</th><th>来源</th><th>调用方</th><th>结果</th><th>耗时</th><th></th></tr></thead><tbody>${items.map(r => `<tr><td>${date(r.time)}<small>${esc(r.request_id.slice(0, 12))}</small></td><td>${esc(labels[r.source] || r.source)}</td><td>${esc(r.key_name || labels[r.key_id] || r.key_id)}<small>${esc(r.client_ip)}</small></td><td><span class="badge">${esc(labels[r.state] || r.state)}</span></td><td>${esc(r.elapsed_ms)} ms</td><td><button data-detail="${esc(r.id)}">查看详情</button></td></tr>`).join('')}</tbody></table></div>${compact ? '' : `<div class="pagination"><span>共 ${esc(filter.total || items.length)} 条 · 第 ${filter.page} 页</span><div><button data-action="prev" ${filter.page <= 1 ? 'disabled' : ''}>上一页</button> <button data-action="next" ${!filter.has_more ? 'disabled' : ''}>下一页</button></div></div>`}`;
}
function preview(url, result, target = 'result-preview') {
  const width = Number(result.width), height = Number(result.height);
  const boxes = (result.boxes || []).filter(b => ['question', 'answer'].includes(b.role) && ['x', 'y', 'w', 'h'].every(k => Number.isFinite(b[k])));
  return `<div class="legend"><span class="question">■ 题目框</span><span class="answer">■ 答案框</span><span>共 ${boxes.length} 框</span></div><div class="actions"><button data-zoom="${target}">切换原图缩放</button><button data-boxes="${target}">显示 / 隐藏框</button></div><div class="preview" id="${target}"><div class="preview-inner"><img src="${esc(url)}" alt="上传原图"><svg viewBox="0 0 ${width} ${height}" aria-label="框选叠加层">${boxes.map(b => `<rect x="${b.x * width}" y="${b.y * height}" width="${b.w * width}" height="${b.h * height}" fill="none" stroke="${b.role === 'question' ? '#4267e8' : '#1a9c69'}" stroke-width="2" vector-effect="non-scaling-stroke"><title>${b.role === 'question' ? '题目' : '答案'} ${Math.round((b.conf || 0) * 100)}%</title></rect>`).join('')}</svg></div></div>`;
}
async function render() {
  if (!csrf || !active) return;
  const gen = ++epoch, selected = page;
  $('page-title').textContent = titles[page][0]; $('page-description').textContent = titles[page][1]; notice('');
  document.querySelectorAll('[data-page]').forEach(button => { if (button.dataset.page === page) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current'); });
  $('content').innerHTML = '<div class="loading" role="status">正在读取服务信息…</div>';
  try {
    let markup = '';
    if (selected === 'overview') {
      const [s, h] = await Promise.all([request('api/admin/overview'), request('api/admin/history')]); currentStatus = s;
      const counts = s.counts || {};
      markup = `<div class="stats">${[['今日框选', Object.values(counts).reduce((a, b) => a + b, 0)], ['成功', counts.success || 0], ['失败 / 中断', (counts.failure || 0) + (counts.interrupted || 0)], ['等待处理', s.waiting]].map(([k, v]) => `<div class="stat"><span>${k}</span><strong>${esc(v)}</strong></div>`).join('')}</div><div class="grid"><section class="card"><div class="card-head"><div><h2>在线模型</h2><p class="card-sub">当前实际加载并用于框选的模型</p></div><span class="badge">${s.paused ? '已暂停接单' : '正在服务'}</span></div><div class="facts">${fact('模型名称', s.model.name)}${fact('输入尺寸', s.model.imgsz)}${fact('置信度阈值', s.model.conf)}${fact('模型指纹', s.model.sha256.slice(0, 16))}</div><div class="actions"><button class="primary" data-page="test">测试框选</button><button data-action="pause">${s.paused ? '恢复接单' : '暂停接单'}</button></div></section><section class="card"><h2>连接到 OMRS</h2><p class="card-sub">将服务地址与调用 Key 填入设置。</p><div class="facts">${fact('图片上限', '15 MiB / 4000 万像素')}${fact('每 Key 每分钟', s.limits.per_key_per_minute + ' 次')}${fact('历史留存', s.history_retention.days + ' 天')}</div><div class="actions"><button data-page="keys">管理调用 Key</button></div></section></div><section class="card"><div class="card-head"><h2>最近框选</h2><button class="quiet" data-page="history">查看全部</button></div>${table(h.items.slice(0, 5), true)}</section>`;
      $('connection').textContent = s.paused ? '已暂停接单' : '服务在线';
    } else if (selected === 'test') {
      markup = '<section class="card"><div class="upload" id="drop-area"><div><h2>放入一张图片，开始框选</h2><p>支持拖入或粘贴 PNG、JPEG、GIF，最大 15 MiB。</p><input id="test-file" type="file" accept="image/png,image/jpeg,image/gif" aria-label="选择测试图片"></div></div><div class="actions"><button class="primary" data-action="detect">开始框选</button></div><div id="test-result"></div></section>';
    } else if (selected === 'keys') {
      const data = await request('api/admin/keys'); keyNames = data.keys;
      markup = `<section class="card"><div class="card-head"><div><h2>调用密钥</h2><p class="card-sub">Key 仅用于检测调用，不能管理服务或读取历史。</p></div><button class="primary" data-action="new-key">创建 Key</button></div>${!data.keys.length ? '<div class="empty"><h2>创建第一个调用密钥</h2><p>建议每个 OMRS 客户端单独使用一个 Key。</p></div>' : `<div class="table-wrap"><table><thead><tr><th>名称 / 指纹</th><th>创建时间</th><th>最近使用</th><th>今日调用</th><th>状态</th><th></th></tr></thead><tbody>${data.keys.map(k => `<tr><td>${esc(k.name)}<small>${esc(k.fingerprint)}</small></td><td>${date(k.created_at)}</td><td>${date(k.last_used_at)}</td><td>${esc(data.key_usage.find(u => u.key_id === k.id)?.calls || 0)}</td><td>${k.state === 'active' ? '有效' : '已吊销'}</td><td>${k.state === 'active' ? `<button class="danger" data-revoke="${esc(k.id)}">吊销</button>` : ''}</td></tr>`).join('')}</tbody></table></div>`}</section>`;
    } else if (selected === 'history') {
      const query = new URLSearchParams(Object.entries(filter).filter(([k, v]) => !['total', 'has_more'].includes(k) && v));
      const [data, keys] = await Promise.all([request('api/admin/history?' + query), request('api/admin/keys')]);
      Object.assign(filter, { total: data.total, has_more: data.has_more }); keyNames = keys.keys;
      markup = `<section class="card"><div class="filters"><div><label for="filter-state">结果</label><select id="filter-state" data-filter="state">${[['', '全部结果'], ['success', '成功'], ['failure', '失败'], ['interrupted', '已中断'], ['running', '处理中']].map(([v, t]) => `<option value="${v}" ${filter.state === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div><div><label for="filter-source">调用入口</label><select id="filter-source" data-filter="source">${[['', '全部入口'], ...['inbox', 'draft', 'test', 'api', 'legacy'].map(v => [v, labels[v]])].map(([v, t]) => `<option value="${v}" ${filter.source === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div><div><label for="filter-key">调用 Key</label><select id="filter-key" data-filter="key_id"><option value="">全部 Key</option>${keys.keys.map(k => `<option value="${esc(k.id)}" ${filter.key_id === k.id ? 'selected' : ''}>${esc(k.name)}</option>`).join('')}</select></div></div>${table(data.items)}</section><p class="muted">原图可能因保留期限或容量清理而不再可用，框选结果与模型信息按记录期限保留。</p>`;
    } else if (selected === 'models') {
      const data = await request('api/admin/models'); modelRevision = data.revision;
      markup = `<section class="card"><div class="card-head"><div><h2>已登记模型</h2><p class="card-sub">选择模型不会自动切换，应用失败保留原模型。</p></div>${data.models.some(m => m.id === 'previous') ? '<button data-model="previous">恢复上一模型</button>' : ''}</div><div class="model-list">${data.models.map(m => `<div class="model-row"><div><strong>${esc(m.model.name)}</strong> ${m.current ? '<span class="badge">当前在线</span>' : ''}<p>${esc(m.model.imgsz)} · 阈值 ${esc(m.model.conf)} · SHA ${esc(m.model.sha256.slice(0, 16))}</p></div>${m.current || m.id === 'previous' ? '' : `<button data-model="${esc(m.id)}">应用模型</button>`}</div>`).join('')}</div><p class="card-sub">候选模型由服务器维护者本地登记，训练实验通过 OMRS 的训练入口查看。</p></section><section class="card"><h2>模型操作历史</h2>${data.history.length ? `<div class="table-wrap"><table><thead><tr><th>时间</th><th>操作</th><th>结果</th><th>说明</th></tr></thead><tbody>${data.history.map(h => `<tr><td>${date(h.time)}</td><td>${h.action === 'rollback' ? '恢复上一模型' : '应用模型'}</td><td>${esc(labels[h.state] || h.state)}</td><td>${esc(h.error || '—')}</td></tr>`).join('')}</tbody></table></div>` : '<p class="card-sub">还没有模型操作记录。</p>'}</section>`;
    } else if (selected === 'settings') {
      const s = await request('api/admin/settings'); currentStatus = s;
      markup = `<form id="settings-form"><section class="card"><h2>访问与接单</h2><div class="check-row"><label for="allow-external">允许对外调用<small>外部调用仍须 Key；监听与 HTTPS 由部署配置决定。</small></label><input id="allow-external" type="checkbox" ${s.allow_external ? 'checked' : ''}></div><div class="check-row"><label for="paused">暂停接收新任务<small>管理面板保持可用，可随时恢复。</small></label><input id="paused" type="checkbox" ${s.paused ? 'checked' : ''}></div></section><section class="card"><h2>调用与记录留存</h2><p class="card-sub">历史原图仅管理员可见，不会自动进入训练集。</p><div class="field"><label for="rate">每 Key 每分钟最多调用</label><input id="rate" type="number" min="1" max="100" required value="${esc(s.limits.per_key_per_minute)}"></div><div class="field"><label for="days">历史保留天数</label><input id="days" type="number" min="1" max="365" required value="${esc(s.history_retention.days)}"></div><div class="field"><label for="limit">历史最多条数</label><input id="limit" type="number" min="1" max="100000" required value="${esc(s.history_retention.limit)}"></div><div class="field"><label for="capacity">原图容量上限（MiB）</label><input id="capacity" type="number" min="1" max="2048" required value="${Math.round(s.history_retention.detail_bytes / 1024 ** 2)}"></div><button class="primary" type="submit">保存服务设置</button></section></form>`;
    }
    if (!active || gen !== epoch) return;
    $('content').innerHTML = markup;
  } catch (error) { if (active && gen === epoch) { $('content').innerHTML = '<section class="card empty"><h2>读取失败</h2><p>服务信息暂不可用，点击刷新重试。</p></section>'; notice(error.message, true); } }
}
async function detail(ident) {
  closeDetail(); $('detail-dialog').showModal(); $('detail-content').innerHTML = '<p class="muted">正在读取记录…</p>'; const gen = ++detailEpoch;
  try {
    const data = await request(`api/admin/history/${ident}`);
    if (gen !== detailEpoch || !$('detail-dialog').open) return;
    const item = data.item, result = item.response;
    $('detail-content').innerHTML = `<div class="facts">${fact('时间', date(item.time))}${fact('调用方', item.key_name || labels[item.key_id] || item.key_id)}${fact('模型', item.model.name + ' · ' + item.model.sha256.slice(0, 12))}${fact('结果', labels[item.state])}${fact('耗时', item.elapsed_ms + ' ms')}</div>${result?.msg ? `<p class="error">${esc(result.msg)}</p>` : ''}<div id="history-preview"><p class="muted">${data.image ? '正在读取原图…' : '原图未留存或已清理。'}</p></div><details><summary>完整返回数据</summary><pre>${esc(JSON.stringify(result, null, 2))}</pre></details>`;
    if (data.image) {
      const blob = await request(`api/admin/history/${ident}/image`, undefined, { raw: true });
      if (gen !== detailEpoch || !$('detail-dialog').open) return;
      detailURL = URL.createObjectURL(blob);
      const geometry = result?.width ? result : { ...data.image, boxes: [] };
      $('history-preview').innerHTML = preview(detailURL, geometry, 'history-overlay');
    }
  } catch (error) { if (gen === detailEpoch) $('detail-content').insertAdjacentHTML('beforeend', `<p class="error">${esc(error.message)}</p>`); }
}
let testFile = null;
async function detect() {
  if (!testFile) { notice('请先选择或粘贴一张图片。', true); return; }
  if (testFile.size > 15 * 1024 ** 2) { notice('图片超过 15 MiB。', true); return; }
  const gen = epoch, button = document.querySelector('[data-action="detect"]'); button.disabled = true; button.textContent = '正在框选…'; notice('');
  const requestId = id();
  try {
    const encoded = await new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.onerror = () => reject(new Error('图片读取失败')); reader.readAsDataURL(testFile); });
    const result = await request('api/admin/try', { image: encoded, request_id: requestId });
    if (gen !== epoch || !active) return;
    clearImage(); imageURL = URL.createObjectURL(testFile);
    $('test-result').innerHTML = `<div class="actions"><span class="badge">${esc(result.strips)} 条带 · ${esc(result.elapsed_ms)} ms</span><span class="badge">${esc(result.model.name)}</span></div>${preview(imageURL, result)}<p class="card-sub">本次已保存到请求历史，未加入训练集。</p>`;
  } catch (error) { if (gen === epoch) notice(error.message, true); }
  finally { if (button.isConnected) { button.disabled = false; button.textContent = '开始框选'; } }
}
async function click(event) {
  const button = event.target.closest('button'); if (!button || button.disabled) return;
  try {
    if (button.dataset.page) { clearImage(); testFile = null; page = button.dataset.page; await render(); return; }
    if (button.dataset.detail) { await detail(button.dataset.detail); return; }
    if (button.dataset.zoom) { $(button.dataset.zoom).querySelector('.preview-inner').classList.toggle('zoom'); return; }
    if (button.dataset.boxes) { $(button.dataset.boxes).querySelector('svg').toggleAttribute('hidden'); return; }
    if (button.dataset.revoke) { if (confirm('吊销这个 Key？对应客户端将立即无法继续调用。')) { button.disabled = true; await request('api/admin/keys/revoke', { id: button.dataset.revoke }); await render(); } return; }
    if (button.dataset.model) {
      if (!confirm('确认切换在线模型？操作会影响所有使用此服务的客户端；失败将保留原模型。')) return;
      button.disabled = true;
      const data = await request('api/admin/models/apply', { action: button.dataset.model === 'previous' ? 'rollback' : 'activate', model_id: button.dataset.model, revision: modelRevision, request_id: id() });
      await render(); notice(data.operation.state === 'done' ? '在线模型已更新。' : data.operation.error || '模型操作结果待核对', data.operation.state !== 'done'); return;
    }
    switch (button.dataset.action) {
      case 'login': $('login-dialog').showModal(); break;
      case 'refresh': await render(); break;
      case 'logout': await request('api/admin/logout', {}); locked(); break;
      case 'new-key': closeKey(); $('key-dialog').showModal(); break;
      case 'close-key': closeKey(); break;
      case 'close-detail': closeDetail(); break;
      case 'copy-key': try { await navigator.clipboard.writeText($('created-key').value); $('key-error').textContent = '已复制'; } catch { $('created-key').select(); $('key-error').textContent = '请选中复制 Key。'; } break;
      case 'detect': await detect(); break;
      case 'prev': filter.page--; await render(); break;
      case 'next': filter.page++; await render(); break;
      case 'pause': await request('api/admin/settings', { paused: !currentStatus.paused }); await render(); break;
    }
  } catch (error) { notice(error.message, true); button.disabled = false; }
}
document.addEventListener('click', click);
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); const button = event.submitter; button.disabled = true;
  try { const data = await request('api/admin/login', { password: $('password').value }, { unauthenticated: true }); csrf = data.csrf_token; $('password').value = ''; $('login-error').textContent = ''; $('login-dialog').close(); $('logout').hidden = false; await render(); }
  catch (error) { $('login-error').textContent = error.message; }
  finally { button.disabled = false; }
});
$('key-form').addEventListener('submit', async event => {
  event.preventDefault(); const gen = ++keyEpoch, button = event.submitter; button.disabled = true;
  try {
    const data = await request('api/admin/keys', { name: $('key-name').value });
    if (gen !== keyEpoch || !$('key-dialog').open || !csrf) {
      if (csrf && active) { await render(); notice('Key 已创建，但明文窗口已关闭。请吊销该 Key 后重新创建。', true); }
      return;
    }
    $('created-key').value = data.key; $('key-secret').hidden = false; $('key-form').hidden = true; await render();
  }
  catch (error) { if (gen === keyEpoch) $('key-error').textContent = error.message; }
  finally { button.disabled = false; }
});
document.addEventListener('submit', async event => {
  if (event.target.id !== 'settings-form') return; event.preventDefault(); const button = event.submitter; button.disabled = true;
  try { await request('api/admin/settings', { allow_external: $('allow-external').checked, paused: $('paused').checked, per_key_per_minute: Number($('rate').value), history_retention: { days: Number($('days').value), limit: Number($('limit').value), detail_bytes: Number($('capacity').value) * 1024 ** 2 } }); await render(); notice('服务设置已保存。'); }
  catch (error) { notice(error.message, true); } finally { button.disabled = false; }
});
document.addEventListener('change', event => {
  if (event.target.id === 'test-file') testFile = event.target.files[0] || null;
  if (event.target.dataset.filter) { filter[event.target.dataset.filter] = event.target.value; filter.page = 1; render(); }
});
document.addEventListener('paste', event => { if (page !== 'test' || !csrf) return; const file = [...(event.clipboardData?.files || [])][0]; if (file) { testFile = file; notice('图片已粘贴，可以开始框选。'); } });
document.addEventListener('dragover', event => { if (event.target.closest('#drop-area')) event.preventDefault(); });
document.addEventListener('drop', event => { if (event.target.closest('#drop-area')) { event.preventDefault(); testFile = event.dataTransfer.files[0]; notice(testFile ? '图片已放入，可以开始框选。' : '请放入图片文件。'); } });
$('key-dialog').addEventListener('cancel', event => { event.preventDefault(); closeKey(); }); $('detail-dialog').addEventListener('cancel', event => { event.preventDefault(); closeDetail(); });
window.addEventListener('pagehide', () => { active = false; pending.forEach(c => c.abort()); locked(); $('password').value = ''; });
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });
try { const data = await request('api/admin/session', undefined, { unauthenticated: true }); csrf = data.csrf_token; $('logout').hidden = false; await render(); }
catch { $('login-dialog').showModal(); }
