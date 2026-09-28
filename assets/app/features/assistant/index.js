/**
 * AI 助手页（#/assistant）：对话列表、运行轨迹、确认与撤销、检查器。
 * 数据：/api/agent/*（AI/api.md）。发消息后长轮询 /api/agent/events 取增量事件，state.js 归约，view.js 渲染，
 * 各区域分别 morph。写入后经 domain 层刷新题目数据、Session 与题目缓存。见 AI/frontend/assistant.md。
 */
import { html, escape } from '../../core/html.js';
import { morph, toElement } from '../../core/dom.js';
import { get, post } from '../../core/api.js';
import { icon } from '../../ui/icon.js';
import { toast } from '../../ui/toast.js';
import { dialog } from '../../ui/dialog.js';
import { openModal } from '../../ui/overlay.js';
import { itemsNow, reloadData } from '../../domain/data.js';
import { copyText, refreshSessions } from '../../domain/sessions.js';
import { invalidateQuestions, viewQ } from '../../domain/question/index.js';
import { applyEvent, mmss, newRun, runFrom, runNow } from './state.js';
import { confirmOf, setRefRenderer, toolTitle } from './tools-view.js';
import { SUGS, dockView, headView, railView, streamView } from './view.js';
import { inspView } from './insp-view.js';

let C = null;
const today = () => new Date().toISOString().slice(0, 10);

function refRenderer(code) {
  const item = itemsNow().find(i => i.uid === code);
  if (item) {
    const tone = item.suspended ? 'off' : item.is_leech ? 'leech' : item.due_date && item.due_date <= today() ? 'due' : 'ok';
    return `<button type="button" class="ast-ref" data-action="assistant.openQ" data-arg="${escape(code)}"><i class="ast-ref__dot is-${tone}"></i>${escape(code)}</button>`;
  }
  if (/^(EXP|SES|FIXTURE)-[\w-]+$/.test(code)) return `<button type="button" class="ast-ref" data-action="assistant.openSession" data-arg="${escape(code)}">${escape(code)}</button>`;
  if (/^CMT-\d{6}$/.test(code)) return `<span class="ast-ref ast-ref--commit">${escape(code)}</span>`;
  return `<code>${escape(code)}</code>`;
}

/** 侧栏入口：未启用时隐藏；运行中显示活动点，等确认时显示角标。main.js 启动时调用一次。 */
export async function syncAssistantNav(doc = document, status) {
  const st = status || (await get('/api/agent/status')).data;
  const tab = doc.querySelector('.tab[data-tab="assistant"]');
  if (!tab || !st) return;
  tab.hidden = !st.enabled;
  const active = (st.active || [])[0];
  tab.classList.toggle('is-live', !!active);
  tab.classList.toggle('is-waiting', active?.status === 'waiting');
}

function createController(root, { router }) {
  const S = { status: null, convs: [], convId: null, items: [], msgs: 0, open: new Set(), closed: new Set(), runSel: null,
    liveRun: null, lastRun: null, popOpen: false, stick: true, inspOpen: false, railOpen: false, uiVer: 0, sugs: SUGS, alive: true };
  morph(root, html`<div class="ast" data-rail="closed" data-insp="closed">
    <div class="ast-scrim" data-action="assistant.closeDrawers"></div>
    <aside class="ast-card ast-rail" id="ast-rail" aria-label="对话列表"></aside>
    <section class="ast-card ast-main" aria-label="对话"><header class="ast-head" id="ast-head"></header>
      <div class="ast-scroll" id="ast-scroll"><div class="ast-stream" id="ast-stream" aria-live="polite"></div></div>
      <div class="ast-dockwrap"><button type="button" class="ui-btn ui-btn--sm ast-jump" data-action="assistant.jump" hidden>${icon('arrow-down')}回到最新</button>
      <div class="ast-dock" id="ast-dock"></div></div></section>
    <aside class="ast-card ast-insp" id="ast-insp" aria-label="运行详情"></aside></div>`);
  const $ = id => root.querySelector('#' + id);
  const shell = root.querySelector('.ast');
  const scroller = $('ast-scroll');
  let frame = 0;
  let ticker = 0;
  setRefRenderer(refRenderer);

  function paint() {
    frame = 0;
    if (!S.alive) return;
    const now = performance.now();
    shell.dataset.rail = S.railOpen ? 'open' : 'closed';
    shell.dataset.insp = S.inspOpen ? 'open' : 'closed';
    morph($('ast-rail'), railView(S));
    morph($('ast-head'), headView(S));
    morph($('ast-stream'), streamView(S, now));
    const input = $('ast-input');
    const draft = input ? input.value : '';
    morph($('ast-dock'), dockView(S, now));
    if ($('ast-input') && !$('ast-input').value && draft) $('ast-input').value = draft;
    morph($('ast-insp'), inspView(S, now));
    if (S.stick) scroller.scrollTop = scroller.scrollHeight;
    root.querySelector('.ast-jump').hidden = S.stick || !S.liveRun;
  }
  const schedule = () => { if (!frame) frame = requestAnimationFrame(paint); };
  // 贴底跟随：只有用户自己往上滚才停止跟随；滚回底部恢复
  const atBottom = () => scroller.scrollTop + scroller.clientHeight >= scroller.scrollHeight - 48;
  const onUserScroll = () => requestAnimationFrame(() => { S.stick = atBottom(); root.querySelector('.ast-jump').hidden = S.stick || !S.liveRun; });
  scroller.addEventListener('wheel', onUserScroll, { passive: true });
  scroller.addEventListener('touchmove', onUserScroll, { passive: true });
  scroller.addEventListener('keyup', onUserScroll);
  const bump = () => { S.uiVer += 1; schedule(); };

  function setLive(run) {
    S.liveRun = run && run.status !== 'done' ? run : null;
    clearInterval(ticker);
    if (S.liveRun) ticker = setInterval(schedule, 250);
    syncAssistantNav(document, { ...S.status, active: S.liveRun ? [{ status: S.liveRun.status }] : [] });
  }

  async function loadList() {
    const [st, cv] = await Promise.all([get('/api/agent/status'), get('/api/agent/conversations')]);
    if (st.ok) S.status = st.data;
    if (cv.ok) S.convs = cv.data.conversations || [];
    return st.data;
  }

  async function load() {
    const st = await loadList();
    const active = st?.active?.[0];
    const target = active?.conversation_id || S.convId || S.convs[0]?.id || null;
    if (target) await openConv(target); else schedule();
  }

  async function openConv(id) {
    const res = await get(`/api/agent/conversation?id=${encodeURIComponent(id)}`);
    if (!res.ok) { toast(res.error?.message || '打开对话失败', { kind: 'error' }); return; }
    S.convId = id; S.railOpen = false; S.runSel = null; S.popOpen = false; S.stick = true;
    S.msgs = res.data.msgs;
    S.items = res.data.items.map(it => (it.type === 'user' ? it : { type: 'run', run: runFrom(it.run, it.events), live: it.live }));
    const runs = S.items.filter(i => i.run).map(i => i.run);
    S.lastRun = runs[runs.length - 1] || null;
    const live = S.items.find(i => i.live);
    setLive(live ? live.run : null);
    if (live) follow(live.run);
    schedule();
  }

  async function follow(run) {
    if (run.following) return;
    run.following = true;
    while (S.alive && run.status !== 'done') {
      const res = await get(`/api/agent/events?run=${encodeURIComponent(run.id)}&after=${run.next}&wait=20`, { timeout: 28000 });
      if (!S.alive) return;
      if (!res.ok) { await new Promise(r => setTimeout(r, 1500)); continue; }
      for (const ev of res.data.events) applyEvent(run, ev);
      if (res.data.compacted && run.status !== 'done') applyEvent(run, { type: 'run.end', t: run.clock.t, data: { reason: 'interrupted' } });
      schedule();
    }
    run.following = false;
    await finish(run);
  }

  async function finish(run) {
    setLive(null);
    S.lastRun = run;
    await loadList();
    S.msgs = S.convs.find(c => c.id === S.convId)?.msgs ?? S.msgs;
    if (run.commits.length) {
      const uids = new Set();
      run.steps.forEach(s => { const a = s.args || {}; [a.uid, ...(a.uids || []), ...(a.items || []).map(i => i.uid)].filter(Boolean).forEach(u => uids.add(u)); });
      invalidateQuestions([...uids]);
      await Promise.all([reloadData(), refreshSessions()]);
      toast(`助手写入了 ${run.commits.length} 条记录，可在这次回答下方整体撤销`, { kind: 'success' });
    }
    bump();
  }

  async function send(text) {
    text = String(text || '').trim();
    if (!text) return;
    if (!S.convId) {
      const res = await post('/api/agent/conversation/create', {});
      if (!res.ok) { toast(res.error?.message || '新建对话失败', { kind: 'error' }); return; }
      S.convId = res.data.conversation.id; S.items = []; S.msgs = 0;
    }
    const res = await post('/api/agent/message', { conversation_id: S.convId, text });
    if (!res.ok) { toast(res.error?.message || '发送失败', { kind: 'error' }); return false; }
    const input = $('ast-input');
    if (input) input.value = '';
    if (res.data.steered) return true;
    const run = newRun({ id: res.data.run_id, conversation_id: S.convId, model: S.status?.model });
    S.items.push({ type: 'user', text, at: new Date().toISOString() }, { type: 'run', run });
    S.msgs += 1;
    setLive(run);
    schedule();
    S.stick = true;
    follow(run);
    loadList().then(schedule);
    return true;
  }

  const findStep = arg => {
    const [runId, id] = String(arg).split('|');
    const run = S.items.map(i => i.run).find(r => r && r.id === runId);
    return { run, st: run && (run.byCall.get(id) || run.steps.find(s => s.id === id)) };
  };

  async function decide(run, st, how) {
    const res = await post('/api/agent/confirm', { run_id: run.id, call_id: st.callId, token: st.token, decision: how });
    if (!res.ok) toast(res.error?.message || '确认没有送达', { kind: 'error' });
  }

  function gate(arg) {
    const { run, st } = findStep(arg);
    if (!run || !st || st.status !== 'waiting') return;
    const spec = confirmOf(st);
    const el = toElement(html`<dialog class="ui-dialog ui-dialog--lg ast-gate-dlg" aria-labelledby="ast-gate-t">
      <div class="ui-dialog__panel"><header class="ui-dialog__head"><h2 class="ui-dialog__title" id="ast-gate-t">${spec.title}</h2>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm ui-dialog__close" data-gate="close" aria-label="稍后再说">${icon('x')}</button></header>
      ${spec.hint ? html`<p class="ui-dialog__hint">${spec.hint}</p>` : ''}<div class="ui-dialog__body">${spec.body}</div>
      <footer class="ui-dialog__foot"><span class="ast-gate__clock" data-gate-clock></span><button type="button" class="ui-btn" data-gate="deny">拒绝</button>
      <button type="button" class="ui-btn ui-btn--primary" data-gate="allow">${icon('check')}${spec.ok}</button></footer></div></dialog>`);
    const clock = el.querySelector('[data-gate-clock]');
    const tick = () => {
      if (st.status !== 'waiting') { entry.close(false); return; }
      clock.textContent = `${mmss((st.ttl || 600000) - (runNow(run, performance.now()) - (st.gateT0 || 0)))} 后过期`;
    };
    const timer = setInterval(tick, 500);
    const entry = openModal(el, { dismissible: true, initialFocus: '[data-gate="deny"]', onClose: () => clearInterval(timer) });
    tick();
    el.addEventListener('click', event => {
      const how = event.target.closest('[data-gate]')?.dataset.gate;
      if (!how) return;
      entry.close(how === 'allow');
      if (how !== 'close') decide(run, st, how);
    });
  }

  async function undo(runId) {
    const run = S.items.map(i => i.run).find(r => r && r.id === runId);
    const res = await post('/api/agent/run/revert', { run_id: runId, dry_run: true });
    if (!res.ok || !run) { toast(res.error?.message || '取不到撤销计划', { kind: 'error' }); return; }
    const plan = res.data;
    const blocked = !plan.ok;
    const body = html`${plan.items.length ? html`<ol class="ast-undo-list">${plan.items.map(i => html`<li><code>${i.commit_id}</code><span>${i.undo}</span></li>`)}</ol>` : ''}
      ${plan.conflicts.length ? html`<div class="ast-undo-hint is-error"><strong>不能整体撤销：</strong>之后又有写入碰过同样的题或 Session。<ul>${plan.conflicts.map(c => html`<li>${c.label}：${c.by_desc}${c.by_commit_id ? `（${c.by_commit_id}）` : ''}</li>`)}</ul></div>`
        : html`<p class="ast-undo-hint">每条撤销另记一条 commit，原记录保留，可在历史页查到。</p>`}${plan.msg ? html`<p class="ast-note">${plan.msg}</p>` : ''}`;
    await dialog({
      title: blocked ? '这次运行不能撤销' : `撤销这次运行的 ${plan.items.length} 条写入？`, size: 'md', body, danger: !blocked,
      okText: blocked ? '知道了' : '撤销', hideCancel: blocked,
      onOk: async () => {
        if (blocked) return true;
        const out = await post('/api/agent/run/revert', { run_id: runId, dry_run: false });
        if (!out.ok) { toast(out.error?.message || '撤销失败', { kind: 'error' }); return false; }
        run.reverted = out.data.info; run.ver += 1;
        await Promise.all([reloadData(), refreshSessions(), loadList()]);
        invalidateQuestions();
        toast(`已撤销 ${out.data.reverted.length} 条写入`, { kind: 'success' });
        bump();
        return true;
      },
    });
  }

  const onKey = event => {
    if (event.target.id !== 'ast-input' || event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    send(event.target.value);
  };
  root.addEventListener('keydown', onKey);
  const onDoc = event => { if (S.popOpen && !event.target.closest('.ast-pop, .ast-meter')) { S.popOpen = false; schedule(); } };
  document.addEventListener('click', onDoc);

  return {
    S, load, schedule, bump, openConv, send, gate, undo,
    async newConv() { const res = await post('/api/agent/conversation/create', {}); if (res.ok) { S.convs.unshift({ ...res.data.conversation, msgs: 0, writes: 0, snippet: '' }); await openConv(res.data.conversation.id); $('ast-input')?.focus(); } },
    toggleStep(arg) { const k = String(arg); const { st } = findStep(k); const open = S.open.has(k) || (st?.phase === 'live' && !S.closed.has(k)); if (open) { S.open.delete(k); S.closed.add(k); } else { S.open.add(k); S.closed.delete(k); } bump(); },
    deny(arg) { const { run, st } = findStep(arg); if (run && st?.status === 'waiting') decide(run, st, 'deny'); },
    async stop() { if (S.liveRun) { const res = await post('/api/agent/abort', { run_id: S.liveRun.id }); if (!res.ok) toast(res.error?.message || '停止失败', { kind: 'error' }); } },
    async copy(runId) { const run = S.items.map(i => i.run).find(r => r && r.id === runId); const text = run ? run.steps.filter(s => s.kind === 'text').map(s => s.src).join('\n\n') : ''; if (await copyText(text)) toast('已复制回答', { kind: 'success' }); },
    select(runId) { S.runSel = runId; S.inspOpen = true; bump(); },
    toggle(key) { S[key] = !S[key]; if (key === 'railOpen' && S.railOpen) S.inspOpen = false; if (key === 'inspOpen' && S.inspOpen) S.railOpen = false; schedule(); },
    closeDrawers() { S.railOpen = false; S.inspOpen = false; schedule(); },
    jump() { S.stick = true; scroller.scrollTop = scroller.scrollHeight; schedule(); },
    openSession() { router?.go?.('schedule'); },
    dispose() { S.alive = false; clearInterval(ticker); cancelAnimationFrame(frame); root.removeEventListener('keydown', onKey); document.removeEventListener('click', onDoc); },
    title: toolTitle,
  };
}

export const page = {
  id: 'assistant', title: 'AI 助手', workbench: true,
  mount(root, ctx = {}) {
    C = createController(root, ctx);
    C.schedule();
    C.load();
    const off = ctx.bus?.on?.('data', () => C?.bump());
    return () => { off?.(); C?.dispose(); C = null; };
  },
  actions: {
    newConv: () => C?.newConv(),
    openConv: ({ arg }) => C?.openConv(arg),
    send: () => C?.send(document.getElementById('ast-input')?.value),
    sug: ({ arg }) => C?.send(C.S.sugs[arg]?.text),
    stop: () => C?.stop(),
    toggleStep: ({ arg }) => C?.toggleStep(arg),
    gate: ({ arg }) => C?.gate(arg),
    deny: ({ arg }) => C?.deny(arg),
    undo: ({ arg }) => C?.undo(arg),
    copy: ({ arg }) => C?.copy(arg),
    selectRun: ({ arg }) => C?.select(arg),
    openQ: ({ arg }) => viewQ(arg),
    openSession: () => C?.openSession(),
    toggleRail: () => C?.toggle('railOpen'),
    toggleInsp: () => C?.toggle('inspOpen'),
    closeDrawers: () => C?.closeDrawers(),
    pop: () => C?.toggle('popOpen'),
    jump: () => C?.jump(),
  },
};
