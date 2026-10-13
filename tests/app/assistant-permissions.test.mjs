// 三模式状态卡与延后回执：送审不是完成，重复刷新不重复统计真实写入。
import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, newRun, runFrom } from '../../assets/app/features/assistant/state.js';
import { reviewCard, createReviewCards } from '../../assets/app/features/assistant/review-cards.js';
import { modeControl, modeNote } from '../../assets/app/features/assistant/permissions.js';
import { operationView } from '../../assets/app/features/ai-review/operation-view.js';

const events = [
  { i: 0, t: 0, type: 'round.start', data: { n: 1 } },
  { i: 1, t: 1, type: 'tool.call', data: { call_id: 'call', name: 'set_question_labels', level: 'confirm', args: { uids: ['题1'] } } },
  { i: 2, t: 2, type: 'tool.waiting', data: { call_id: 'call', operation_id: 'op_1', revision: 1 } },
  { i: 3, t: 3, type: 'tool.decision', data: { call_id: 'call', how: 'defer' } },
  { i: 4, t: 4, type: 'tool.end', data: { call_id: 'call', status: 'deferred', result: { operation_id: 'op_1', pending_review: true, executed: false } } },
  { i: 5, t: 5, type: 'run.end', data: { reason: 'completed' } },
];
const pending = { id: 'op_1', operation_id: 'op_1', kind: 'operation', source: 'agent', tool: 'set_question_labels',
  status: 'pending_confirmation', revision: 1, payload: { uids: ['题1'] }, preview: { items: [] },
  permission: { mode: 'hold', channel: 'center', reason: 'hold' }, commits: [] };

test('送审后运行结束仍保持待审，独立回执只统计一次并保留原结束原因', () => {
  const run = runFrom({ id: 'run', status: 'done' }, events);
  const step = run.byCall.get('call');
  assert.equal(step.status, 'deferred'); assert.equal(run.writes, 0);
  const reviewed = { i: 6, t: 5, type: 'tool.reviewed', data: { call_id: 'call', status: 'done',
    result: { operation_id: 'op_1' }, wrote: true, commits: [{ commit_id: 'CMT-1' }] } };
  applyEvent(run, reviewed); applyEvent(run, reviewed); applyEvent(run, { ...reviewed, i: 7 });
  assert.equal(run.writes, 1); assert.equal(run.commits.length, 1);
  assert.equal(step.status, 'done'); assert.equal(run.status, 'done'); assert.equal(run.reason, 'completed');
});

test('移交与批准竞争时较晚的移交事件不会覆盖已收到的执行回执', () => {
  const run = newRun({ id: 'run' });
  events.slice(0, 3).forEach(event => applyEvent(run, event));
  applyEvent(run, { type: 'tool.reviewed', data: { call_id: 'call', status: 'done', wrote: true, commits: [{ commit_id: 'CMT-1' }] } });
  events.slice(3).forEach(event => applyEvent(run, event));
  assert.equal(run.byCall.get('call').status, 'done'); assert.equal(run.writes, 1);
});

test('送审卡展示长期状态和详情入口，手动卡有送审按钮和自动移交倒计时', () => {
  const run = runFrom({ id: 'run' }, events), step = run.byCall.get('call');
  const S = { reviews: { op_1: { item: pending } } };
  const card = String(reviewCard(S, run, step));
  assert.match(card, /已送审核/); assert.match(card, /查看审核详情/);
  assert.doesNotMatch(card, /assistant.approve|assistant.deny|ast-op__expiry/);
  S.reviews.op_1.item = { ...pending, expires_at: new Date(Date.now() + 600000).toISOString(), permission: { mode: 'manual', channel: 'chat' } };
  const manual = String(reviewCard(S, run, step));
  assert.match(manual, /送到审核中心/); assert.match(manual, /后自动送审/); assert.match(manual, /assistant.approve/);
});

test('危险模式的自动同意与实际执行完成分开显示，选择器保留红色语义', () => {
  const run = runFrom({ id: 'run' }, events), step = run.byCall.get('call');
  const item = { ...pending, status: 'approved', permission: { mode: 'danger', automatic: true } };
  const card = String(reviewCard({ reviews: { op_1: { item } } }, run, step));
  assert.match(card, /危险模式 · 自动同意/); assert.match(card, /等待执行/); assert.doesNotMatch(card, /已完成/);
  assert.match(String(modeControl({ permissionMode: 'danger' }, false)), /is-danger/);
  assert.match(String(modeNote({ permissionMode: 'danger' })), /自动同意全部权限请求/);
  assert.match(String(modeControl({}, false)), /手动模式/);
});

test('中心回执刷新同步结束的运行与撤销入口，重复刷新不重复计数', async () => {
  const run = runFrom({ id: 'run' }, events);
  const S = { alive: true, items: [{ run }] };
  let applied = 0;
  const cards = createReviewCards(S, () => {}, { timers: { setTimeout() {}, clearTimeout() {} }, onApplied: () => applied++,
    request: async () => ({ ok: true, item: { ...pending, status: 'applied', result: {}, commits: [{ commit_id: 'CMT-1' }] } }) });
  await cards.refresh(); await cards.refresh();
  assert.equal(run.writes, 1); assert.equal(run.commits.length, 1); assert.equal(applied, 1);
  cards.dispose();
});

test('审核详情展示自动决定与设置该模式的真实来源', () => {
  const view = String(operationView({ item: { ...pending, status: 'applied', permission: { mode: 'danger', automatic: true, channel: 'center', reason: 'timeout' },
    decision: { actor: { kind: 'permission_mode', selected_by: { access: 'session', client_ip: '192.0.2.1' } }, decision: 'approve' } }, original: {}, edited: {} }));
  assert.match(view, /危险模式 · 自动同意/); assert.match(view, /模式设置来源/); assert.match(view, /登录会话 · 192.0.2.1/); assert.match(view, /长期待审/);
});
