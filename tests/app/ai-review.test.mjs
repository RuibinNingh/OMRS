import test from 'node:test';
import assert from 'node:assert/strict';
import { createBus } from '../../assets/app/core/bus.js';
import { createReviewNavigation } from '../../assets/app/domain/ai-review.js';
import { editableValues, editedValue, changedPatch, isPending, mergePage } from '../../assets/app/features/ai-review/state.js';
import { createReviewCards, reviewCard } from '../../assets/app/features/assistant/review-cards.js';
import { runtimePanel } from '../../assets/app/features/history/runtime-view.js';
import { sortDraftQueue } from '../../assets/app/features/ai-review/drafts-state.js';
import { reviewView } from '../../assets/app/features/ai-review/view.js';
import { pendingDraftQueue, readDraftQueue, reviewFilters } from '../../assets/app/features/ai-review/queue.js';
import { operationView } from '../../assets/app/features/ai-review/operation-view.js';

const timers = () => ({ setTimeout: () => 1, clearTimeout() {} });
test('内联批准绑定已展示版本；后台新版本到达时不能代替用户确认', async () => {
  const step = { name: 'set_question_labels', args: {}, operationId: 'op_1' };
  const S = { alive: true, items: [{ run: { steps: [step] } }] }, sent = [], notices = [];
  let revision = 1, state = 'pending_confirmation';
  const cards = createReviewCards(S, () => {}, { timers: timers(), request: async () => ({ ok: true,
    item: { tool: step.name, revision, status: state, preview: { items: [] } } }),
    decide: async (...args) => { sent.push(args); state = 'approved'; return { ok: true }; } });
  await cards.refresh(); revision = 2;
  await cards.approve(step, message => notices.push(message), 1);
  assert.equal(sent.length, 0); assert.match(notices[0], /提案已变化/);
  await cards.approve(step, () => {}, 2);
  assert.deepEqual(sent, [['op_1', 2, 'approve']]);
  assert.match(String(reviewCard(S, { id: 'run' }, step)), /等待执行/);
  assert.doesNotMatch(String(reviewCard(S, { id: 'run' }, step)), /已完成/);
  cards.dispose();
});

test('标记回执解释变更和跳过数量，成功卡片不保留待确认文案；历史不能再批准', () => {
  const step = { name: 'set_question_labels', args: {}, operationId: 'op_1' }, run = { id: 'run' };
  const S = { reviews: { op_1: { item: { tool: step.name, status: 'applied',
    result: { changed: ['A', 'B'], skipped: ['C'], details: [] } } } } };
  const view = String(reviewCard(S, run, step));
  assert.match(view, /已修改 2 道 · 1 道无需变更/);
  assert.doesNotMatch(view, /需确认|你已允许|assistant.approve/);
  S.reviews.op_1.item = { tool: step.name, status: 'pending_confirmation', history_readonly: true };
  assert.doesNotMatch(String(reviewCard(S, run, step)), /assistant.approve|assistant.deny/);
});
test('统一导航与角标：草稿去重总数、失败保留、同页目标和修改通知', async () => {
  const bus = createBus(), badge = { hidden: true, setAttribute() {} }, seen = [];
  let count = 3, route = 'assistant';
  const nav = createReviewNavigation({ bus, document: { getElementById: () => badge, addEventListener() {}, removeEventListener() {} }, timers: timers(),
    router: { current: () => route.split('?')[0], go: value => { route = value; } },
    request: async () => count == null ? { ok: false } : { ok: true, data: { counts: { pending: count, drafts: 2, operations: 1 } } } });
  bus.on('ai-review:counts', value => seen.push(value.pending));
  await nav.refresh(); assert.equal(badge.textContent, '3'); assert.equal(badge.hidden, false);
  count = null; await nav.refresh(); assert.equal(badge.textContent, '3');
  assert.equal(await nav.open('DR-1', { kind: 'draft' }), true); assert.equal(route, 'ai-review?draft=DR-1');
  await nav.open('op_2'); assert.equal(route, 'ai-review?operation=op_2');
  count = 0; const changed = []; bus.on('ai-review:changed', payload => changed.push(payload.ids));
  nav.changed(['op_2']); await nav.refresh(); assert.equal(badge.hidden, true); assert.deepEqual(changed, [['op_2']]);
  assert.equal(seen[0], 3); nav.dispose();
});

test('人工修订：只提供服务端白名单，不允许复杂对象；数字、列表及补丁保持类型', () => {
  const item = { kind: 'operation', status: 'pending_confirmation', editable_fields: ['question', 'difficulty', 'labels', 'target'],
    payload: { patch: { question: '旧提案', difficulty: 5, labels: ['重要'], target: { uid: 'A' } } } };
  const original = editableValues(item); assert.deepEqual(original, { question: '旧提案', difficulty: 5, labels: ['重要'] });
  const edited = { ...original, difficulty: editedValue(5, '7'), labels: editedValue(['重要'], '重要，考前\n复习') };
  assert.deepEqual(changedPatch(original, edited), { difficulty: 7, labels: ['重要', '考前', '复习'] });
  assert.equal(isPending(item), true); assert.equal(isPending({ ...item, history_readonly: true }), false);
  assert.equal(isPending({ ...item, status: 'approved' }), false);
  assert.equal(mergePage([{ id: '1', kind: 'operation', revision: 1 }], [{ id: '1', kind: 'operation', revision: 2 }, { id: '1', kind: 'draft' }]).length, 2);
});

test('聊天权威状态：修订使结束卡片重绘，拒绝用当前 revision，历史事件不被覆盖', async () => {
  const step = { callId: 'c', operationId: 'op_1', reviewRevision: 1, status: 'waiting', preview: { title: '历史内容' } };
  const run = { id: 'run', steps: [step] }, S = { alive: true, items: [{ run }] }, decisions = [], opened = [];
  let revision = 2, state = 'pending_confirmation';
  const cards = createReviewCards(S, () => {}, { timers: timers(), request: async () => ({ ok: true,
    item: { id: 'op_1', revision, status: state, preview: { title: '人工修订内容' } } }),
    decide: async (...args) => { decisions.push(args); state = 'rejected'; return { ok: true }; }, open: async id => opened.push(id) });
  await cards.refresh(); assert.ok(S.reviewVer > 0); assert.match(String(reviewCard(S, run, step)), /提案已修订/);
  assert.equal(step.preview.title, '历史内容');
  await cards.reject(step, () => {}); assert.deepEqual(decisions, [['op_1', 2, 'reject']]);
  assert.equal(S.reviews.op_1.item.status, 'rejected'); assert.doesNotMatch(String(reviewCard(S, run, step)), /assistant.deny/);
  await cards.open(step); assert.deepEqual(opened, ['op_1']); cards.dispose(); S.alive = false;
});

test('聊天并发决定只送达一次，状态读取失败保留已核实结果', async () => {
  const step = { operationId: 'op_1' }, S = { alive: true, items: [{ run: { steps: [step] } }] };
  let fail = false, release, calls = 0;
  const cards = createReviewCards(S, () => {}, { timers: timers(), request: async () => fail ? { ok: false, error: '离线' }
    : { ok: true, item: { revision: 4, status: 'pending_confirmation' } }, decide: () => { calls++; return new Promise(resolve => { release = resolve; }); } });
  await cards.refresh(); const first = cards.reject(step, () => {}); await new Promise(setImmediate);
  await cards.reject(step, () => {}); assert.equal(calls, 1); release({ ok: true }); await first;
  fail = true; await cards.refresh(); assert.equal(S.reviews.op_1.item.revision, 4); assert.equal(S.reviews.op_1.error, '离线'); cards.dispose();
});

test('系统运行的关联审核只提供中心入口，不提供独立批准', () => {
  const view = String(runtimePanel({ operation: { operation_id: 'op_1', status: 'pending_confirmation', impact: {} } }, 'local'));
  assert.match(view, /history.openReview/); assert.doesNotMatch(view, /history.operationConfirm|history.operationReject/);
});

test('同秒草稿按与公共队列相同的ID倒序推进，不改变接口原数组', () => {
  const same = '2026-10-03T08:00:00Z', rows = [
    { id: 'DR-a', created_at: same }, { id: 'DR-z', created_at: same },
    { id: 'DR-m', created_at: same }, { id: 'DR-0', created_at: '2026-10-03T08:00:01Z' },
  ];
  const queue = sortDraftQueue(rows); assert.deepEqual(queue.map(row => row.id), ['DR-0', 'DR-z', 'DR-m', 'DR-a']);
  const previousIndex = queue.findIndex(row => row.id === 'DR-m');
  assert.equal(queue.filter(row => row.id !== 'DR-m')[previousIndex].id, 'DR-a');
  assert.deepEqual(rows.map(row => row.id), ['DR-a', 'DR-z', 'DR-m', 'DR-0']);
});

test('手机队列与详情标识保留布尔字符串，空队列仍能维护草稿', () => {
  const state = { items: [], loaded: true, view: 'pending', source: '', type: '', range: '', mobileDetail: false };
  assert.match(String(reviewView(state)), /data-mobile-detail="false"/);
  assert.match(String(reviewView({ ...state, mobileDetail: true })), /data-mobile-detail="true"/);
  assert.match(String(reviewView(state)), /ai-review.draftQueueMenu/);
  const records = String(reviewView({ ...state, view: 'records', status: 'interrupted' }));
  assert.match(records, /value="interrupted" selected/); assert.doesNotMatch(records, /value="invalidated"/);
});

test('连续审核按完整公共待办分页筛选身份，保留来源/时间且排除入库提案', async () => {
  const filters = reviewFilters({ view: 'records', source: 'agent', type: 'draft', status: 'done', range: '7' });
  assert.equal(filters.source, 'agent'); assert.ok(filters.from); const seen = [];
  const allowed = await pendingDraftQueue(filters, async args => {
    seen.push(args); return args.offset ? { ok: true, items: [{ id: 'inside-2', kind: 'draft' }], has_more: false }
      : { ok: true, items: [{ id: 'inside-1', kind: 'draft' }, { id: 'op_commit', kind: 'operation' }], has_more: true, next_offset: 100 };
  });
  assert.deepEqual(allowed.items.map(row => row.id), ['inside-1', 'inside-2']);
  assert.ok(seen.every(args => args.view === 'pending' && args.source === 'agent' && args.from === filters.from && args.status === ''));
  const rows = ['outside', 'inside-1', 'represented', 'inside-2'].map(id => ({ id, status: 'review', created_at: '2026-10-03T08:00:00Z' }));
  const result = await readDraftQueue('pending', async () => allowed, async () => ({ ok: true, data: { drafts: rows } }));
  assert.deepEqual(result.data.drafts.map(row => row.id), ['inside-2', 'inside-1']);
});

test('原生或公共队列失败不伪造为空待审，原生失败时不继续请求身份', async () => {
  let calls = 0; const filter = async () => { calls++; return { ok: false, error: '公共请求失败' }; };
  const native = { ok: false, error: { message: '原生请求失败' } };
  assert.equal(await readDraftQueue('pending', filter, async () => native), native); assert.equal(calls, 0);
  const result = await readDraftQueue('pending', filter, async () => ({ ok: true, data: { drafts: [] } }));
  assert.equal(result.ok, false); assert.equal(result.error.message, '公共请求失败');
});

test('公共待办超过原生500条上限时，最旧详情仍在连续导航范围内', async () => {
  const rows = Array.from({ length: 501 }, (_, index) => ({ id: `DR-${String(500 - index).padStart(4, '0')}`, status: 'review', created_at: '2026-10-03T08:00:00Z' }));
  const queue = await readDraftQueue('pending', async () => ({ ok: true, items: rows }), async () => ({ ok: true, data: { drafts: rows.slice(0, 500) } }));
  assert.equal(queue.data.drafts.length, 501);
  const selected = rows[500].id, position = queue.data.drafts.findIndex(row => row.id === selected);
  assert.equal(position, 500);
  const remaining = queue.data.drafts.filter(row => row.id !== selected);
  assert.equal(remaining[Math.min(position, remaining.length - 1)].id, 'DR-0001');
});

test('详情仅展示已有MCP请求身份及Web决定身份，历史缺失不补造', () => {
  const state = { item: { id: 'op_1', kind: 'operation', revision: 1, source: 'mcp', status: 'applied',
    actor: { key_id: 'KEY-17', request_id: '<request-9>' },
    decision: { decision: 'approve', actor: { kind: 'web', access: 'direct', client_ip: '127.0.0.1' } } }, original: {} };
  const view = String(operationView(state));
  assert.match(view, /MCP 密钥编号/); assert.match(view, /KEY-17/); assert.match(view, /&lt;request-9&gt;/);
  assert.match(view, /Web · 本机访问/); assert.match(view, /审核来源 IP/); assert.match(view, /127\.0\.0\.1/);
  const session = String(operationView({ ...state, item: { ...state.item, decision: { actor: { kind: 'web', access: 'session' } } } }));
  assert.match(session, /Web · 登录会话/);
  const old = String(operationView({ ...state, item: { ...state.item, actor: {}, decision: null } }));
  assert.doesNotMatch(old, /MCP 密钥编号|来源请求|审核身份|审核来源 IP/);
});
