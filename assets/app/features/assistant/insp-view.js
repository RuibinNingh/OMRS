/** 检查器：选中运行的用量、瀑布时间线（SVG）、预算与写入记录。 */
import { html, raw } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { REASON, avgTps, fmtK, fmtN, fmtS, hms, liveTps, runNow } from './state.js';
import { lvl, toolTitle } from './tools-view.js';
import { bar } from './tools-view.js';

const esc = s => String(s ?? '').replace(/[&<>"]/g, ch => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[ch]);

function waterfall(run, now) {
  const end = Math.max(1, run.status === 'done' ? run.dur : now);
  const W = 300; const L = 74; const R = 4; const H = 14; const G = 5;
  const X = t => L + ((W - L - R) * Math.max(0, Math.min(end, t))) / end;
  const rows = run.timeline.slice(-18);
  let y = 0;
  const out = [];
  for (const seg of rows) {
    const st = seg.kind === 'tool' ? run.steps.find(s => s.id === seg.step) : null;
    const label = seg.kind === 'model' ? `第 ${seg.n} 轮` : st ? toolTitle(st) : '工具';
    out.push(`<text class="ast-wf__lbl" x="0" y="${y + 10}">${esc(label.length > 7 ? label.slice(0, 7) + '…' : label)}</text>`);
    out.push(`<rect class="ast-wf__track" x="${L}" y="${y}" width="${W - L - R}" height="${H}"/>`);
    const rect = (a, b, c) => { if (a == null) return; const x0 = X(a); const x1 = Math.max(x0 + 2, X(b ?? now)); out.push(`<rect class="${c}" x="${x0.toFixed(1)}" y="${y + 2}" width="${(x1 - x0).toFixed(1)}" height="${H - 4}"/>`); };
    if (seg.kind === 'model') { rect(seg.t0, seg.tf ?? seg.t1, 'ast-wf__wait'); if (seg.tf != null) rect(seg.tf, seg.t1, 'ast-wf__gen'); }
    else { if (seg.w0 != null) rect(seg.w0, seg.w1, 'ast-wf__user'); if (seg.t0 != null) rect(seg.t0, seg.t1, st?.status === 'error' ? 'ast-wf__err' : 'ast-wf__tool'); }
    y += H + G;
  }
  const ticks = [0, 0.5, 1].map(f => `<text class="ast-wf__tick" x="${(L + (W - L - R) * f).toFixed(1)}" y="${y + 9}" text-anchor="${f === 0 ? 'start' : f === 1 ? 'end' : 'middle'}">${fmtS(end * f)}</text>`).join('');
  return raw(`<svg class="ast-wf" viewBox="0 0 ${W} ${y + 12}" role="img" aria-label="时间线">${out.join('')}${ticks}</svg>`);
}

function spark(run, now) {
  const slot = 250; const n = 40; const buckets = new Array(n).fill(0);
  const start = now - n * slot;
  for (const [t, k] of run.win) { const i = Math.floor((t - start) / slot); if (i >= 0 && i < n) buckets[i] += k; }
  const max = Math.max(1, ...buckets);
  return raw(`<svg class="ast-spark" viewBox="0 0 ${n * 3} 20" preserveAspectRatio="none" aria-hidden="true">${buckets.map((b, i) => { const h = Math.max(b ? 1 : 0, (b / max) * 20); return `<rect x="${i * 3}" y="${(20 - h).toFixed(1)}" width="2" height="${h.toFixed(1)}"/>`; }).join('')}</svg>`);
}

const usage = (k, v, s) => html`<div class="ast-usage__c"><span class="ast-usage__k">${k}</span><span class="ast-usage__v">${v}</span>${s ? html`<span class="ast-usage__s">${s}</span>` : ''}</div>`;

export function inspView(S, perfNow) {
  const run = S.items.map(i => i.run).filter(Boolean).find(r => r.id === S.runSel) || S.liveRun || S.lastRun;
  const head = html`<header class="ast-insp__head"><h2 class="ast-insp__title">${icon('chart')}运行详情</h2>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm" data-action="assistant.toggleInsp" aria-label="关闭">${icon('x')}</button></header>`;
  if (!run) return html`${head}<p class="ast-insp__empty">发一条消息后，这里显示每一轮模型请求与工具调用的耗时、token 用量和写入。</p>`;
  const now = runNow(run, perfNow);
  const live = run.status !== 'done';
  const u = run.usage;
  const totals = run.usageTotals || {};
  const main = totals.main || { input: u.prompt, output: u.out, total: u.prompt + u.out, complete: false, count: 0 };
  const aux = totals.aux || { input: 0, output: 0, total: 0, count: 0 };
  const all = totals.all || { total: main.total, complete: false };
  const cache = totals.cache || { ratio: null, covered: 0, total: 0 };
  const ttft = run.ttfts.length ? run.ttfts.reduce((a, b) => a + b, 0) / run.ttfts.length : 0;
  const lim = run.limits || S.status?.limits || { rounds: 25, calls: 40, writes: 20 };
  const separateWrites = run.steps.filter(step => step.kind === 'tool' && step.wrote && !step.commits?.length);
  const budget = (label, v, max) => html`<div class="ast-budget__r"><span>${label}</span>${bar(v / max, v / max > 0.8)}<b>${v} / ${max}</b></div>`;
  return html`${head}<div class="ast-insp__body">
    <p class="ast-runmeta">${hms(run.startedAt)} · ${run.model} · ${live ? (run.status === 'waiting' ? '等你确认' : '运行中') : REASON[run.reason] || run.reason}${run.reverted ? ' · 已撤销' : ''}</p>
    <section class="ast-sec"><h3 class="ast-sec__h">用量</h3><div class="ast-usage">
      ${usage('主对话输入', fmtN(main.input), `${main.count} 次请求`)}${usage('主对话输出', fmtN(main.output), u.think ? `含思考 ${fmtK(u.think)}` : '')}
      ${usage('图片辅助', aux.count ? fmtN(aux.total) : '无调用', aux.count ? `${aux.count} 次 · ${fmtN(aux.input)} 入 / ${fmtN(aux.output)} 出` : '')}
      ${usage(all.complete ? '本次总量' : '已知总量', fmtN(all.total), all.complete ? '输入 + 输出' : '部分或估算；未知未计入')}
      ${usage('主对话缓存', cache.ratio == null ? '未知/未返回' : `${Math.round(cache.ratio * 100)}%`, `${cache.covered} / ${cache.total} 次可统计${cache.complete ? '' : ' · 部分调用可统计'}`)}
      ${usage('首 token', fmtS(ttft), `${run.ttfts.length} 轮平均`)}${usage('速度', `${Math.round(live ? liveTps(run, now) : avgTps(run))} tok/s`, run.peak ? `峰值 ${Math.round(run.peak)}` : '')}</div>
      ${live ? spark(run, now) : ''}</section>
    <section class="ast-sec"><h3 class="ast-sec__h">时间线 <small>${fmtS(now)}</small></h3>${waterfall(run, now)}
      <ul class="ast-wf__legend"><li><i class="ast-wf__wait"></i>等首 token</li><li><i class="ast-wf__gen"></i>生成</li><li><i class="ast-wf__tool"></i>工具</li><li><i class="ast-wf__user"></i>等你确认</li></ul></section>
    <section class="ast-sec"><h3 class="ast-sec__h">预算</h3><div class="ast-budget">${budget('轮数', run.rounds, lim.rounds)}${budget('工具调用', run.calls, lim.calls)}${budget('写入', run.writes, lim.writes)}</div></section>
    <section class="ast-sec"><h3 class="ast-sec__h">写入 <small>${run.writes} 次，其中 ${run.commits.length} 条 commit</small></h3>
      ${run.commits.length ? html`<ul class="ast-commits">${run.commits.map(c => html`<li class="ast-commit">${lvl(c.level === 'confirm' ? 'confirm' : 'rev', c.level === 'confirm' ? '已确认' : '可撤销')}<code>${c.commit_id}</code><span>${c.message}</span></li>`)}</ul>` : ''}
      ${separateWrites.length ? html`<ul class="ast-commits">${separateWrites.map(step => html`<li class="ast-commit">${lvl(step.level, step.level === 'confirm' ? '已确认' : '已执行')}<span>${toolTitle(step)} · ${step.summary || '草稿或分类写入'}（不支持按运行自动撤销）</span></li>`)}</ul>` : ''}
      ${!run.writes ? html`<p class="ast-note">这次运行没有写入。</p>` : ''}
      ${run.reverted ? html`<p class="ast-note">已于 ${hms(run.reverted.at)} 撤销，另记 ${(run.reverted.commits || []).length} 条 commit。</p>` : ''}</section>
  </div>`;
}
