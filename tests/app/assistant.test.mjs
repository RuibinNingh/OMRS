// AI 助手页（features/assistant）的纯函数：事件归约成运行视图模型、持久化后合并过的事件重放、聊天 Markdown。
import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, newRun, runFrom, ctxUsed, dayGroup, tokOf, fmtS, REASON } from '../../assets/app/features/assistant/state.js';
import { renderMd, renderInline, plainOf } from '../../assets/app/features/assistant/md.js';
import { dockView, userView } from '../../assets/app/features/assistant/view.js';
import { confirmOf, toolPreview } from '../../assets/app/features/assistant/tools-view.js';

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
