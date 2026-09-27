/* ── 收件箱录入流程（v1.12.0）：上传 → 处理 → 录入 + AI 训练 ──
   依赖 core.js 的 api / escapeHtml，questions.js 的 renderMdContent；
   所有类名以 ib- 为前缀，避免和既有样式冲突。
   区域坐标一律归一化 0–1；像素工作（裁图 / 切片）在浏览器 canvas 里做，后端零依赖。 */

const IB = {
  items: [], cur: null, sel: new Set(), csel: new Set(), stage: 'upload',
  drawRole: 'question', selR: null, last: null, disp: { w: 0, h: 0 }, bound: false,
  imgs: {}, saveTimers: new Map(), savePatches: new Map(), saveItems: new Map(), saveChains: new Map(), revisions: new Map(), polls: {}, drawCard: 1,
  dragging: false,
};
const IB_STATUS = { pending: '待处理', boxed: '已框选', ready: '待创建', done: '已录入', discarded: '已丢弃' };
const IB_ROLE = { question: '题目', answer: '答案', ignore: '忽略' };
const $ib = id => document.getElementById(id);

/* ── 入口 / 阶段 ── */
function inboxInit() {
  if (!IB.bound) { ibBind(); IB.bound = true; }
  ibGo(IB.stage);
  ibLoad();
}
async function ibLoad() {
  try {
    const res = await api('/api/inbox/items');
    IB.items = res.items || [];
  } catch (e) { ibToast('读取收件箱失败：' + e.message, 'warn'); IB.items = []; }
  ibRenderAll();
}
function ibRenderAll() {
  ibCounts(); ibRenderInbox();
  if (IB.stage === 'process') ibRenderProcess();
  if (IB.stage === 'create') ibRenderCards();
}
function ibGo(stage) {
  if (IB.stage === 'process' && stage !== 'process') ibFlushSaves();
  IB.stage = stage;
  document.querySelectorAll('#panel-create .ib-flow-step').forEach(f => {
    const active = f.dataset.stage === stage;
    f.classList.toggle('on', active);
    f.setAttribute('aria-current', active ? 'step' : 'false');
  });
  document.querySelectorAll('#panel-create .ib-stage').forEach(s => s.classList.toggle('on', s.id === 'ib-stage-' + stage));
  if (stage === 'process') { if (!IB.cur || !ibCur()) IB.cur = (ibQueue()[0] || {}).id || null; ibRenderProcess(); }
  if (stage === 'create') ibRenderCards();
  if (stage === 'train') { ibLoadStats(); ibLoadPolicy(); }
  ibBatchbar();
}
function ibItem(id) { return IB.items.find(i => i.id === id); }
function ibCur() { return ibItem(IB.cur); }
function ibLive() { return IB.items.filter(i => i.status !== 'discarded'); }
function ibQueue() { return ibLive().filter(i => i.status !== 'done'); }
function ibCounts() {
  const c = s => ibLive().filter(i => i.status === s).length;
  const set = (id, v) => { const el = $ib(id); if (el) el.textContent = v; };
  set('ib-c-pending', c('pending')); set('ib-c-boxed', c('boxed')); set('ib-c-ready', c('ready'));
}
// 收件箱提示：v1.20.0 起转调全站唯一的 uiToast（assets/app/ui/toast.js）；带操作按钮的多留一会儿。
function ibToast(msg, kind, action) {
  const actions = action && action.label && typeof action.onClick === 'function' ? [{ label: action.label, onClick: action.onClick }] : [];
  uiToast(msg, { kind: kind === 'warn' ? 'warn' : 'ok', actions, duration: actions.length ? 8000 : 3200 });
}
function ibBytes(n) { return n > 1048576 ? (n / 1048576).toFixed(1) + ' MB' : Math.round(n / 1024) + ' KB'; }
function ibRawUrl(item) { return `/api/inbox/raw?id=${encodeURIComponent(item.id)}`; }
function ibImg(item) {
  if (!IB.imgs[item.id]) { const im = new Image(); im.src = ibRawUrl(item); IB.imgs[item.id] = im; }
  return IB.imgs[item.id];
}
function ibLoadImg(item) {
  const im = ibImg(item);
  if (im.complete && im.naturalWidth) return Promise.resolve(im);
  return new Promise((ok, fail) => { im.addEventListener('load', () => ok(im), { once: true }); im.addEventListener('error', () => fail(new Error('原图加载失败')), { once: true }); });
}
/* 浏览器裁图：返回 data URL。type 默认 PNG；切片条带用 JPEG 减小体积 */
const IB_JPEG_PX = 1500000; // 超过约 150 万像素的裁图（整张长截图的答案区）改用 JPEG，避免几 MB 的 base64
async function ibCrop(item, r, type = 'image/png', quality = 0.92) {
  const im = await ibLoadImg(item);
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(r.w * im.naturalWidth)); c.height = Math.max(1, Math.round(r.h * im.naturalHeight));
  const ctx = c.getContext('2d');
  if (type === 'image/png' && c.width * c.height > IB_JPEG_PX) { type = 'image/jpeg'; quality = 0.9; ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, c.width, c.height); }
  ctx.drawImage(im, r.x * im.naturalWidth, r.y * im.naturalHeight, c.width, c.height, 0, 0, c.width, c.height);
  return c.toDataURL(type, quality);
}

/* 上传由 features/create/upload.js 负责，旧列表收到 inbox:reload 后同步。 */

/* ── 阶段 ①：收件箱网格已迁到 features/create/grid.js。旧控制器只发布更新。 ── */
function ibRenderInbox() { window.__omrs?.emit('inbox:grid'); }
function ibBatchbar() { window.__omrs?.emit('inbox:grid'); }

/* ── 阶段 ②：队列 / 画布 / 区域面板 ── */
function ibRenderProcess() { window.__omrs?.emit('inbox:process'); }
function ibRenderQueue() { window.__omrs?.emit('inbox:process'); }
function ibOpen(id) { IB.cur = id; IB.selR = null; IB.drawCard = 1; const it = ibCur(); if (it) $ib('ib-layout').value = it.layout || 'zuoyebang'; ibRenderProcess(); }
function ibStep(d) { const q = ibQueue(); if (!q.length) return; let idx = q.findIndex(i => i.id === IB.cur); idx = (idx + d + q.length) % q.length; ibOpen(q[idx].id); }
function ibRenderStage() { window.__omrs?.emit('inbox:process'); }
function ibLayoutStage() { window.__omrs?.emit('inbox:process'); }
function ibRenderBoxes() { window.__omrs?.emit('inbox:process'); }
function ibGroupCards(it) { const g = {}; (it.regions || []).forEach(r => { (g[r.card] = g[r.card] || []).push(r); }); return g; }
function ibSetDrawRole(role) {
  IB.drawRole = role;
  document.querySelectorAll('#ib-role-seg button').forEach(b => b.classList.toggle('on', b.dataset.v === role));
  const it = ibCur(); const r = it && (it.regions || []).find(x => x.id === IB.selR);
  if (r && r.role !== role) { r.role = role; r.judge = null; ibAfterEdit(); }
}
function ibNewRegion(card, role, x, y, w, h, extra = {}) {
  return { id: 'r_' + Math.random().toString(36).slice(2, 10), card, role, x, y, w, h, origin: 'manual', conf: null, ai_box: null, convert: 'auto', text: null, text_status: 'none', judge: null, judge_overridden: false, ...extra };
}
function ibFmtBox(r) { return `[${r.x.toFixed(3)}, ${r.y.toFixed(3)}, ${r.w.toFixed(3)}, ${r.h.toFixed(3)}]`; }
function ibIou(a, b) { if (!b) return 0; const x1 = Math.max(a.x, b.x), y1 = Math.max(a.y, b.y), x2 = Math.min(a.x + a.w, b.x + b.w), y2 = Math.min(a.y + a.h, b.y + b.h); const inter = Math.max(0, x2 - x1) * Math.max(0, y2 - y1); return inter / (a.w * a.h + b.w * b.h - inter); }
/* 本地改动 → 重绘 → 去抖保存到后端 */
function ibAfterEdit(save = true) {
  const it = ibCur(); if (!it) return;
  if (it.regions.length && it.status === 'pending') it.status = 'boxed';
  if (!it.regions.length && it.status === 'boxed') it.status = 'pending';
  ibRenderBoxes(); ibRenderSide(); ibRenderQueue(); ibRenderInbox();
  if (save) ibSaveSoon(it);
}
function ibMergePatch(a, b) { return { ...a, ...b, cards: { ...(a.cards || {}), ...(b.cards || {}) } }; }
function ibSaveSoon(it, patch = {}, delay = 500) {
  if (!it) return;
  const id = it.id;
  IB.revisions.set(id, (IB.revisions.get(id) || 0) + 1);
  IB.savePatches.set(id, ibMergePatch(IB.savePatches.get(id) || {}, patch));
  IB.saveItems.set(id, it);
  clearTimeout(IB.saveTimers.get(id));
  IB.saveTimers.set(id, setTimeout(() => ibSave(it), delay));
}
function ibFlushSaves() {
  return Promise.all([...IB.savePatches.keys()].map(id => ibSave(IB.saveItems.get(id))));
}
function ibSave(it, patch = {}) {
  if (!it) return Promise.resolve(null);
  const id = it.id;
  clearTimeout(IB.saveTimers.get(id)); IB.saveTimers.delete(id);
  const merged = ibMergePatch(IB.savePatches.get(id) || {}, patch);
  const local = IB.saveItems.get(id) || it;
  IB.savePatches.delete(id); IB.saveItems.delete(id);
  const revision = (IB.revisions.get(id) || 0) + 1;
  IB.revisions.set(id, revision);
  const previous = IB.saveChains.get(id) || Promise.resolve();
  const pending = previous.catch(() => null).then(async () => {
    try {
      const res = await api('/api/inbox/item/update', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id, regions: local.regions, layout: local.layout, ...merged }) });
      const idx = IB.items.findIndex(item => item.id === id);
      if (idx >= 0 && IB.revisions.get(id) === revision) IB.items[idx] = res.item;
      ibCounts(); return res.item;
    } catch (e) { ibToast('保存失败：' + e.message, 'warn'); return null; }
  });
  IB.saveChains.set(id, pending);
  pending.finally(() => { if (IB.saveChains.get(id) === pending) IB.saveChains.delete(id); });
  return pending;
}
function ibSetLayout(v) { const it = ibCur(); if (it) { it.layout = v; ibSaveSoon(it); } }
function ibSelectRegion(id) { IB.selR = id; const r = (ibCur()?.regions || []).find(x => x.id === id); if (r && r.role !== 'ignore') { IB.drawRole = r.role; document.querySelectorAll('#ib-role-seg button').forEach(b => b.classList.toggle('on', b.dataset.v === r.role)); } ibRenderBoxes(); ibRenderSide(); }
function ibDeleteRegion(id) { const it = ibCur(); it.regions = it.regions.filter(x => x.id !== id); if (IB.selR === id) IB.selR = null; ibAfterEdit(); }
function ibClearBoxes() { const it = ibCur(); if (!it) return; it.regions = []; IB.selR = null; ibAfterEdit(); }
function ibWholeImage() { const it = ibCur(); if (!it) return; it.regions = [ibNewRegion(1, 'question', 0, 0, 1, 1)]; it.layout = 'plain'; $ib('ib-layout').value = 'plain'; IB.selR = it.regions[0].id; ibAfterEdit(); ibToast('整张图作为题目区域；「转换文本」会判断是否需要留图'); }
function ibAddCard() { const it = ibCur(); if (!it) return; IB.drawCard = Object.keys(ibGroupCards(it)).length + 1; ibToast(`题卡 ${IB.drawCard}：接下来画的框归入它`); }
function ibSetConvert(id, v) {
  const it = ibCur(); const r = it.regions.find(x => x.id === id); const prev = r.convert;
  r.convert = v;
  if (r.judge && ((v === 'text' && !r.judge.ok) || (v === 'image' && r.judge.ok))) r.judge_overridden = true;
  if (v !== prev) ibAfterEdit();
}
function ibEditText(id, v) { const r = ibCur().regions.find(x => x.id === id); r.text = v; r.text_status = v.trim() ? 'done' : 'none'; const p = $ib('ib-prev-' + id); if (p) p.innerHTML = ibMd(v); ibSaveSoon(ibCur()); }
function ibMd(t) { return typeof renderMdContent === 'function' ? renderMdContent(t) : escapeHtml(t).replace(/\n/g, '<br>'); }
/* 沿用上一张框位：横向照搬；纵向对顶部锚定的框按像素偏移，其余按比例 */
function ibApplyLast() {
  const it = ibCur(); if (!it) return; const last = IB.last;
  if (!last || last.id === it.id) { ibToast('还没有处理过的上一张', 'warn'); return; }
  it.regions = ibTransferBoxes(last, it); IB.selR = null; ibAfterEdit();
  ibToast(`已沿用 ${last.file} 的 ${it.regions.length} 个框，调一下位置即可`);
}
function ibTransferBoxes(from, to) {
  return (from.regions || []).map(r => {
    const topPx = r.y * from.height, hPx = r.h * from.height;
    const anchoredTop = r.y < 0.35; // 靠上的框（题目）按像素锚定；下方的框（答案）按比例
    const y = anchoredTop ? Math.min(0.95, topPx / to.height) : r.y;
    const h = anchoredTop ? Math.min(1 - y, hPx / to.height) : Math.min(1 - y, r.h);
    return ibNewRegion(r.card, r.role, r.x, y, r.w, h, { convert: r.convert === 'auto' ? 'auto' : r.convert });
  });
}
async function ibApplyLastSelected() {
  const last = IB.last; if (!last) { ibToast('还没有处理过的上一张', 'warn'); return; }
  let n = 0;
  for (const id of IB.sel) { const it = ibItem(id); if (!it || it.status === 'done' || it.id === last.id) continue; it.regions = ibTransferBoxes(last, it); await ibSave(it); n++; }
  ibToast(`已给 ${n} 张沿用 ${last.file} 的框位`); ibRenderAll();
}
async function ibWholeSelected() {
  let n = 0;
  for (const id of IB.sel) { const it = ibItem(id); if (!it || it.status === 'done') continue; it.regions = [ibNewRegion(1, 'question', 0, 0, 1, 1)]; it.layout = 'plain'; await ibSave(it); n++; }
  ibToast(`已把 ${n} 张整图标为题目区域`); ibRenderAll();
}
async function ibDiscardCurrent() {
  const it = ibCur(); if (!it) return;
  if (!await uiConfirm('丢弃这张图？')) return;
  try { await api('/api/inbox/discard', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: it.id }) }); IB.sel.delete(it.id); await ibLoad(); IB.cur = (ibQueue()[0] || {}).id || null; ibRenderProcess(); }
  catch (e) { ibToast(e.message, 'warn'); }
}

/* 右栏由 features/create/process-content.js 渲染；旧提取流程只发布更新。 */
function ibRenderSide() { window.__omrs?.emit('inbox:process'); }
async function ibPaintCropCanvases() {
  const it = ibCur(); if (!it) return;
  for (const cv of document.querySelectorAll('[data-ib-cropcv]')) {
    const r = it.regions.find(x => x.id === cv.dataset.ibCropcv); if (!r) continue;
    try { const im = await ibLoadImg(it); const sw = r.w * im.naturalWidth, sh = r.h * im.naturalHeight; const scale = Math.min(1, 340 / sw); cv.width = Math.max(1, sw * scale); cv.height = Math.max(1, sh * scale); cv.getContext('2d').drawImage(im, r.x * im.naturalWidth, r.y * im.naturalHeight, sw, sh, 0, 0, cv.width, cv.height); } catch (e) { /* 忽略 */ }
  }
}

/* ── AI 任务：detect / extract / classify（后台 job + 轮询）── */
async function ibJob(type, payload, onDone) {
  const res = await api('/api/inbox/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type, ...payload }) });
  const id = res.job.id;
  IB.polls[id] = setInterval(async () => {
    try {
      const j = (await api(`/api/inbox/job?id=${encodeURIComponent(id)}`)).job;
      if (j.done || j.status === 'done' || j.status === 'error') {
        clearInterval(IB.polls[id]); delete IB.polls[id];
        if ((j.errors || []).length) ibToast(`${type} 有 ${j.errors.length} 个失败：${j.errors[0].msg}`, 'warn');
        if (onDone) await onDone(j);
      }
    } catch (e) { clearInterval(IB.polls[id]); delete IB.polls[id]; ibToast('读取任务进度或同步结果失败：' + e.message, 'warn'); }
  }, 1200);
  return id;
}
async function ibStrips(it) {
  const plan = (await api(`/api/inbox/slice-plan?width=${it.width}&height=${it.height}`)).strips;
  const out = [];
  for (const s of plan) out.push({ y0: s.y0, y1: s.y1, data: await ibCrop(it, { x: 0, y: s.y0, w: 1, h: s.y1 - s.y0 }, 'image/jpeg', 0.85) });
  return out;
}
/* provider：不传 → 服务端按设置里的 inbox_detect_provider（vlm / template / local_http）；'template' 零联网，不需要切片 */
async function ibDetect(ids, provider) {
  const items = [];
  for (const id of ids) {
    const it = ibItem(id); if (!it || it.status === 'done') continue;
    try {
      const unit = { item_id: id, replace: !it.regions.length };
      if (provider) unit.provider = provider;
      if (provider !== 'template') unit.strips = await ibStrips(it);
      items.push(unit);
    } catch (e) { ibToast(e.message, 'warn'); }
  }
  if (!items.length) return;
  ibToast(provider === 'template' ? `按版式模板给 ${items.length} 张打初始框…` : `已提交 ${items.length} 张给 AI 框选（长图已切成条带），完成后自动回填`);
  try {
    await ibJob('detect', { items }, async j => {
      await ibLoad(); if (IB.stage === 'process') ibRenderProcess();
      const res = j.result || []; const n = res.reduce((s, r) => s + (r.boxes || 0), 0);
      const blind = res.filter(r => r.blind).length, ready = res.filter(r => r.auto && r.auto.ready).length;
      let msg = `框选完成：${items.length} 张，共 ${n} 框，请逐张确认`;
      if (blind) msg += `；其中 ${blind} 张为盲标（不展示 AI 框，请直接手画）`;
      if (ready) msg += `；${ready} 张已按自动策略转文本并就绪`;
      if (j.errors && j.errors.length) msg += `；${j.errors.length} 张失败：${j.errors[0].msg}`;
      ibToast(msg, j.errors && j.errors.length ? 'warn' : undefined);
    });
  } catch (e) { ibToast('AI 框选失败：' + e.message, 'warn'); }
}
function ibDetectCurrent(provider) { if (IB.cur) ibDetect([IB.cur], provider); }
function ibDetectSelected(provider) { const ids = [...IB.sel]; if (!ids.length) { ibToast('先勾选要框选的图', 'warn'); return; } ibDetect(ids, provider); }
async function ibExtractRegions(it, regionIds) {
  const regions = [];
  for (const rid of regionIds) {
    const r = it.regions.find(x => x.id === rid); if (!r || r.role === 'ignore' || r.convert === 'image') continue;
    r.text_status = 'running'; regions.push({ region_id: rid, crop: await ibCrop(it, r) });
  }
  if (!regions.length) { ibToast('没有需要提取的区域（都已提取或选择保留图片）', 'warn'); return; }
  await ibSave(it); ibRenderSide();
  try {
    await ibJob('extract', { regions }, async () => {
      // 只同步本次提取的区域；整页 ibLoad 会替换另一张图正在拖动的框对象。
      const fresh = (await api(`/api/inbox/item?id=${encodeURIComponent(it.id)}`)).item;
      const idx = IB.items.findIndex(item => item.id === it.id);
      if (idx >= 0 && fresh) {
        if (IB.cur === it.id) {
          const local = IB.items[idx];
          const extracted = new Set(regions.map(r => r.region_id));
          for (const result of fresh.regions || []) {
            const target = local.regions.find(r => r.id === result.id);
            if (target && extracted.has(result.id) && target.text_status === 'running') {
              for (const key of ['convert', 'text', 'text_status', 'judge', 'judge_overridden']) target[key] = result[key];
            }
          }
          local.status = fresh.status;
          if (IB.stage === 'process' && !IB.dragging) ibRenderSide();
        } else IB.items[idx] = fresh;
      }
      ibCounts(); ibRenderQueue(); ibRenderInbox();
      ibToast('文本提取完成，请核对预览；确认后原图不再嵌入题目');
    });
  } catch (e) { it.regions.forEach(r => { if (r.text_status === 'running') r.text_status = 'none'; }); ibRenderSide(); ibToast('提取失败：' + e.message, 'warn'); }
}
function ibExtractAll() { const it = ibCur(); if (!it) return; ibExtractRegions(it, it.regions.filter(r => r.role !== 'ignore' && r.convert !== 'image' && r.text_status !== 'done').map(r => r.id)); }
async function ibMarkReady() {
  const it = ibCur(); if (!it) return;
  if (it.regions.some(r => r.text_status === 'running')) { ibToast('还有区域在提取中', 'warn'); return; }
  const saved = await ibSave(it, { status: 'ready' });
  if (!saved) return;
  IB.last = saved; it.regions.forEach(r => { if (r.origin === 'ai') r.origin = 'ai'; });
  const nxt = ibQueue().find(i => i.status !== 'ready' && i.id !== it.id);
  ibToast(`${it.file} 已就绪，进入「录入」；${nxt ? '已切到下一张' : '队列里没有待处理的图了'}`);
  if (nxt) ibOpen(nxt.id); else ibRenderProcess();
}

/* ── 阶段 ③：题卡录入 ── */
function ibReadyCards() {
  const out = [];
  ibLive().filter(i => i.status === 'ready').forEach(it => { const g = ibGroupCards(it); Object.keys(g).map(Number).sort((a, b) => a - b).forEach(c => { if (!(it.cards || {})[String(c)]) it.cards[String(c)] = { subject: '', category: '', difficulty: 5, tags: [], labels: [], cause: '', page: '', classified: false }; const form = it.cards[String(c)]; if (!Array.isArray(form.labels)) form.labels = []; if (!form.created_uid) out.push({ it, c, regions: g[c], form }); }); });
  return out;
}
function ibCardKey(it, c) { return it.id + '#' + c; }
function ibRenderCards() {
  const wrap = $ib('ib-cards'); if (!wrap) return;
  const cards = ibReadyCards();
  $ib('ib-cr-count').textContent = `${cards.length} 张题卡待创建 · 来自 ${new Set(cards.map(x => x.it.id)).size} 张图`;
  $ib('ib-cr-all').checked = cards.length > 0 && cards.every(x => IB.csel.has(ibCardKey(x.it, x.c)));
  wrap.innerHTML = cards.map(({ it, c, regions, form }, idx) => {
    const k = ibCardKey(it, c); const q = regions.filter(r => r.role === 'question'), a = regions.filter(r => r.role === 'answer');
    const block = rs => rs.map(r => r.convert === 'text' && r.text ? `<div class="q-md">${ibMd(r.text)}</div>` : `<canvas data-ib-cardcv="${it.id}|${r.id}"></canvas>`).join('<div style="height:8px"></div>');
    const kinds = rs => rs.map(r => r.convert === 'text' ? '文本' : '图片').join(' + ');
    const ai = form.classified ? '<span class="ai">AI 已填 · 可改</span>' : '';
    const tags = Array.isArray(form.tags) ? form.tags.join(', ') : (form.tags || '');
    const allText = regions.every(r => r.role === 'ignore' || r.convert === 'text');
    return `<div class="ib-qcard" id="ib-card-${it.id}-${c}" data-ib-card="${k}"><div class="ib-qcard-head"><input type="checkbox" class="ib-chk" data-ib-csel="${k}" ${IB.csel.has(k) ? 'checked' : ''}><span class="t">题卡 ${idx + 1}</span><span class="src">${escapeHtml(it.file)}${Object.keys(ibGroupCards(it)).length > 1 ? ` · 题卡 ${c}` : ''}</span><span class="grow"></span><span class="tag ib-muted">题目 ${kinds(q)}</span>${a.length ? `<span class="tag ib-muted">答案 ${kinds(a)}</span>` : '<span class="tag ib-muted">无答案</span>'}</div>
    <div class="ib-qcard-body"><div class="ib-qcard-prev">
      <div class="ib-pv"><div class="ib-pv-l"><span class="ib-role question">题目</span>写入 <code># 题目</code></div><div class="ib-pv-b question">${block(q)}</div></div>
      ${a.length ? `<div class="ib-pv"><div class="ib-pv-l"><span class="ib-role answer">答案</span>写入 <code># 答案</code></div><div class="ib-pv-b answer">${block(a)}</div></div>` : ''}
      <div class="hint">${allText ? `原图 ${it.width}×${it.height} 不随题保存（已全部转文本），只留在收件箱数据集里。` : `保留图片的区域会裁出存入 <code>附件/</code>；原图只留在收件箱数据集里。`}</div>
    </div><div class="ib-qcard-form">
      <div class="ib-row2"><div class="ib-fg"><label>科目 *${ai}</label><input class="input" value="${escapeHtml(form.subject)}" data-ib-f="${k}|subject" list="cr-subj-list"></div><div class="ib-fg"><label>分类 *${ai}</label><input class="input" value="${escapeHtml(form.category)}" data-ib-f="${k}|category" list="cr-cat-list"></div></div>
      <div class="ib-fg"><label>难度${ai}</label><div class="ib-range"><input type="range" min="1" max="10" value="${form.difficulty || 5}" data-ib-f="${k}|difficulty"><b>${form.difficulty || 5}</b></div></div>
      <div class="ib-fg"><label>相关知识点${ai}</label><input class="input" value="${escapeHtml(tags)}" data-ib-f="${k}|tags" list="cr-ktag-list" placeholder="逗号分隔，写入 YAML 为 [[双链]]"></div>
      <div class="ib-fg"><label>标记${ai}</label><div class="ib-labels" data-ib-labels="${escapeAttr(k)}">${lblChips(form.labels || [], { lg: true })}<button type="button" class="lbl-form-add" data-ib-label-open="${escapeAttr(k)}">＋ 添加标记</button></div></div>
      <div class="ib-fg ib-cause"><label>⚑ 错因 · 这道题为什么错？</label><textarea class="input" rows="2" data-ib-f="${k}|cause" placeholder="写入 # 备注 的「## 错因」，复习时先看这里">${escapeHtml(form.cause)}</textarea></div>
      <div class="ib-fg" style="margin-bottom:0"><label>笔记本页码</label><input class="input" style="max-width:140px" value="${escapeHtml(form.page)}" data-ib-f="${k}|page" placeholder="p.23"></div>
    </div></div>
    <div class="ib-qcard-foot"><span class="file">→ 错题/${escapeHtml(form.subject || '科目')}/${escapeHtml(form.category || '分类')}/${escapeHtml(form.category || '分类')}N.md</span><span class="grow"></span><button class="btn sm" data-ib-classify="${k}">🤖 ${form.classified ? '重新识别题目信息' : 'AI 识别题目信息'}</button><button class="btn sm" data-ib-back="${it.id}">退回处理</button><button class="btn sm primary" data-ib-commit="${k}">创建题目</button></div></div>`;
  }).join('') || '<div class="ib-empty">还没有就绪的题卡。<br>去「处理」把框选好的图标记就绪。</div>';
  ibPaintCardCanvases();
}
async function ibPaintCardCanvases() {
  for (const cv of document.querySelectorAll('[data-ib-cardcv]')) {
    const [id, rid] = cv.dataset.ibCardcv.split('|'); const it = ibItem(id); const r = it && it.regions.find(x => x.id === rid); if (!r) continue;
    try { const im = await ibLoadImg(it); const sw = r.w * im.naturalWidth, sh = r.h * im.naturalHeight; const scale = Math.min(1, 520 / sw); cv.width = Math.max(1, sw * scale); cv.height = Math.max(1, sh * scale); cv.getContext('2d').drawImage(im, r.x * im.naturalWidth, r.y * im.naturalHeight, sw, sh, 0, 0, cv.width, cv.height); } catch (e) { /* 忽略 */ }
  }
}
function ibCardForm(k) { const [id, c] = k.split('#'); const it = ibItem(id); return { it, c: Number(c), form: it.cards[c] }; }
function ibCardLabels(k) { return ibCardForm(k).form?.labels || []; }
function ibSetCardLabels(k, values) {
  const { it, c, form } = ibCardForm(k);
  if (!it || !form) return;
  form.labels = [...new Set((values || []).map(value => String(value || '').trim()).filter(Boolean))];
  const box = [...document.querySelectorAll('[data-ib-labels]')].find(node => node.dataset.ibLabels === k);
  if (box) box.innerHTML = `${lblChips(form.labels, { lg: true })}<button type="button" class="lbl-form-add" data-ib-label-open="${escapeAttr(k)}">＋ 添加标记</button>`;
  ibSaveSoon(it, { cards: { [c]: form } }, 600);
}
function ibOpenCardLabels(k, anchor) {
  openLabelPicker(`__ib_card__${k}`, anchor, {
    get: () => ibCardLabels(k),
    onSave: values => ibSetCardLabels(k, values),
  });
}
function ibCardField(k, f, v) {
  const { it, c, form } = ibCardForm(k);
  form[f] = f === 'difficulty' ? Number(v) : f === 'tags' ? v.split(/[,，]/).map(s => s.trim()).filter(Boolean) : f === 'labels' ? v.split(/[,，]/).map(s => s.trim()).filter(Boolean) : v;
  if (f === 'subject' || f === 'category') { const foot = document.querySelector(`#ib-card-${it.id}-${c} .file`); if (foot) foot.textContent = `→ 错题/${form.subject || '科目'}/${form.category || '分类'}/${form.category || '分类'}N.md`; }
  ibSaveSoon(it, { cards: { [c]: form } }, 600);
}
function ibSelectAllCards(on) { ibReadyCards().forEach(x => on ? IB.csel.add(ibCardKey(x.it, x.c)) : IB.csel.delete(ibCardKey(x.it, x.c))); ibRenderCards(); }
async function ibClassify(keys) {
  const cards = [];
  for (const k of keys) { const { it, c } = ibCardForm(k); const q = it.regions.find(r => r.card === c && r.role === 'question'); if (!q) continue; cards.push({ item_id: it.id, card: c, crop: await ibCrop(it, q) }); }
  if (!cards.length) { ibToast('没有可识别的题卡', 'warn'); return; }
  ibToast(`AI 识别 ${cards.length} 张题卡的科目 / 分类 / 难度 / 知识点…`);
  try { await ibJob('classify', { cards }, async () => { await ibLoad(); ibRenderCards(); ibToast('已填科目 / 分类 / 难度 / 知识点（只填空缺项，不覆盖已填）'); }); }
  catch (e) { ibToast('识别失败：' + e.message, 'warn'); }
}
function ibClassifySelected() { const ks = [...IB.csel]; if (!ks.length) { ibToast('先勾选要识别的题卡', 'warn'); return; } ibClassify(ks); }
// 提示条上的「加入展示板」：一张或一批都走 boardQuickAdd（加入最近用过的板，没有板就先新建）
function ibBoardAction(uids) {
  const clean = (uids || []).filter(Boolean);
  if (!clean.length || typeof boardQuickAdd !== 'function') return null;
  return { label: clean.length > 1 ? `加入展示板（${clean.length} 题）` : '加入展示板', onClick: () => boardQuickAdd(clean) };
}
async function ibCommit(k, options = {}) {
  const { it, c, form } = ibCardForm(k);
  if (!form.subject || !form.category) { ibToast(`${options.quiet ? `题卡 ${k.split('#')[1] || ''}：` : ''}科目和分类是必填项`, 'warn'); return null; }
  const crops = {};
  for (const r of it.regions.filter(r => r.card === c && r.role !== 'ignore' && r.convert === 'image')) crops[r.id] = await ibCrop(it, r);
  try {
    const res = await api('/api/inbox/commit', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: it.id, card: c, form, crops }) });
    IB.csel.delete(k);
    if (!options.quiet) ibToast(`已创建 ${res.uid}（${res.file_path}）；原图与框位已存入数据集`, undefined, ibBoardAction([res.uid]));
    await ibLoad(); ibRenderCards();
    if (!options.quiet && typeof reloadData === 'function') reloadData();
    return res;
  } catch (e) { ibToast('创建失败：' + e.message, 'warn'); return null; }
}
// 批量创建：逐张提交，最后只弹一条提示，「加入展示板」一次把这批新题全部加进去
// （以前每张各弹一条互相覆盖，只有最后一题能加板）
async function ibCommitSelected() {
  const ks = [...IB.csel];
  if (!ks.length) { ibToast('先勾选要创建的题卡', 'warn'); return; }
  const created = [];
  let failed = 0;
  for (const k of ks) { const res = await ibCommit(k, { quiet: true }); if (res?.uid) created.push(res.uid); else failed += 1; }
  if (created.length) ibToast(`已创建 ${created.length} 道题目${failed ? `，${failed} 张失败` : ''}；原图与框位已存入数据集`, failed ? 'warn' : undefined, ibBoardAction(created));
  if (created.length && typeof reloadData === 'function') reloadData();
}
async function ibBackToProcess(id) { const it = ibItem(id); if (!it) return; it.status = 'boxed'; await ibSave(it, { status: 'boxed' }); IB.cur = id; ibGo('process'); }

/* ── AI 训练：数据集统计 ── */
async function ibLoadStats() {
  const box = $ib('ib-train'); if (!box) return;
  try {
    const s = await api('/api/inbox/dataset/stats');
    const pct = v => v == null ? '—' : Math.round(v * 100) + '%';
    const num = v => v == null ? '—' : v;
    $ib('ib-tr-imgs').textContent = s.images; $ib('ib-tr-imgs-sub').textContent = `已录入 ${s.done} · 含已转文本不再需要图的题`;
    $ib('ib-tr-boxes').textContent = s.boxes.total; $ib('ib-tr-boxes-sub').textContent = `题目 ${s.boxes.question} · 答案 ${s.boxes.answer} · 忽略 ${s.boxes.ignore}`;
    $ib('ib-tr-adopt').textContent = pct(s.ai.adoption_rate); $ib('ib-tr-adopt-sub').textContent = `AI 建议 ${s.ai.suggested} · 直接采纳 ${s.ai.adopted} · 微调 ${s.ai.edited}（IoU ${num(s.ai.mean_iou_edited)}）· 拒绝 ${s.ai.rejected}`;
    $ib('ib-tr-agree').textContent = pct(s.convert.agreement_rate); $ib('ib-tr-agree-sub').textContent = `AI 判断 ${s.convert.judged} 次，与人工最终选择一致 ${s.convert.agree}`;
    const b = s.blind || {}; const bl = $ib('ib-tr-blind');
    if (bl) bl.textContent = b.images ? `盲标 ${b.images} 张（已评估 ${b.evaluated}，待画 ${b.pending}）· 隐藏 AI 框 ${b.ai_boxes} 个，IoU≥0.5 命中 ${b.matched}，平均 IoU ${num(b.mean_iou)}` : '还没有盲标样本：在下方把「每 N 张盲标」设为大于 0 后，AI 框选会按间隔隐藏建议';
    const st = s.storage || {}; const se = $ib('ib-tr-storage');
    if (se) se.textContent = `原图 ${ibBytes(st.raw_bytes || 0)} · 裁图缓存 ${ibBytes(st.crops_bytes || 0)} · 已丢弃待清理 ${st.discarded || 0} 张`;
    const total = Math.max(1, s.images);
    $ib('ib-tr-layouts').innerHTML = Object.entries(s.layouts).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<div class="ib-bar"><span class="bl">${{ zuoyebang: '作业帮截图', photo: '拍照 / 扫描', plain: '已裁好的题图', other: '其他' }[k] || k}</span><div class="bt"><div class="bf" style="width:${Math.round(v / total * 100)}%"></div></div><span class="bv">${v} 张</span></div>`).join('') || '<div class="hint">还没有数据</div>';
    const dtotal = Math.max(1, s.convert.text + s.convert.image);
    $ib('ib-tr-convert').innerHTML = `<div class="ib-bar"><span class="bl">转文本</span><div class="bt"><div class="bf blue" style="width:${Math.round(s.convert.text / dtotal * 100)}%"></div></div><span class="bv">${s.convert.text}</span></div><div class="ib-bar"><span class="bl">保留图片</span><div class="bt"><div class="bf green" style="width:${Math.round(s.convert.image / dtotal * 100)}%"></div></div><span class="bv">${s.convert.image}</span></div>`;
  } catch (e) { ibToast('读取数据集统计失败：' + e.message, 'warn'); }
}
function ibExportDataset() { const fmt = $ib('ib-tr-fmt').value; window.location.href = `/api/inbox/dataset/export?format=${encodeURIComponent(fmt)}`; }

/* ── AI 训练：提供方与自动策略（存 config.json，与「设置」共用 /api/config）── */
async function ibLoadPolicy() {
  if (!$ib('ib-pl-provider')) return;
  try {
    const c = await api('/api/config');
    $ib('ib-pl-provider').value = c.inbox_detect_provider || 'vlm';
    $ib('ib-pl-local').value = c.inbox_local_detect_url || '';
    $ib('ib-pl-blind').value = c.inbox_blind_every || 0;
    $ib('ib-pl-conf').value = c.inbox_auto_ready_conf || 0;
    $ib('ib-pl-upload').checked = !!c.inbox_auto_on_upload;
    $ib('ib-pl-days').value = c.inbox_discard_keep_days == null ? 7 : c.inbox_discard_keep_days;
    ibPolicyToggle();
  } catch (e) { ibToast('读取策略配置失败：' + e.message, 'warn'); }
}
function ibPolicyToggle() { const row = $ib('ib-pl-local-row'); if (row) row.style.display = $ib('ib-pl-provider').value === 'local_http' ? '' : 'none'; }
async function ibSavePolicy() {
  const status = $ib('ib-pl-status');
  const body = {
    inbox_detect_provider: $ib('ib-pl-provider').value,
    inbox_local_detect_url: $ib('ib-pl-local').value.trim(),
    inbox_blind_every: Math.max(0, parseInt($ib('ib-pl-blind').value, 10) || 0),
    inbox_auto_ready_conf: Math.max(0, Math.min(1, parseFloat($ib('ib-pl-conf').value) || 0)),
    inbox_auto_on_upload: $ib('ib-pl-upload').checked,
    inbox_discard_keep_days: Math.max(0, parseInt($ib('ib-pl-days').value, 10) || 0),
  };
  try { await api('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); if (status) status.innerHTML = '<span style="color:var(--green)">✓ 已保存，立即生效</span>'; }
  catch (e) { if (status) status.innerHTML = `<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`; }
}
async function ibCleanup(crops) {
  if (crops && !await uiConfirm('清空裁剪缓存？（可重建，不影响原图与标注）')) return;
  try {
    const r = await api('/api/inbox/cleanup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ crops: !!crops }) });
    ibToast(`已清理：超过 ${r.discarded_days} 天的已丢弃原图 ${r.raw} 张（${ibBytes(r.raw_bytes)}）${crops ? `，裁图缓存 ${r.crops} 个` : ''}`);
    ibLoadStats();
  } catch (e) { ibToast('清理失败：' + e.message, 'warn'); }
}

/* ── 事件绑定（委托）── */
function ibBind() {
  const panel = $ib('panel-create');
  panel.addEventListener('click', ev => {
    const t = ev.target.closest('[data-ib-cur],[data-ib-rg],[data-ib-del],[data-ib-conv],[data-ib-extract],[data-ib-drawcard],[data-ib-classify],[data-ib-back],[data-ib-commit],[data-ib-stage],[data-ib-label-open]');
    if (!t) return;
    if (t.dataset.ibStage) { ibGo(t.dataset.ibStage); return; }
    if (t.dataset.ibDel) { ev.stopPropagation(); ibDeleteRegion(t.dataset.ibDel); return; }
    if (t.dataset.ibConv) { ev.stopPropagation(); const [id, v] = t.dataset.ibConv.split(':'); ibSetConvert(id, v); return; }
    if (t.dataset.ibExtract) { ev.stopPropagation(); ibExtractRegions(ibCur(), [t.dataset.ibExtract]); return; }
    if (t.dataset.ibDrawcard) { ev.preventDefault(); IB.drawCard = Number(t.dataset.ibDrawcard); ibToast(`接下来画的框归入题卡 ${IB.drawCard}`); return; }
    if (t.dataset.ibLabelOpen) { ev.stopPropagation(); ibOpenCardLabels(t.dataset.ibLabelOpen, t); return; }
    if (t.dataset.ibClassify) { ibClassify([t.dataset.ibClassify]); return; }
    if (t.dataset.ibBack) { ibBackToProcess(t.dataset.ibBack); return; }
    if (t.dataset.ibCommit) { ibCommit(t.dataset.ibCommit); return; }
    if (t.dataset.ibRg) { if (!ev.target.closest('textarea,input,button')) ibSelectRegion(t.dataset.ibRg); return; }
    if (t.dataset.ibCur) { if (!ev.target.closest('input,label')) ibOpen(t.dataset.ibCur); return; }

  });
  panel.addEventListener('change', ev => {
    const t = ev.target;
    if (t.dataset.ibSel) { t.checked ? IB.sel.add(t.dataset.ibSel) : IB.sel.delete(t.dataset.ibSel); ibRenderInbox(); ibRenderQueue(); }
    if (t.dataset.ibCsel) { t.checked ? IB.csel.add(t.dataset.ibCsel) : IB.csel.delete(t.dataset.ibCsel); ibRenderCards(); }
  });
  panel.addEventListener('input', ev => {
    const t = ev.target;
    if (t.dataset.ibText) ibEditText(t.dataset.ibText, t.value);
    if (t.dataset.ibF) { const [k, f] = t.dataset.ibF.split('|'); ibCardField(k, f, t.value); if (f === 'difficulty' && t.nextElementSibling) t.nextElementSibling.textContent = t.value; }
  });
  window.__omrs?.bus.on('inbox:reload', () => ibLoad());
  window.addEventListener('resize', () => { if (panel.classList.contains('active') && IB.stage === 'process') ibLayoutStage(); });
  // 侧栏裁剪预览在每次渲染后补画
  const obs = new MutationObserver(() => { if (document.querySelector('[data-ib-cropcv]')) ibPaintCropCanvases(); });
  obs.observe($ib('ib-ps-body'), { childList: true });
}

// 分步迁移适配：新网格借用旧处理区的数据与批量算法，P6 收尾时删除。
if (typeof window !== 'undefined') window.__omrsInbox = {
  snapshot: () => ({ items: IB.items, selected: IB.sel, stage: IB.stage }),
  refresh: () => { ibRenderInbox(); ibRenderQueue(); },
  open: id => { IB.cur = id; ibGo('process'); },
  reload: ibLoad,
  detect: ibDetectSelected,
  applyLast: ibApplyLastSelected,
  whole: ibWholeSelected,
  flush: ibFlushSaves,
  process: {
    state: () => IB,
    afterEdit: ibAfterEdit,
    deleteRegion: ibDeleteRegion,
    queueAll: on => { ibQueue().forEach(item => on ? IB.sel.add(item.id) : IB.sel.delete(item.id)); ibRenderQueue(); ibRenderInbox(); },
    layout: ibSetLayout,
    detectSelected: ibDetectSelected,
    applyLastSelected: ibApplyLastSelected,
    step: ibStep,
    role: ibSetDrawRole,
    detectCurrent: ibDetectCurrent,
    wholeImage: ibWholeImage,
    applyLast: ibApplyLast,
    clearBoxes: ibClearBoxes,
    addCard: ibAddCard,
    discardCurrent: ibDiscardCurrent,
    extractAll: ibExtractAll,
    markReady: ibMarkReady,
  },
};
