import { businessToday, daysBetween } from '../../core/date.js';
/**
 * 助手页的纯函数：把服务端事件流归约成「一次运行」的视图模型（步骤、时间线、用量、写入），以及格式化与对话分组。
 * 事件协议见 AI/agent.md「事件」；node 单测覆盖（tests/app/assistant.test.mjs）。
 */
import { usageRecord, usageTotals } from './usage.js';
export const pad = n => String(n).padStart(2, '0');
export const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
export const fmtK = n => { n = Math.round(n || 0); return n >= 1000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1) + 'k' : String(n); };
export const fmtN = n => Math.round(n || 0).toLocaleString('en-US');
export const fmtS = ms => { ms = Math.max(0, ms || 0); return ms < 1000 ? (ms / 1000).toFixed(2) + 's' : ms < 60000 ? (ms / 1000).toFixed(1) + 's' : Math.floor(ms / 60000) + 'm' + pad(Math.round((ms % 60000) / 1000)) + 's'; };
export const pct = x => (x == null ? '新题' : Math.round(x * 100) + '%');
export const mmss = ms => { const s = Math.max(0, Math.ceil(ms / 1000)); return Math.floor(s / 60) + ':' + pad(s % 60); };
export const hhmm = d => { d = new Date(d); return Number.isNaN(d.getTime()) ? '' : pad(d.getHours()) + ':' + pad(d.getMinutes()); };
export const hms = d => { d = new Date(d); return Number.isNaN(d.getTime()) ? '' : hhmm(d) + ':' + pad(d.getSeconds()); };

export function tokOf(s) {
  const text = String(s || '');
  const cjk = (text.match(/[\u3000-\u303f\u3400-\u9fff\uf900-\ufaff\uff00-\uffef]/g) || []).length;
  return cjk / 1.35 + (text.length - cjk) / 3.6;
}

export function newRun(meta = {}) {
  return {
    id: meta.id, conv: meta.conversation_id, model: meta.model || '', status: meta.status === 'done' ? 'done' : 'running',
    reason: meta.reason || null, error: meta.error || '', startedAt: meta.started_at || new Date().toISOString(),
    reverted: meta.reverted || null, steps: [], timeline: [], byCall: new Map(), rounds: 0, calls: 0, writes: 0, commits: [],
    usage: { prompt: 0, cached: 0, out: 0, think: 0 }, usageRequests: new Map(), usageTotals: usageTotals(new Map()),
    seenEvents: new Set(), ttfts: [], genMs: 0, genTok: 0, peak: 0, win: [], spark: [],
    ctx: { sys: 0, tools: 0, chat: 0, res: 0, msgs: 0 }, roundOut: 0, limits: null, dur: 0, next: 0, clock: { t: 0, at: 0 },
    aborting: false, ver: 0, seg: null, round: null,
  };
}

const think = run => run.round?.think;
function closeThink(run, t) {
  const th = think(run);
  if (!th || th.phase === 'done' || th.phase === 'cut') return;
  if (!th.src) { run.steps = run.steps.filter(s => s !== th); run.round.think = null; return; }
  th.phase = 'done'; th.t1 = t;
}
function argsStep(run, index, name, t) {
  const key = `r${run.rounds}-a${index ?? 0}`;
  let st = run.round.args.get(key);
  if (!st) {
    st = { kind: 'tool', id: key, name: name || '', argsSrc: '', status: 'args', args: null, level: 'read', t0: null, q0: t };
    run.round.args.set(key, st);
    run.round.order.push(st);
    run.steps.push(st);
  }
  if (name && !st.name) st.name = name;
  return st;
}
function countTok(run, t, tok, isThink) {
  run.genTok += tok; run.roundOut += tok;
  const key = `round:${run.rounds}`;
  const prior = run.usageRequests.get(key) || { input: null, output: 0, cache: null, reasoning: null,
    scope: 'main', source: 'estimated', estimated: true, invalid: false };
  if (prior.estimated) run.usageRequests.set(key, { ...prior, output: (prior.output || 0) + tok,
    reasoning: isThink ? (prior.reasoning || 0) + tok : prior.reasoning });
  refreshUsage(run);
  run.win.push([t, tok]);
}

function refreshUsage(run) {
  run.usageTotals = usageTotals(run.usageRequests);
  const main = [...run.usageRequests.values()].filter(row => row.scope === 'main');
  run.usage.prompt = run.usageTotals.main.input;
  run.usage.cached = run.usageTotals.cache.read;
  run.usage.out = run.usageTotals.main.output;
  run.usage.think = main.reduce((n, row) => n + (row.reasoning || 0), 0);
}

export function liveTps(run, now) {
  const win = 1000;
  let tok = 0;
  for (const [t, k] of run.win) if (t > now - win) tok += k;
  return tok / (win / 1000);
}
export const avgTps = run => (run && run.genMs ? run.genTok / (run.genMs / 1000) : 0);

/** 归约一条事件。返回 run（就地修改）。 */
export function applyEvent(run, ev) {
  const d = ev.data || {};
  const t = ev.t || 0;
  if (ev.i != null && run.seenEvents.has(ev.i)) return run;
  if (ev.i != null) run.seenEvents.add(ev.i);
  run.next = Math.max(run.next, (ev.i ?? run.next) + 1);
  run.ver += 1;
  switch (ev.type) {
    case 'run.start':
      run.model = d.model || run.model; run.limits = d.limits || run.limits; run.ctxWindow = d.context_window;
      break;
    case 'round.start': {
      run.rounds = d.n;
      run.seg = { kind: 'model', n: d.n, t0: t, tf: null, t1: null };
      run.timeline.push(run.seg);
      const th = { kind: 'think', id: `r${d.n}-think`, phase: 'wait', src: '', t0: t, open: false };
      run.steps.push(th);
      run.round = { think: th, text: null, args: new Map(), order: [], calls: 0 };
      run.ctx = { ...run.ctx, ...(d.context || {}) };
      run.roundOut = 0;
      const contextInput = d.context ? Math.round(['sys', 'tools', 'chat', 'res']
        .reduce((sum, key) => sum + (Number(d.context[key]) || 0), 0)) : null;
      if (!run.usageRequests.has(`round:${d.n}`)) run.usageRequests.set(`round:${d.n}`, {
        input: contextInput, output: null, cache: null, reasoning: null, scope: 'main', source: 'estimated',
        estimated: true, invalid: false });
      refreshUsage(run);
      break;
    }
    case 'delta': {
      if (!run.round) break;
      if (run.seg && run.seg.tf == null) { run.seg.tf = t; run.ttfts.push(t - run.seg.t0); }
      const tok = tokOf(d.text);
      if (d.kind === 'think') {
        const th = think(run);
        if (th) { th.phase = 'live'; th.tStart = th.tStart ?? t; th.src += d.text; }
        countTok(run, t, tok, true);
      } else if (d.kind === 'text') {
        closeThink(run, t);
        if (!run.round.text) { run.round.text = { kind: 'text', id: `r${d.n}-text`, src: '', live: true }; run.steps.push(run.round.text); }
        run.round.text.src += d.text;
        countTok(run, t, tok, false);
      } else if (d.kind === 'args') {
        closeThink(run, t);
        if (run.round.text) run.round.text.live = false;
        argsStep(run, d.index, d.name, t).argsSrc += d.text;
        countTok(run, t, tok, false);
      }
      break;
    }
    case 'round.end': {
      if (run.seg) { run.seg.t1 = t; if (run.seg.tf == null) { run.seg.tf = t; run.ttfts.push(t - run.seg.t0); } }
      if (run.round) { closeThink(run, t); if (run.round.text) run.round.text.live = false; }
      const u = d.usage || {};
      const key = d.request_id || `round:${d.n}`;
      const row = usageRecord(u);
      const prior = run.usageRequests.get(key);
      if (row.input === null && prior?.input != null) row.input = prior.input;
      if (row.output === null && prior) row.output = prior.output;
      if (row.output === null || row.input === null) row.estimated = true;
      if (row.source === 'missing' && prior && (row.input !== null || row.output !== null)) row.source = 'estimated';
      if (prior?.estimated && (u.input_total == null && u.prompt == null || u.output_total == null && u.completion == null)) row.estimated = true;
      run.usageRequests.set(key, row);
      refreshUsage(run);
      run.genMs += d.gen_ms || 0;
      if (d.gen_ms > 400) run.peak = Math.max(run.peak, run.roundOut / (d.gen_ms / 1000));
      if (row.input !== null) run.ctx = { ...run.ctx, prompt: row.input };
      break;
    }
    case 'usage.aux': {
      const key = d.request_id || `aux:${ev.i}`;
      run.usageRequests.set(key, usageRecord(d.usage, 'aux'));
      refreshUsage(run);
      break;
    }
    case 'tool.call': {
      if (!run.round) break;
      const st = run.round.order[run.round.calls] || argsStep(run, run.round.calls, d.name, t);
      run.round.calls += 1;
      Object.assign(st, { callId: d.call_id, name: d.name, args: d.args, level: d.level || 'read', status: 'queued', q0: t, argsSrc: d.arguments || st.argsSrc });
      run.byCall.set(d.call_id, st);
      run.calls += 1;
      break;
    }
    case 'tool.running': {
      const st = run.byCall.get(d.call_id);
      if (st) { st.status = 'running'; st.t0 = t; st.seg = st.seg || { kind: 'tool', step: st.id, q0: st.q0 }; st.seg.t0 = t; if (!run.timeline.includes(st.seg)) run.timeline.push(st.seg); }
      break;
    }
    case 'tool.waiting': {
      const st = run.byCall.get(d.call_id);
      if (st) {
        Object.assign(st, { status: 'waiting', gateT0: t, ttl: d.ttl_ms, token: d.token, preview: d.preview || {} });
        st.seg = { kind: 'tool', step: st.id, q0: st.q0, w0: t };
        run.timeline.push(st.seg);
      }
      run.status = 'waiting';
      break;
    }
    case 'tool.decision': {
      const st = run.byCall.get(d.call_id);
      if (st) { st.decision = { how: d.how, t }; if (st.seg) st.seg.w1 = t; if (st.status === 'waiting') st.status = 'queued'; }
      run.status = 'running';
      break;
    }
    case 'tool.end': {
      const st = run.byCall.get(d.call_id);
      if (!st) break;
      st.status = d.status === 'done' ? 'done' : d.status;
      st.summary = d.summary || ''; st.error = d.error || ''; st.result = d.result ?? (d.error ? { ok: false, error: d.error } : null);
      st.resultChars = d.result_chars || 0; st.dur = d.dur_ms || 0; st.extra = d.extra || null; st.t1 = t;
      st.wrote = Boolean(d.wrote || d.commits?.length);
      if (d.decision && !st.decision) st.decision = { how: d.decision, t };
      if (st.seg) st.seg.t1 = t;
      if (st.wrote) {
        run.writes += 1;
        st.commits = d.commits || [];
        st.commits.forEach(c => run.commits.push({ ...c, level: st.level, callId: st.callId }));
      }
      break;
    }
    case 'steer.queued':
      run.steps.push({ kind: 'steer', id: 'steer-' + d.id, steerId: d.id, text: d.text, delivered: 0 });
      break;
    case 'steer.delivered': case 'steer.late': {
      const st = run.steps.find(s => s.steerId === d.id);
      if (st) st.delivered = ev.type === 'steer.late' ? -1 : d.round;
      break;
    }
    case 'image.transcribe': {
      const ref = d.ref || 'IMG';
      const id = `image-${ref}`;
      let st = run.steps.find(s => s.kind === 'image' && s.id === id);
      if (!st) { st = { kind: 'image', id, ref, status: 'running', cached: !!d.cached, ms: 0, error: '' }; run.steps.push(st); }
      st.status = 'running'; st.cached = !!d.cached;
      break;
    }
    case 'image.transcribed': {
      const ref = d.ref || 'IMG';
      const id = `image-${ref}`;
      let st = run.steps.find(s => s.kind === 'image' && s.id === id);
      if (!st) { st = { kind: 'image', id, ref, status: d.ok === false ? 'error' : 'done', cached: false, ms: 0, error: '' }; run.steps.push(st); }
      st.status = d.ok === false ? 'error' : 'done'; st.ms = d.ms || 0; st.error = d.error || '';
      break;
    }
    case 'run.aborting': run.aborting = true; break;
    case 'run.end':
      run.status = 'done'; run.reason = d.reason; run.error = d.error || ''; run.dur = t;
      for (const s of run.steps) {
        if (s.kind === 'think' && (s.phase === 'wait' || s.phase === 'live')) { s.phase = s.src ? 'cut' : 'gone'; s.t1 = t; }
        if (s.kind === 'text' && s.live) { s.live = false; s.cut = d.reason === 'aborted'; }
        if (s.kind === 'tool' && ['args', 'queued', 'waiting', 'running'].includes(s.status)) s.status = 'aborted';
        if (s.kind === 'image' && s.status === 'running') s.status = 'aborted';
      }
      run.steps = run.steps.filter(s => s.phase !== 'gone');
      for (const seg of run.timeline) { if (seg.t1 == null && seg.kind === 'model') seg.t1 = t; if (seg.w0 != null && seg.w1 == null) seg.w1 = t; }
      break;
    default: break;
  }
  run.clock = { t, at: typeof performance !== 'undefined' ? performance.now() : 0 };
  return run;
}

export function runFrom(meta, events, { hasMore = false, next } = {}) {
  const run = newRun(meta);
  for (const ev of events || []) applyEvent(run, ev);
  if (!hasMore && meta.status === 'done' && run.status !== 'done') applyEvent(run, { type: 'run.end', t: run.clock.t, data: { reason: meta.reason || 'interrupted', error: meta.error } });
  if (hasMore && meta.status === 'done') run.status = 'done';
  run.eventsMore = hasMore; run.eventsBusy = false;
  if (next != null) run.next = next;
  return run;
}

/** 运行中：服务端最后一条事件的时间 + 本地流逝。 */
export const runNow = (run, perfNow) => (run.status === 'done' ? run.dur : run.clock.t + Math.max(0, perfNow - run.clock.at));

export function ctxUsed(run) {
  if (!run) return 0;
  const c = run.ctx;
  return (c.prompt || (c.sys + c.tools + c.chat + c.res)) + (run.status !== 'done' ? run.roundOut : 0);
}

export function dayGroup(iso, now = new Date()) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '更早';
  const diff = daysBetween(businessToday(d), businessToday(now));
  return diff <= 0 ? '今天' : diff === 1 ? '昨天' : '更早';
}

export const REASON = { completed: '完成', aborted: '已中止', error: '出错', budget: '预算用完', max_rounds: '轮数到上限', interrupted: '服务重启中断' };

/** 历史页保留稳定 DOM 键；事件尚未读完时不提前合成终止事件。 */
export function historyItems(items = []) {
  return items.map((item, index) => {
    const item_key = item.item_key || (item.type === 'user' ? `user:${items[index + 1]?.run?.id || item.at || index}` : `run:${item.run.id}`);
    return item.type === 'user' ? { ...item, item_key } : { ...item, item_key,
      run: runFrom(item.run, item.events, { hasMore: !!item.events_has_more, next: item.events_next }) };
  });
}
export function mergeHistoryItems(older, current) {
  const existing = new Set(current.map(item => item.item_key));
  return [...older.filter(item => !existing.has(item.item_key)), ...current];
}
