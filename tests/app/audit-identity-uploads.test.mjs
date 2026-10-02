import test from 'node:test';
import assert from 'node:assert/strict';
import { questionRef, questionRefs } from '../../assets/app/domain/question/ref.js';
import { fbRowsForSession, fbRailEntries, currentContext, remainingFeedbackRows, mergeSessionRows, omrApplyToRows, submitPayload } from '../../assets/app/features/feedback/state.js';
import { sessionProgress } from '../../assets/app/domain/sessions.js';
import { mergeLoaded } from '../../assets/app/features/schedule/arrange.js';
import { pruneSelection } from '../../assets/app/features/schedule/exporter.js';
import { uploadImage, uploadFiles } from '../../assets/app/core/uploads.js';
import { businessToday, dayKey, daysBetween, parseDay } from '../../assets/app/core/date.js';
import { historyItems, mergeHistoryItems, applyEvent } from '../../assets/app/features/assistant/state.js';
import { configSavedStatus } from '../../assets/app/core/config-status.js';
import { connectData, reloadData, resetData, itemsNow } from '../../assets/app/domain/data.js';
import { batchLabels } from '../../assets/app/domain/labels/state.js';
import { detailModel } from '../../assets/app/features/schedule/state.js';

const entry = (entry_id, question_id, uid, availability = 'active', feedback_submitted = false) => ({ entry_id, question_id, uid, uid_at_creation: 'OLD', availability, feedback_submitted });

test('确认前冻结的身份不会因移动和UID重用而换题；未知身份拒绝写入', () => {
  const old = { question_id: 'original', uid: 'OLD' };
  const ref = questionRef('OLD', [old]);
  old.uid = 'NEW';
  const reused = { question_id: 'replacement', uid: 'OLD' };
  assert.deepEqual(questionRef(ref, [old, reused]), { question_id: 'original' });
  assert.deepEqual(questionRefs([old, old]), [{ question_id: 'original' }]);
  assert.throws(() => questionRef('gone', [old, reused]), /身份不可确认/);
  assert.throws(() => { ref.question_id = 'replacement'; }, TypeError);
});

test('批量标记回包前发生移动与UID复用，本地回执仍只更新原题身份', async () => {
  const initial = { question_id: 'original', uid: 'OLD', labels: [] };
  let snapshot = { items: [initial] };
  let release;
  let posted;
  const originalFetch = globalThis.fetch;
  const response = data => new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } });
  connectData({ fetch: async () => response(snapshot) });
  globalThis.fetch = async (path, init) => {
    if (path === '/api/questions/labels') {
      posted = JSON.parse(init.body);
      await new Promise(resolve => { release = resolve; });
      return response({ count: 1 });
    }
    assert.equal(path, '/api/labels');
    return response({ labels: [] });
  };
  try {
    await reloadData();
    const pending = batchLabels([initial], ['已复核']);
    assert.deepEqual(posted.question_refs, [{ question_id: 'original' }]);
    snapshot = { items: [{ question_id: 'original', uid: 'NEW', labels: [] }, { question_id: 'replacement', uid: 'OLD', labels: [] }] };
    await reloadData();
    release();
    await pending;
    assert.deepEqual(itemsNow().map(item => [item.question_id, item.labels]), [['original', ['已复核']], ['replacement', []]]);
  } finally {
    release?.();
    globalThis.fetch = originalFetch;
    resetData();
  }
});

test('Session按固定条目编号；同UID归档条目不串到新题，unresolved保持只读', () => {
  const session = { entries: [entry('a', 'original', 'OLD', 'archived'), entry('b', 'replacement', 'OLD'), entry('c', '', '', 'unresolved')] };
  const rows = fbRowsForSession(session);
  const report = omrApplyToRows(rows, [{ number: 1, correct: true }, { number: 2, correct: false }, { number: 3, correct: true }], session.entries, new Set());
  assert.deepEqual(rows.map(row => row.correct), [null, false, null]);
  assert.equal(report.filled, 1); assert.equal(report.manual.length, 2);
  const rail = fbRailEntries(session, rows);
  assert.equal(currentContext(rail, rows, 0), null); assert.equal(currentContext(rail, rows, 2), null);
  assert.equal(currentContext(rail, rows, 1).row.question_id, 'replacement');
  assert.deepEqual(submitPayload(rows), [{ question_id: 'replacement', entry_id: 'b', sub_score: 4, is_correct: false, note: '' }]);
  assert.equal(sessionProgress(session).total, 3);
});

test('计划详情预览和翻页上下文冻结稳定ID，旧UID复用不改变题目身份', () => {
  const first = entry('a', 'original-a', 'OLD-A');
  const second = entry('b', 'original-b', 'OLD-B');
  const detail = detailModel({ entries: [first, second, entry('c', '', 'OLD-C', 'unresolved')] });
  const current = [{ question_id: 'original-a', uid: 'NEW-A' }, { question_id: 'original-b', uid: 'NEW-B' },
    { question_id: 'replacement-a', uid: 'OLD-A' }, { question_id: 'replacement-b', uid: 'OLD-B' }];
  assert.deepEqual(detail.previewable, ['original-a', 'original-b']);
  assert.deepEqual(detail.previewable.map(key => questionRef(key, current).question_id), ['original-a', 'original-b']);
  assert.deepEqual(detail.questions.map(row => [row.uid, row.preview_key]), [['OLD-A', 'original-a'], ['OLD-B', 'original-b'], ['OLD-C', '']]);
});

test('失败反馈按稳定身份保留输入并同步新UID，成功回执仅移除对应题', () => {
  const failed = { ...entry('b', 'original', 'OLD'), score: 2, correct: false, note: '保留人工错因' };
  const successful = { ...entry('a', 'other', 'OTHER'), score: 9, correct: true, note: '' };
  const retained = remainingFeedbackRows([successful, failed], [{ question_id: 'other', status: 'ok' }]);
  const next = mergeSessionRows({ entries: [entry('a', 'other', 'OTHER', 'active', true), entry('b', 'original', 'NEW')] }, retained);
  assert.equal(next.length, 1); assert.strictEqual(next[0], failed);
  assert.deepEqual([next[0].question_id, next[0].uid, next[0].score, next[0].correct, next[0].note], ['original', 'NEW', 2, false, '保留人工错因']);
});

test('调度和导出选择跟随ID移动，不保留复用旧UID的新身份', () => {
  const selected = new Map([['original', { question_id: 'original', uid: 'OLD' }]]);
  const items = [{ question_id: 'original', uid: 'NEW' }, { question_id: 'replacement', uid: 'OLD' }];
  assert.equal(mergeLoaded({ due: items }, selected).selected.get('original').uid, 'NEW');
  assert.deepEqual(pruneSelection(['original'], items), ['original']);
  assert.deepEqual(pruneSelection(['original'], items.slice(1)), []);
});

test('超16MiB原图按块保留精确字节、MIME及文件名，重复块重试不改变index', async () => {
  const size = 16 * 1024 * 1024 + 3;
  const bytes = new Uint8Array(size); bytes[0] = 137; bytes[size - 1] = 91;
  const file = new File([bytes], '原图.png', { type: 'image/png' });
  const sent = []; let first = true;
  const send = async (path, body, options) => {
    sent.push([path, body, options]);
    if (path.endsWith('/start')) return { ok: true, data: { upload_id: 'upl-1', chunk_bytes: 16 * 1024 * 1024 } };
    if (path.includes('/chunk')) { if (first) { first = false; return { ok: false, status: 0 }; } return { ok: true, data: {} }; }
    return { ok: true, data: { upload_ref: 'upl-1', bytes: size } };
  };
  assert.deepEqual(await uploadImage(file, { purpose: 'inbox', send }), { upload_ref: 'upl-1' });
  assert.deepEqual(sent[0][1], { filename: '原图.png', mime: 'image/png', total_bytes: size, purpose: 'inbox' });
  const chunks = sent.filter(([path]) => path.includes('/chunk'));
  assert.deepEqual(chunks.map(([path, body]) => [path.split('index=')[1], body.size]), [['0', 16 * 1024 * 1024], ['0', 16 * 1024 * 1024], ['1', 3]]);
  const reconstructed = new Blob(chunks.slice(1).map(([, body]) => body));
  assert.deepEqual(new Uint8Array(await reconstructed.arrayBuffer()), bytes);
  assert.equal(chunks[0][2].headers['Content-Type'], 'application/octet-stream');
});

test('上传失败不会交给领域创建；引用回执字节不一致明确失败', async () => {
  let finalized = false;
  const result = await uploadFiles([new File(['bytes'], 'a.png', { type: 'image/png' })], 'inbox', '/api/inbox/upload-refs', { send: async path => {
    if (path === '/api/inbox/upload-refs') finalized = true;
    return { ok: false, status: 413, error: { message: '超量' } };
  } });
  assert.equal(result.ok, false); assert.equal(finalized, false);
  await assert.rejects(uploadImage(new Blob(['abc'], { type: 'image/png' }), { send: async path => ({ ok: true,
    data: path.endsWith('start') ? { upload_id: 'id', chunk_bytes: 16 } : path.endsWith('complete') ? { upload_ref: 'id', bytes: 1 } : {} }) }), /大小不一致/);
});

test('业务午夜由上海决定，夏令时天差仍为整数，非法日期拒绝', () => {
  for (const zone of ['UTC', 'America/Los_Angeles', 'Asia/Shanghai']) {
    const previous = process.env.TZ; process.env.TZ = zone;
    try {
      assert.equal(dayKey(businessToday(new Date('2026-10-02T15:59:59Z'))), '2026-10-02');
      assert.equal(dayKey(businessToday(new Date('2026-10-02T16:00:00Z'))), '2026-10-03');
      assert.equal(daysBetween('2026-03-08', '2026-03-09'), 1);
      assert.equal(parseDay('2026-02-31'), null);
    } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
  }
});

test('助手分段事件不提前结束步骤；更早页合并保留当前run对象和消息键', () => {
  const current = historyItems([{ type: 'user', text: '原话', item_key: 'u-r' }, { type: 'run', item_key: 'r-r', run: { id: 'r', status: 'done' },
    events: [{ i: 0, type: 'round.start', data: { n: 1 } }, { i: 1, type: 'delta', data: { kind: 'text', text: '前半' } }], events_has_more: true, events_next: 2 }]);
  const run = current[1].run;
  assert.equal(run.steps.at(-1).live, true); assert.equal(run.next, 2);
  applyEvent(run, { i: 2, type: 'delta', data: { kind: 'text', text: '后半' } });
  applyEvent(run, { i: 3, type: 'run.end', data: { reason: 'completed' } });
  assert.equal(run.steps.at(-1).src, '前半后半'); assert.equal(run.steps.at(-1).live, false);
  const merged = mergeHistoryItems([...historyItems([{ type: 'user', item_key: 'older', text: '更早' }]), ...current], current);
  assert.equal(merged.length, 3); assert.strictEqual(merged[2].run, run); assert.equal(merged[1].item_key, 'u-r');
  assert.equal(configSavedStatus({ mirror_pending: true }).tone, 'warning');
});
