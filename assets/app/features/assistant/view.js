/**
 * 助手页视图：纯函数，输入页面状态 S 输出 html``；index.js 按区域 morph（rail / head / stream / dock / insp）。
 * 已结束的运行带 data-hash（运行 id + 版本），morph 整棵跳过，公式不重算。
 */
import { html, raw, each, cls } from '../../core/html.js';
import { icon } from '../../ui/icon.js';
import { renderMd, plainOf } from './md.js';
import { REASON, avgTps, ctxUsed, dayGroup, fmtK, fmtN, fmtS, hhmm, mmss, runNow } from './state.js';
import { LVL, gateOf, lvl, refOf, toolArgs, toolIcon, toolPreview, toolTitle } from './tools-view.js';
import { imageSrc } from './attachments.js';
import { operationId, reviewCard } from './review-cards.js';

export const SUGS = {
  plan: { label: '排今天的复习，8 道以内', icon: 'calendar', text: '帮我把今天要复习的题排出来，8 道以内。' },
  weak: { label: '最近哪块最弱？', icon: 'chart', text: '最近哪块最弱？' },
  period: { label: '找「周期」相关的题', icon: 'search', text: '找一下和「周期」有关的题' },
  label: { label: '低熟练度的题标「考前必看」', icon: 'tag', text: '把熟练度低于 30% 的题都标上「考前必看」' },
};

const STATUS = {
  args: ['生成参数', 'is-queued'], queued: ['排队', 'is-queued'], running: ['执行中', 'is-running'], waiting: ['等你确认', 'is-waiting'],
  done: ['完成', 'is-done'], error: ['出错', 'is-error'], denied: ['未允许', 'is-denied'], aborted: ['已中止', 'is-aborted'],
};

/* ── 左栏：对话列表 ── */
export function railView(S) {
  const groups = new Map();
  for (const c of S.convs) {
    const g = dayGroup(c.updated_at);
    if (!groups.has(g)) groups.set(g, []);
    groups.get(g).push(c);
  }
  const item = c => html`<li data-key="${c.id}"><button type="button" class="${cls('ast-conv', c.id === S.convId && 'is-active')}" data-action="assistant.openConv" data-arg="${c.id}" aria-current="${c.id === S.convId ? 'true' : 'false'}">
    <span class="ast-conv__t">${c.live ? html`<i class="ast-live-dot${c.live === 'waiting' ? ' is-waiting' : ''}" aria-label="${c.live === 'waiting' ? '等你确认' : '运行中'}"></i>` : ''}${c.title}</span>
    <span class="ast-conv__s">${plainOf(c.snippet) || '（还没有回复）'}</span>
    <span class="ast-conv__f"><span class="ast-conv__time">${hhmm(c.updated_at)}</span>${c.writes ? html`<span class="ui-tag ui-tag--info">写入 ${c.writes}</span>` : ''}${c.reverted ? html`<span class="ui-tag">有撤销</span>` : ''}</span>
  </button></li>`;
  return html`<header class="ast-rail__head"><h2 class="ast-rail__title">对话</h2>
    <button type="button" class="ui-btn ui-btn--sm" data-action="assistant.newConv">${icon('plus')}新对话</button></header>
    <div class="ast-rail__list">${S.convs.length ? each([...groups], ([g]) => g, ([g, list]) => html`<section class="ast-group" data-key="${g}"><h3>${g}</h3><ul>${each(list, c => c.id, item)}</ul></section>`)
      : html`<p class="ast-rail__empty">还没有对话。</p>`}</div>
    ${S.listMore ? html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="assistant.moreConversations"${S.listBusy ? html` disabled` : ''}>${S.listBusy ? '读取中…' : '更多对话'}</button>` : ''}<footer class="ast-rail__foot">对话存在 agent.db，随备份导出；不进 Ledger。</footer>`;
}

/* ── 头部 ── */
export function headView(S) {
  const st = S.status || {};
  const conv = S.convs.find(c => c.id === S.convId);
  return html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ast-rail-toggle" data-action="assistant.toggleRail" aria-label="对话列表">${icon('menu')}</button>
    <div class="ast-head__text"><h2 class="ast-head__title">${conv ? conv.title : 'AI 助手'}</h2>
      <p class="ast-head__meta">${st.model ? html`<span class="ast-model">${icon('sparkle')}${st.model}</span>` : ''}${st.faux ? html`<span class="ui-tag ui-tag--warning">假模型</span>` : ''}<span>${st.base_host || ''}</span></p></div>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="assistant.newConv" aria-label="新对话">${icon('plus')}<span class="ast-hide-sm">新对话</span></button>
    <button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ast-insp-toggle" data-action="assistant.toggleInsp" aria-label="运行详情" aria-pressed="${S.inspOpen ? 'true' : 'false'}">${icon('chart')}</button>`;
}

/* ── 对话流 ── */
function thinkView(S, run, st, now) {
  const key = `${run.id}|${st.id}`;
  const open = !S.closed.has(key);
  const secs = st.phase === 'done' || st.phase === 'cut' ? fmtS((st.t1 ?? now) - (st.tStart ?? st.t0)) : fmtS(now - (st.tStart ?? st.t0));
  const label = st.phase === 'wait' ? '等待首个 token' : st.phase === 'live' ? `思考中 ${secs}` : st.phase === 'cut' ? `思考被中止 · ${secs}` : `思考了 ${secs}`;
  return html`<div class="ast-node ast-node--dot" data-key="${st.id}"><div class="${cls('ast-think', st.phase === 'live' && 'is-live')}">
    <button type="button" class="ast-think__btn" data-action="assistant.toggleStep" data-arg="${key}" aria-expanded="${open ? 'true' : 'false'}" ${st.src ? '' : 'disabled'}>${icon(open ? 'chevron-down' : 'chevron-right')}<span>${label}</span></button>
    ${open && st.src ? html`<div class="ast-think__body">${st.src}</div>` : ''}</div></div>`;
}

function gateView(run, st, now) {
  const g = gateOf(st);
  const left = (st.ttl || 600000) - (now - (st.gateT0 || 0));
  const key = `${run.id}|${st.callId}`;
  return html`<div class="ast-gate" role="group" aria-label="需要你确认">
    <p class="ast-gate__what">${lvl('confirm')}${g.what}</p><div class="ast-gate__preview">${raw(renderMd(g.preview, { refOf }))}</div>
    <div class="ast-gate__bar"><span class="ast-gate__clock">${icon('clock')}${mmss(left)} 后过期</span>
      <button type="button" class="ui-btn ui-btn--sm ui-btn--primary" data-action="assistant.gate" data-arg="${key}">${icon('eye')}查看并决定</button></div>
    <p class="ast-gate__note">这是历史确认轨迹，当前决定与执行结果请在审核中心核对。</p></div>`;
}

function toolView(S, run, st, now) {
  const key = `${run.id}|${st.id}`;
  const open = S.open.has(key) || (['create_draft', 'update_draft', 'create_category', 'create_practice_card'].includes(st.name) && st.status === 'done' && !S.closed.has(key));
  const [label, tone] = STATUS[st.status] || STATUS.queued;
  const dur = st.status === 'running' ? fmtS(now - st.t0) : st.dur ? fmtS(st.dur) : '';
  const decided = st.decision && st.decision.how !== 'allow' ? '' : st.decision ? html`<span class="ast-tool__sum">你已允许</span>` : '';
  return html`<div class="${cls('ast-node ast-node--tool', tone)}" data-key="${st.id}"><div class="${cls('ast-tool', tone, open && 'is-open')}">
    <button type="button" class="ast-tool__head" data-action="assistant.toggleStep" data-arg="${key}" aria-expanded="${open ? 'true' : 'false'}" ${st.result || st.error ? '' : 'disabled'}>
      ${icon(toolIcon(st))}<span class="ast-tool__title">${toolTitle(st)}</span><span class="ast-tool__args">${toolArgs(st)}</span>
      <span class="ast-tool__right">${st.level !== 'read' ? lvl(st.level) : ''}${st.summary ? html`<span class="ast-tool__sum">${st.summary}</span>` : ''}${decided}
      <span class="${cls('ast-tool__st', tone)}">${label}</span>${dur ? html`<span class="ast-tool__meta">${dur}</span>` : ''}${st.result || st.error ? html`<span class="ast-tool__chev">${icon(open ? 'chevron-up' : 'chevron-down')}</span>` : ''}</span></button>
    ${operationId(st) ? reviewCard(S, run, st) : st.status === 'waiting' ? gateView(run, st, now) : ''}
    ${st.error && !open ? html`<p class="ast-note is-error">${st.error}</p>` : ''}
    ${open ? html`<div class="ast-tool__body">${toolPreview(st, S.drafts?.[st.result?.draft_id], S.draftCropMode)}${st.commits?.length ? html`<p class="ast-note">写入 ${st.commits.map(c => c.commit_id).join('、')}</p>` : ''}</div>` : ''}
  </div></div>`;
}

function imageView(st) {
  const label = st.status === 'running' ? `转述 ${st.ref}…` : st.status === 'error' ? `转述 ${st.ref} 失败` : `转述 ${st.ref} 完成`;
  return html`<div class="ast-node ast-node--dot"><div class="${cls('ast-image-step', `is-${st.status}`)}">${icon(st.status === 'error' ? 'alert-circle' : st.status === 'done' ? 'check-circle' : 'image')}${label}${st.ms ? html`<span>${st.ms} ms</span>` : ''}${st.error ? html`<span>${st.error}</span>` : ''}</div></div>`;
}

function stepView(S, run, st, now) {
  if (st.kind === 'think') return thinkView(S, run, st, now);
  if (st.kind === 'tool') return toolView(S, run, st, now);
  if (st.kind === 'image') return imageView(st);
  if (st.kind === 'steer') {
    const when = st.delivered > 0 ? `第 ${st.delivered} 轮前送达` : st.delivered < 0 ? '运行结束前没来得及送达，已留在对话里' : '排队中，下一轮前送达';
    return html`<div class="ast-node ast-node--dot" data-key="${st.id}"><div class="ast-user ast-user--steer"><span class="ast-user__m">${icon('message')}插话 · ${when}</span><div class="ast-user__b">${st.text}</div></div></div>`;
  }
  return html`<div class="ast-node ast-node--text" data-key="${st.id}"><div class="ast-md">${raw(renderMd(st.src, { live: st.live && run.status !== 'done', refOf }))}</div>${st.cut ? html`<p class="ast-cut">（输出被中止）</p>` : ''}</div>`;
}

function footView(run) {
  const tag = run.reason === 'completed' ? '' : html`<span class="${cls('ui-tag', run.reason === 'aborted' ? '' : 'ui-tag--danger')}">${REASON[run.reason] || run.reason}</span>`;
  const writes = run.commits.length;
  return html`<div class="ast-foot">${tag}${run.error ? html`<span class="ast-foot__st is-error">${run.error}</span>` : ''}
    <span class="ast-foot__st">${fmtS(run.dur)} · ${run.rounds} 轮 · ${run.calls} 次调用${run.writes ? ` · 写入 ${run.writes}` : ''} · ${run.usageTotals?.main?.complete ? '主对话' : '主对话已知/估算'} ${fmtK(run.usage.prompt)} 入 / ${fmtK(run.usage.out)} 出</span>
    <span class="ast-foot__acts">${run.reverted ? html`<span class="ui-tag">${icon('undo')}已撤销</span>`
      : writes ? html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="assistant.undo" data-arg="${run.id}">${icon('undo')}撤销这次写入</button>` : ''}
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="assistant.copy" data-arg="${run.id}" aria-label="复制回答">${icon('copy')}</button>
      <button type="button" class="ui-btn ui-btn--ghost ui-btn--sm ui-btn--icon" data-action="assistant.selectRun" data-arg="${run.id}" aria-label="查看运行详情">${icon('chart')}</button></span></div>`;
}

export function turnView(S, run, perfNow) {
  const live = run.status !== 'done';
  const now = runNow(run, perfNow);
  const collapsed = !live && S.traceClosed?.has(run.id);
  const answer = [...run.steps].reverse().find(st => st.kind === 'text');
  // 回答、插话和需要用户操作的结果始终可见，不随处理过程收起。
  const outside = run.steps.filter(st => st === answer || st.kind === 'steer'
    || st.kind === 'tool' && (st.level !== 'read' || st.wrote || ['waiting', 'error', 'denied'].includes(st.status)));
  const process = run.steps.filter(st => !outside.includes(st));
  const label = live ? '处理中' : run.reason === 'aborted' ? '处理已停止'
    : run.error || run.reason && run.reason !== 'completed' ? '处理已结束' : '处理完成';
  const detail = live && run.status === 'waiting' ? '等你确认' : live && run.aborting ? '正在中止…' : fmtS(live ? now : run.dur);
  const body = html`<header class="ast-turn__head"><span class="ast-turn__who">${icon('sparkle')}助手</span><span class="ast-turn__model">${run.model}</span>
      <span class="ast-turn__time">${hhmm(run.startedAt)}</span></header>
    <section class="ast-process" data-key="process"><button type="button" class="ast-process__toggle" data-action="assistant.toggleTrace" data-arg="${run.id}" aria-expanded="${collapsed ? 'false' : 'true'}" aria-controls="process-${run.id}" ${live ? 'disabled' : ''}>
      <span class="ast-process__label" role="status">${label}</span><span class="ast-process__meta">${detail}</span>${icon(collapsed ? 'chevron-right' : 'chevron-down')}</button>
      ${collapsed ? '' : html`<div class="ast-trace" id="process-${run.id}" data-key="process-body">${each(process, st => st.id, st => stepView(S, run, st, now))}</div>`}</section>
    <div class="ast-result" data-key="result">${each(outside, st => st.id, st => stepView(S, run, st, now))}</div>
    ${run.eventsMore ? html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="assistant.loadRunEvents" data-arg="${run.id}"${run.eventsBusy || run.following ? html` disabled` : ''}>${run.eventsBusy ? '读取中…' : '继续读取运行记录'}</button><p class="ast-note">这次运行的记录尚未全部读取。</p>` : ''}
    ${live ? '' : footView(run)}`;
  return html`<article class="${cls('ast-turn', live && 'is-live', run.reverted && 'is-undone', S.runSel === run.id && 'is-selected')}" data-key="run-${run.id}" ${live ? '' : raw(`data-hash="${run.id}:${run.ver}:${S.uiVer}:${S.draftVer || 0}:${S.reviewVer || 0}:${S.runSel === run.id ? 1 : 0}"`)}>${body}</article>`;
}

export function userView(item, i, S = {}) {
  const images = item.images || [];
  const long = item.text?.length > 360;
  const expanded = S.longOpen?.has(String(i));
  return html`<div class="ast-user" data-key="u-${i}" data-hash="u${i}:${item.text?.length || 0}:${images.map(image => image.sha || image.ref).join(',')}:${expanded ? 1 : 0}"><span class="ast-user__m">你 · ${hhmm(item.at)}</span>
    ${images.length ? html`<div class="ast-user__images">${images.map((image, n) => html`<button type="button" class="ast-image" data-action="assistant.openSentImage" data-arg="${i}|${n}" aria-label="预览 ${image.ref || `IMG-${n + 1}`}"><img src="${imageSrc(image)}" alt="${image.ref || `IMG-${n + 1}`}" loading="lazy"><span>${image.ref || `IMG-${n + 1}`}</span></button>`)}</div>` : ''}
    ${item.text ? html`<div class="ast-user__b${long && !expanded ? ' is-clamped' : ''}">${item.text}</div>${long ? html`<button type="button" class="ast-user__expand" data-action="assistant.toggleLong" data-arg="${i}" aria-expanded="${expanded ? 'true' : 'false'}">${expanded ? '收起' : '展开全文'}</button>` : ''}` : ''}</div>`;
}

export function streamView(S, perfNow) {
  if (!S.status?.enabled) return offView(S);
  if (!S.items.length) return emptyView(S);
  return html`${S.historyMore ? html`<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="assistant.loadHistory"${S.historyBusy ? html` disabled` : ''}>${S.historyBusy ? '读取中…' : '加载更早的消息'}</button>` : ''}${each(S.items, (it, i) => it.item_key || (it.type === 'user' ? `u-${i}` : `run-${it.run.id}`),
    (it, i) => (it.type === 'user' ? userView(it, it.item_key || i, S) : turnView(S, it.run, perfNow)))}`;
}

function offView(S) {
  const st = S.status || {};
  return html`<div class="ast-empty" data-key="off"><div class="ast-empty__mark">${icon('sparkle')}</div><h3>AI 助手还没启用</h3>
    <p>${st.enabled === false ? '在「设置 → AI 助手」里打开开关，填好模型服务的地址、密钥和模型名。' : '正在读取助手状态…'}</p>
    <a class="ui-btn ui-btn--primary" href="#/settings">${icon('sliders')}去设置</a></div>`;
}

const PERMS = [
  ['read', '找题、读题、看统计与复习推荐', '直接执行'],
  ['rev', '录入或修订 AI 草稿、创建聊天练习卡；草稿不进题库', '直接执行并留记录'],
  ['confirm', '安排正式复习、改题目与标记、移动或停用题目、记反馈、建分类、草稿入库', '审核中心批准后执行'],
  ['none', '删除题目、修改设置与 PIN、备份恢复、重启服务', '不支持'],
];
export function emptyView(S) {
  const st = S.status || {};
  return html`<div class="ast-empty ast-welcome" data-key="empty"><div class="ast-welcome__intro"><div class="ast-empty__mark">${icon('sparkle')}</div>
    <h3>从一道题，开始聊起</h3><p>找题、梳理薄弱点，或发张图片一起整理。</p></div>
    ${st.configured === false ? html`<p class="ast-welcome__warning">还没配置好：缺 ${(st.missing || []).join('、')}。</p>` : ''}
    <div class="ast-perm" aria-label="助手的能力与权限">${PERMS.map(([k, what, how]) => html`<div class="ast-perm__row"><div class="ast-perm__head">${lvl(k)}<span class="ast-perm__how">${how}</span></div><p class="ast-perm__what">${what}</p></div>`)}</div></div>`;
}

/* ── 底部：建议、输入框、用量计 ── */
export function dockView(S, perfNow) {
  const st = S.status || {};
  const run = S.liveRun;
  const busy = !!run && run.status !== 'done';
  const win = st.context_window || 65536;
  const used = ctxUsed(run || S.lastRun) || 0;
  const ratio = Math.min(1, used / win);
  const cache = (run || S.lastRun)?.usageTotals?.cache;
  const cacheLabel = cache?.ratio == null ? '缓存未知' : `缓存 ${Math.round(cache.ratio * 100)}%${cache.complete ? '' : '（部分）'}`;
  const meterLabel = `上下文占用 ${Math.round(ratio * 100)}%，${cacheLabel}，查看用量`;
  const circ = 2 * Math.PI * 9;
  const sugs = !busy && !S.composing && !S.inputActive && !S.inputValue && !(S.items || []).length && st.enabled ? Object.entries(S.sugs) : [];
  const disabled = !st.enabled || !st.configured;
  return html`${sugs.length ? html`<div class="ast-sugs" data-key="sugs">${sugs.map(([k, s]) => html`<button type="button" class="ast-sug" data-action="assistant.sug" data-arg="${k}">${icon(s.icon)}${s.label}</button>`)}</div>` : ''}
    <div class="${cls('ast-composer', busy && 'is-busy')}" data-key="composer">
      ${S.attachments.length || S.pendingFiles ? html`<div class="ast-attachments" aria-label="待发送图片">${S.attachments.map((image, i) => html`<div class="ast-attachment" data-key="attachment-${i}"><button type="button" class="ast-attachment__preview" data-action="assistant.openImage" data-arg="${i}" aria-label="查看待发送图片 ${i + 1} 大图"><img src="${image.dataUrl}" alt="待发送图片 ${i + 1}"></button><span>图片 ${i + 1}</span><button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm ast-attachment__remove" data-action="assistant.removeImage" data-arg="${i}" aria-label="删除图片 ${i + 1}">${icon('x')}</button></div>`)}${S.pendingFiles ? html`<span class="ast-attachment__pending" role="status">正在处理 ${S.pendingFiles} 张图片…</span>` : ''}<button type="button" class="ui-btn ui-btn--ghost ui-btn--sm" data-action="assistant.clearImages">清空</button></div>` : ''}
      <textarea id="ast-input" class="ast-input" rows="1" maxlength="4000" placeholder="${busy ? '插话：下一轮模型请求前送达' : '问点什么'}" aria-label="给助手的消息" ${disabled ? 'disabled' : ''}></textarea>
      <div class="ast-cbar">
        <input id="ast-image-picker" type="file" accept="image/png,image/jpeg,image/gif" multiple hidden data-change="assistant.pickImages">
        <button type="button" class="ui-btn ui-btn--ghost ui-btn--icon ui-btn--sm" data-action="assistant.pickImages" aria-label="添加图片" title="添加图片" ${disabled ? 'disabled' : ''}>${icon('paperclip')}</button>
        <button type="button" class="ast-meter" data-action="assistant.pop" aria-expanded="${S.popOpen ? 'true' : 'false'}" aria-label="${meterLabel}">
          <svg class="${cls('ast-ring', ratio > 0.8 && 'is-warn')}" viewBox="0 0 24 24" aria-hidden="true"><circle class="t" cx="12" cy="12" r="9"/><circle class="v" cx="12" cy="12" r="9" stroke-dasharray="${(circ * ratio).toFixed(1)} ${circ.toFixed(1)}" transform="rotate(-90 12 12)"/></svg>
          <span class="ast-meter__context">${fmtK(used)} / ${fmtK(win)}</span><span class="ast-meter__cache">${cacheLabel}</span></button>
        <span class="ast-cbar__sp">${busy ? html`<span class="ast-model">${fmtS(runNow(run, perfNow))} · ${Math.round(avgTps(run))} tok/s</span>` : `${S.msgs} / ${st.msg_cap || 60} 条消息`}</span>
        ${busy ? html`<button type="button" class="ui-btn ui-btn--sm ast-stop" data-action="assistant.stop">${icon('stop')}停止</button>` : ''}
        <button type="button" class="ui-btn ui-btn--primary ui-btn--sm ui-btn--icon ast-send" data-action="assistant.send" aria-label="${busy ? '插话' : '发送'}" ${disabled || S.pendingFiles ? 'disabled' : ''}>${icon('arrow-up')}</button>
      </div>
      ${S.popOpen ? popView(S, run || S.lastRun, used, win) : ''}
    </div>`;
}

function popView(S, run, used, win) {
  const c = run?.ctx || { sys: 0, tools: 0, chat: 0, res: 0 };
  const cache = run?.usageTotals?.cache;
  const parts = [['sys', '系统提示', c.sys], ['tools', '工具定义', c.tools], ['chat', '对话', c.chat], ['res', '工具结果', c.res]];
  const total = parts.reduce((a, p) => a + p[2], 0) || 1;
  let x = 0;
  const rects = parts.map(([k, , v]) => { const w = (v / total) * 100; const r = `<rect class="c-${k}" x="${x.toFixed(2)}" width="${w.toFixed(2)}" height="6"/>`; x += w; return r; }).join('');
  const lim = S.status?.limits || {};
  return html`<div class="ast-pop" role="dialog" aria-label="上下文与缓存">
    <section class="ast-pop__section"><h4 class="ast-pop__h">上下文 <span>${fmtN(used)} / ${fmtN(win)}</span></h4>
      <p class="ast-pop__note">最近请求 · tokens</p>
      ${raw(`<svg class="ast-stack" viewBox="0 0 100 6" preserveAspectRatio="none" aria-hidden="true">${rects}</svg>`)}
      <ul class="ast-legend">${parts.map(([k, label, v]) => html`<li><i class="c-${k}"></i>${label}<b>${fmtK(v)}</b></li>`)}</ul></section>
    <section class="ast-pop__section"><h4 class="ast-pop__h">缓存命中 <span>${cache?.ratio == null ? '未知/未返回' : `${Math.round(cache.ratio * 100)}%`}</span></h4>
      <p class="ast-pop__note">本次主对话 · ${cache?.ratio == null ? '供应商未返回可统计的缓存用量' : `${fmtN(cache.read)} / ${fmtN(cache.input)} 输入 tokens`}；${cache?.covered || 0} / ${cache?.total || 0} 次调用可统计${cache?.complete ? '' : '（部分调用可统计）'}。</p></section>
    <p class="ast-pop__note">${S.msgs} / ${S.status?.msg_cap || 60} 条消息 · 每次最多 ${lim.rounds || 25} 轮、${lim.calls || 40} 次调用、${lim.writes || 20} 次写入。</p></div>`;

}

export { LVL };
