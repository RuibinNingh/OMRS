// AI 助手页（features/assistant）的纯函数：事件归约成运行视图模型、持久化后合并过的事件重放、聊天 Markdown。
import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, newRun, runFrom, ctxUsed, dayGroup, tokOf, fmtS, REASON } from '../../assets/app/features/assistant/state.js';
import { renderMd, renderInline, plainOf } from '../../assets/app/features/assistant/md.js';
import { dockView, userView, turnView } from '../../assets/app/features/assistant/view.js';
import { inspView } from '../../assets/app/features/assistant/insp-view.js';
import { confirmOf, toolPreview } from '../../assets/app/features/assistant/tools-view.js';
import { detectCardState } from '../../assets/app/features/assistant/draft-cards.js';
import { normalizeJpegBytes } from '../../assets/app/features/assistant/attachments.js';
import { usageRecord, usageTotals } from '../../assets/app/features/assistant/usage.js';

test('两轮缓存按输入加权，显式零和缺失分开，总量不重复加子集', () => {
  const events = [
    { i: 0, t: 0, type: 'round.start', data: { n: 1 } },
    { i: 1, t: 1, type: 'round.end', data: { n: 1, usage: { input_total: 1000, output_total: 200, cache_read: 0 } } },
    { i: 2, t: 2, type: 'round.start', data: { n: 2 } },
    { i: 3, t: 3, type: 'round.end', data: { n: 2, usage: { input_total: 9000, output_total: 300, cache_read: 9000, reasoning_output: 100 } } },
  ];
  const run = runFrom({ id: 'usage' }, events);
  assert.equal(run.usageTotals.main.total, 10500);
  assert.equal(run.usageTotals.cache.ratio, 0.9);
  assert.equal(run.usageTotals.cache.complete, true);
  assert.equal(run.usageTotals.all.total, 10500);
  applyEvent(run, events[3]);
  applyEvent(run, { ...events[3], i: 4 });
  assert.equal(run.usageTotals.main.total, 10500);
  assert.equal(runFrom({ id: 'replay' }, events).usageTotals.cache.ratio, 0.9);
});

test('缺缓存、中断、completion=0 和辅助请求保留统计边界', () => {
  const run = newRun({ id: 'partial' });
  applyEvent(run, { i: 1, type: 'round.start', data: { n: 1 } });
  applyEvent(run, { i: 2, type: 'delta', data: { n: 1, kind: 'text', text: '暂存' } });
  assert.equal(run.usageTotals.main.complete, false);
  applyEvent(run, { i: 3, type: 'round.end', data: { n: 1, usage: { prompt: 10, completion: 0 } } });
  assert.equal(run.usage.out, 0);
  assert.equal(run.usageTotals.cache.ratio, null);
  assert.equal(run.usageTotals.main.complete, true);
  applyEvent(run, { i: 4, type: 'usage.aux', data: { request_id: 'r:describe:c', usage: { input_total: 5, output_total: 2,
    cache_read: null, reasoning_output: null, scope: 'aux' } } });
  assert.equal(run.usageTotals.aux.total, 7);
  assert.equal(run.usageTotals.all.total, 17);
  assert.equal(usageRecord({ prompt: 10, completion: 2 }).cache, null);
  assert.equal(usageRecord({ prompt: 10, completion: 2, cached: 0 }).cache, null);
  assert.equal(usageRecord({ input_total: 10, output_total: 2, cache_read: 0 }).cache, 0);
  assert.equal(usageRecord({}).source, 'missing');
  const interrupted = newRun({ id: 'old' });
  applyEvent(interrupted, { i: 1, type: 'round.start', data: { n: 1, context: { sys: 100, tools: 20, chat: 30, res: 0 } } });
  applyEvent(interrupted, { i: 2, type: 'round.end', data: { n: 1, usage: {} } });
  assert.equal(interrupted.usageTotals.main.input, 150);
  assert.equal(interrupted.usageTotals.main.complete, false);
  assert.equal(interrupted.usageRequests.get('round:1').source, 'estimated');
  assert.equal(usageTotals(new Map([['x', usageRecord({ input_total: null, output_total: 2, estimated: true })]])).all.complete, false);
});

test('手机 JPEG：保留编码像素，跳过缩略图标记，清除相册尾数据或补主图结束标记', () => {
  const body = Uint8Array.from([0xff, 0xd8, 0xff, 0xe1, 0, 6, 0xff, 0xd9, 1, 2,
    0xff, 0xda, 0, 8, 1, 1, 0, 0, 63, 0, 10, 20, 0xff, 0, 30, 0xff, 0xd0, 40]);
  const complete = Uint8Array.from([...body, 0xff, 0xd9]);
  assert.deepEqual(normalizeJpegBytes(body), complete);
  assert.deepEqual(normalizeJpegBytes(Uint8Array.from([...body, 0xff])), complete);
  assert.deepEqual(normalizeJpegBytes(Uint8Array.from([...complete, 97, 108, 98, 117, 109, 33])), complete);
  assert.strictEqual(normalizeJpegBytes(complete), complete);
  const brokenHeader = Uint8Array.from([0xff, 0xd8, 0xff, 0xe1, 0, 16, 1]);
  assert.strictEqual(normalizeJpegBytes(brokenHeader), brokenHeader);
});

const ev = (i, t, type, data = {}) => ({ i, t, type, data });
const script = [
  ev(0, 0, 'run.start', { model: 'm', limits: { rounds: 25, calls: 40, writes: 20 }, context_window: 65536 }),
  ev(1, 5, 'round.start', { n: 1, context: { sys: 900, tools: 1500, chat: 20, res: 0 } }),
  ev(2, 400, 'delta', { n: 1, kind: 'think', text: '先看推荐' }),
  ev(3, 500, 'delta', { n: 1, kind: 'args', index: 0, name: 'get_recommendations', text: '{"count":8}' }),
  ev(4, 520, 'delta', { n: 1, kind: 'args', index: 1, name: 'update_question_section', text: '{"uid":"三角函数1"}' }),
  ev(5, 600, 'round.end', { n: 1, finish: 'tool_calls', usage: { prompt: 2400, completion: 30, cached: 1024 }, ttft_ms: 395, gen_ms: 200 }),
  ev(6, 601, 'tool.call', { n: 1, call_id: 'a', name: 'get_recommendations', args: { count: 8 }, level: 'read' }),
  ev(7, 602, 'tool.call', { n: 1, call_id: 'b', name: 'update_question_section', args: { uid: '三角函数1', section: '错因', content: 'x' }, level: 'confirm' }),
  ev(8, 610, 'tool.running', { call_id: 'a' }),
  ev(9, 640, 'tool.end', { call_id: 'a', status: 'done', summary: '到期 8', result: { due: [], proficiency: [] }, dur_ms: 30 }),
  ev(10, 650, 'tool.waiting', { call_id: 'b', token: 'tok', ttl_ms: 600000, preview: { before: '', after: 'x' } }),
  ev(11, 700, 'steer.queued', { id: 's1', text: '顺便看看数列' }),
  ev(12, 3000, 'tool.decision', { call_id: 'b', how: 'allow' }),
  ev(13, 3001, 'tool.running', { call_id: 'b' }),
  ev(14, 3050, 'tool.end', { call_id: 'b', status: 'done', summary: '已写入', result: { ok: true }, commits: [{ commit_id: 'CMT-000061', seq: 61, message: 'AI 修改' }] }),
  ev(15, 3060, 'steer.delivered', { id: 's1', round: 2 }),
  ev(16, 3070, 'round.start', { n: 2, context: { sys: 900, tools: 1500, chat: 60, res: 400 } }),
  ev(17, 3500, 'delta', { n: 2, kind: 'text', text: '排好了 `三角函数1`' }),
  ev(18, 3600, 'round.end', { n: 2, finish: 'stop', usage: { prompt: 2900, completion: 12 }, ttft_ms: 430, gen_ms: 100 }),
  ev(19, 3610, 'run.end', { reason: 'completed', error: '' }),
];

test('事件归约：思考、参数、确认、插话、写入与结束', () => {
  const run = runFrom({ id: 'r1', status: 'done', reason: 'completed' }, script);
  assert.equal(run.status, 'done');
  assert.equal(run.reason, 'completed');
  assert.equal(run.rounds, 2);
  assert.equal(run.calls, 2);
  assert.equal(run.writes, 1);
  assert.deepEqual(run.commits.map(c => c.commit_id), ['CMT-000061']);
  assert.deepEqual(run.steps.map(s => s.kind), ['think', 'tool', 'tool', 'steer', 'text']);
  const gate = run.steps[2];
  assert.equal(gate.status, 'done');
  assert.equal(gate.decision.how, 'allow');
  assert.equal(gate.level, 'confirm');
  assert.equal(run.steps[3].delivered, 2);
  assert.equal(run.usage.prompt, 5300);
  assert.equal(run.usage.cached, 1024);
  assert.equal(run.ttfts.length, 2);
  const seg = run.timeline.find(s => s.kind === 'tool' && s.w0 != null);
  assert.equal(seg.w1, 3000);
  assert.equal(ctxUsed(run), 2900);
});

test('无 Ledger commit 的分类与草稿写入仍显示真实预算和活动', () => {
  const events = [
    ev(0, 0, 'run.start', { model: 'faux', limits: { rounds: 25, calls: 40, writes: 20 } }),
    ev(1, 5, 'round.start', { n: 1, context: { sys: 0, tools: 0, chat: 0, res: 0 } }),
    ev(2, 10, 'tool.call', { call_id: 'category', name: 'create_category', args: { subject: '数学', category: '矩阵' }, level: 'confirm' }),
    ev(3, 20, 'tool.end', { call_id: 'category', status: 'done', result: { subject: '数学', category: '矩阵', created: true }, wrote: true, commits: [] }),
    ev(4, 30, 'tool.call', { call_id: 'draft', name: 'update_draft', args: { draft_id: 'DR-1', expected_revision: 1 }, level: 'rev' }),
    ev(5, 40, 'tool.end', { call_id: 'draft', status: 'done', result: { draft_id: 'DR-1', revision: 2, wrote: true }, wrote: true, commits: [] }),
    ev(6, 50, 'run.end', { reason: 'completed' }),
  ];
  const run = runFrom({ id: 'p4', status: 'done', reason: 'completed' }, events);
  assert.equal(run.writes, 2);
  assert.equal(run.commits.length, 0);
  const S = { items: [{ run }], lastRun: run, runSel: run.id, open: new Set(), closed: new Set(), drafts: {}, draftCropMode: 'manual', uiVer: 0, draftVer: 0, status: { limits: { rounds: 25, calls: 40, writes: 20 } } };
  assert.match(String(turnView(S, run, 0)), /写入 2/);
  assert.doesNotMatch(String(turnView(S, run, 0)), /撤销这次写入/);
  const inspector = String(inspView(S, 0));
  assert.match(inspector, /2 次，其中 0 条 commit/);
  assert.match(inspector, /创建分类/);
  assert.match(inspector, /修改 AI 草稿/);
  assert.doesNotMatch(inspector, /这次运行没有写入/);
});

test('人工保护的草稿建议卡保留目标与前后内容', () => {
  const card = String(toolPreview({ name: 'update_draft', args: { draft_id: 'DR-1', expected_revision: 3 },
    result: { draft_id: 'DR-1', revision: 3, wrote: false, suggestions: [
      { target: 'block:blk-1', before: { text: '人工解法', note: '' }, after: { text: 'AI 解法', note: '' } },
      { target: 'field:category', before: '函数', after: '矩阵' },
    ] } }));
  for (const value of ['blk-1', '人工解法', 'AI 解法', '函数', '矩阵', 'assistant.openDraft']) assert.match(card, new RegExp(value));
});

test('中止：未完成的步骤标为已中止，空思考被移除', () => {
  const run = newRun({ id: 'r2' });
  applyEvent(run, ev(0, 0, 'round.start', { n: 1, context: {} }));
  applyEvent(run, ev(1, 10, 'delta', { n: 1, kind: 'args', index: 0, name: 'search_questions', text: '{"key' }));
  applyEvent(run, ev(2, 20, 'run.end', { reason: 'aborted' }));
  assert.deepEqual(run.steps.map(s => [s.kind, s.status]), [['tool', 'aborted']]);
  assert.equal(REASON[run.reason], '已中止');
});

test('持久化后合并的增量与逐片增量重放结果一致', () => {
  const pieces = newRun({ id: 'a' });
  const merged = newRun({ id: 'b' });
  applyEvent(pieces, ev(0, 0, 'round.start', { n: 1 }));
  applyEvent(merged, ev(0, 0, 'round.start', { n: 1 }));
  ['排', '好了', '。'].forEach((t, i) => applyEvent(pieces, ev(i + 1, 10 + i, 'delta', { n: 1, kind: 'text', text: t })));
  applyEvent(merged, ev(1, 10, 'delta', { n: 1, kind: 'text', text: '排好了。' }));
  assert.equal(pieces.steps.at(-1).src, merged.steps.at(-1).src);
});

test('格式化与分组', () => {
  assert.equal(fmtS(820), '0.82s');
  assert.equal(fmtS(61000), '1m01s');
  assert.ok(tokOf('周期') > tokOf('ab'));
  const now = new Date('2026-09-28T12:00:00');
  assert.equal(dayGroup('2026-09-28T01:00:00', now), '今天');
  assert.equal(dayGroup('2026-09-27T23:00:00', now), '昨天');
  assert.equal(dayGroup('2026-09-20T23:00:00', now), '更早');
});

test('聊天 Markdown：引用芯片、表格、列表、转义与光标', () => {
  const refOf = c => `<b data-ref="${c}"></b>`;
  const out = renderMd('找到 `函数1`，**两道**。\n\n| 指标 | 数量 |\n|---|---|\n| 逾期 | 3 |\n\n- a\n- <x>', { refOf, live: true });
  assert.match(out, /data-ref="函数1"/);
  assert.match(out, /<strong>两道<\/strong>/);
  assert.match(out, /<th>指标<\/th>/);
  assert.match(out, /<li>&lt;x&gt;<span class="ast-caret"/);
  assert.doesNotMatch(renderInline('<script>'), /<script>/);
  assert.equal(plainOf('| a |\n周期是 $\\pi$，**好**'), '周期是 pi，好');
});

test('转述事件先于模型轮次，完成和失败状态可重放', () => {
  const events = [ev(0, 0, 'run.start'), ev(1, 10, 'image.transcribe', { ref: 'IMG-1', sha: 'a' }),
    ev(2, 110, 'image.transcribed', { ref: 'IMG-1', ok: true, ms: 100 }),
    ev(3, 120, 'image.transcribe', { ref: 'IMG-2', sha: 'b' }),
    ev(4, 130, 'image.transcribed', { ref: 'IMG-2', ok: false, ms: 10, error: '模型失败' }),
    ev(5, 140, 'round.start', { n: 1 }), ev(6, 150, 'run.end', { reason: 'completed' })];
  const run = runFrom({ id: 'r-image', status: 'done' }, events);
  assert.deepEqual(run.steps.map(s => s.kind), ['image', 'image']);
  assert.deepEqual(run.steps.map(s => s.status), ['done', 'error']);
  assert.equal(run.steps[1].error, '模型失败');
});

test('附图输入与草稿结果显示图片编号、删除入口和草稿状态', () => {
  const state = { status: { enabled: true, configured: true, limits: {} }, convId: 'c', msgs: 0,
    sugs: {}, attachments: [{ dataUrl: 'data:image/png;base64,AAAA' }], liveRun: null, lastRun: null, popOpen: false };
  const dock = String(dockView(state, 0));
  assert.match(dock, /data-action="assistant\.pickImages"/);
  assert.match(dock, /data-action="assistant\.removeImage"/);
  const user = String(userView({ text: '录一下', at: '2026-09-28T10:00:00Z', images: [{ ref: 'IMG-3', sha: 'a'.repeat(64) }] }, 0));
  assert.match(user, /IMG-3/);
  assert.match(user, /\/api\/drafts\/image\?sha=/);
  const card = String(toolPreview({ name: 'create_draft', result: { draft_id: 'DR-1', status: 'cropping', subject: '数学', category: '函数',
    question_preview: '求最小值', blocks: [{ section: '题目', kind: 'text' }, { section: '答案', kind: 'image' }] } }));
  assert.match(card, /DR-1/);
  assert.match(card, /正在获取当前状态/);
  assert.match(card, /答案 · 图片/);
  assert.match(card, /assistant.openDraft/);
  const changed = String(toolPreview({ name: 'create_draft', result: { draft_id: 'DR-1', status: 'cropping', subject: '数学', category: '函数', blocks: [] } },
    { draft: { id: 'DR-1', status: 'done', subject: '数学', category: '函数', blocks: [{ section: '题目', kind: 'text', text: '已入库' }] } }));
  assert.match(changed, /已入库/);
  assert.match(changed, /已入库.*查看草稿/s);
});

test('长用户消息保留原文，长查询轨迹默认折叠且可展开', () => {
  const text = '完整消息'.repeat(100);
  const state = { longOpen: new Set(), traceOpen: new Set(), open: new Set(), closed: new Set(), drafts: {}, runSel: null, uiVer: 0 };
  const user = String(userView({ text, at: '2026-09-29T10:00:00Z', images: [] }, 0, state));
  assert.match(user, /展开全文/);
  assert.match(user, /完整消息/);
  const run = newRun({ id: 'r-1', status: 'done' });
  run.steps = Array.from({ length: 4 }, (_, index) => ({ kind: 'tool', id: `t-${index}`, name: 'search_questions', level: 'read', status: 'done', result: {} }));
  run.steps.push({ kind: 'text', id: 'answer', src: '最终回答', live: false });
  const compact = String(turnView(state, run, 0));
  assert.match(compact, /展开 4 项查询轨迹/);
  assert.match(compact, /最终回答/);
  state.traceOpen.add(run.id);
  assert.match(String(turnView(state, run, 0)), /收起查询轨迹/);
});

test('入库确认展示当前版本的正文、来源图与错因', () => {
  const review = confirmOf({ name: 'commit_draft', args: { draft_id: 'DR-1', revision: 4 },
    preview: { draft_id: 'DR-1', revision: 4, subject: '数学', category: '函数', difficulty: 5,
      cause: '计算失误', source_images: [{ sha256: 'a'.repeat(64) }],
      blocks: [{ section: '题目', kind: 'text', text: '求最小值' },
        { section: '答案', kind: 'image', image_sha: 'a'.repeat(64) }] } });
  const body = String(review.body);
  assert.match(body, /求最小值/);
  assert.match(body, /计算失误/);
  assert.match(body, /来源截图/);
  assert.match(body, /\/api\/drafts\/image\?sha=/);
  assert.match(review.hint, /第 4 版/);
});

test('待框选卡片仅在询问模式提供我来框', () => {
  const step = { name: 'create_draft', result: { draft_id: 'DR-ask', subject: '数学', category: '函数', blocks: [] } };
  const current = { draft: { id: 'DR-ask', status: 'cropping', subject: '数学', category: '函数', blocks: [] } };
  assert.match(String(toolPreview(step, current, 'ask')), /我来框/);
  assert.match(String(toolPreview(step, current, 'ask')), /data-action="assistant\.detectDraft"[^>]*>AI 框/);
  assert.doesNotMatch(String(toolPreview(step, current, 'manual')), /我来框/);
  assert.doesNotMatch(String(toolPreview(step, current, 'manual')), /assistant\.detectDraft/);
  assert.doesNotMatch(String(toolPreview(step, current, 'auto')), /我来框/);
  assert.doesNotMatch(String(toolPreview(step, current, 'auto')), /assistant\.detectDraft/);
  assert.doesNotMatch(String(toolPreview(step, { draft: { ...current.draft, status: 'done' } }, 'ask')), /我来框/);
});

test('草稿卡片展示自动框选作业与可重试状态，不显示图片 SHA', () => {
  const sha = 'a'.repeat(64);
  const step = { name: 'create_draft', result: { draft_id: 'DR-auto', subject: '数学', category: '函数', blocks: [] } };
  const draft = { id: 'DR-auto', status: 'cropping', subject: '数学', category: '函数', blocks: [] };
  const running = { ...draft, jobs: [{ type: 'detect', status: 'running', processed: 1, total: 2 }] };
  assert.equal(detectCardState(running).phase, 'busy');
  const busy = String(toolPreview(step, { draft: running }, 'auto'));
  assert.match(busy, /AI 正在框选（1\/2 张）/);
  assert.doesNotMatch(busy, /assistant\.detectDraft/);

  const failed = { ...draft, jobs: [{ type: 'detect', status: 'error', result: [],
    errors: [{ sha, error: '检测模型暂时不可用' }] }] };
  const retry = String(toolPreview(step, { draft: failed }, 'auto'));
  assert.match(retry, /检测模型暂时不可用/);
  assert.match(retry, /重试 AI 框/);
  assert.doesNotMatch(retry, new RegExp(sha));
  assert.doesNotMatch(String(toolPreview(step, { draft: failed }, 'manual')), /重试 AI 框/);

  const shared = { ...draft, jobs: [{ type: 'detect', status: 'done',
    result: [{ sha, status: 'skipped', reason_code: 'shared_image', reason: '共用图需人工框选' }], errors: [] }] };
  const skipped = String(toolPreview(step, { draft: shared }, 'ask'));
  assert.match(skipped, /共用图需人工框选/);
  assert.match(skipped, /我来框/);
  assert.doesNotMatch(skipped, new RegExp(sha));

  const force = { ...draft, status: 'done', training_tasks: [{ force_crop: true, boxes: [] }] };
  const afterCommit = String(toolPreview(step, { draft: force }, 'ask'));
  assert.match(afterCommit, /我来框/);
  assert.match(afterCommit, /AI 框/);
});
