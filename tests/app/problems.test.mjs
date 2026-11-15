import test from 'node:test';
import assert from 'node:assert/strict';
import { markdown } from '../../assets/app/domain/problems.js';

test('问题Markdown支持标题、列表、代码与安全链接，HTML转义且附件走私有入口', () => {
  const src = '# 处理办法\n\n**先看符号**\n\n- 负数变号\n- 检查边界\n\n```text\n<script>bad()</script>\n```\n\n[参考](https://example.invalid/doc)\n![](PA-'+ 'a'.repeat(64)+'.svg)';
  const out = markdown(src);
  assert.match(out,/<h1>处理办法<\/h1>/);
  assert.match(out,/<strong>先看符号<\/strong>/);
  assert.match(out,/<li>负数变号<\/li>/);
  assert.match(out,/<pre><code>/);
  assert.ok(!out.includes('<script>'));
  assert.match(out,/\/api\/problem-asset\?name=PA-/);
  assert.ok(!markdown('[危险](javascript:alert(1))').includes('href="javascript:'));
});

const { createWorkspace } = await import('../../assets/app/features/problems/store.js');
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
const problem = (id, title = id) => ({ id, title, description_md: '', status: 'analyzing', revision: 1 });
const list = items => ({ items, total: items.length, counts: { all: items.length } });

test('新搜索开始后旧分页结果失效，读取失败保留已读取问题', async () => {
  const requests = [];
  const m = createWorkspace(() => {}, { read: () => { const d = deferred(); requests.push(d); return d.promise; } });
  const old = m.load();
  m.s.query = '新'; m.invalidateList();
  requests[0].resolve(list([problem('旧')])); await old;
  assert.equal(m.s.items.length, 0);
  const current = m.load(); requests[1].resolve(list([problem('新')])); await current;
  const failed = m.load(); requests[2].reject(new Error('离线')); await failed;
  assert.equal(m.s.items[0].id, '新');
  assert.equal(m.s.listError, '离线');
  assert.equal(m.s.loading, false);
});

test('快速换问题和关闭详情时，迟到响应不能重新打开或覆盖详情', async () => {
  const requests = [];
  const m = createWorkspace(() => {}, { read: () => { const d = deferred(); requests.push(d); return d.promise; } });
  const a = m.open('甲'), b = m.open('乙');
  requests[1].resolve({ problem: problem('乙') }); await b;
  requests[0].resolve({ problem: problem('甲') }); await a;
  assert.equal(m.s.detail.id, '乙');
  const late = m.open('丙'); m.close();
  requests[2].resolve({ problem: problem('丙') }); await late;
  assert.equal(m.s.detail, null);
});

test('编辑草稿与已保存问题分开，取消新建不产生正式问题', async () => {
  let writes = 0;
  const m = createWorkspace(() => {}, { read: async () => ({ problem: problem('甲') }), write: async () => { writes++; } });
  await m.open('甲'); m.s.draft.title = '草稿';
  assert.equal(m.s.detail.title, '甲'); assert.equal(m.dirty(), true);
  m.close(); assert.equal(m.dirty(), false);
  m.create(); assert.equal(m.dirty(), true);
  m.close(); assert.equal(writes, 0);
});

test('写入失败保留草稿，重试复用请求编号，重复点击只发送一次', async () => {
  const requests = [], pending = deferred();
  const m = createWorkspace(() => {}, { read: async () => ({}), write: async (action, data) => {
    requests.push(data); if (requests.length === 1) throw new Error('响应丢失'); return pending.promise;
  } });
  m.create(); m.s.draft.title = '待保存';
  await assert.rejects(m.mutate('create_problem', { title: '待保存' }), /响应丢失/);
  assert.equal(m.s.draft.title, '待保存');
  const retry = m.mutate('create_problem', { title: '待保存' });
  assert.equal(await m.mutate('create_problem', { title: '待保存' }), null);
  assert.equal(requests[0].request_id, requests[1].request_id);
  pending.resolve({ problem: problem('甲') }); await retry;
  assert.equal(m.s.busy, false);
});

test('删除最后一页后回退至有效页，保留每页数量和查询条件', async () => {
  const paths = [];
  const m = createWorkspace(() => {}, { read: async path => {
    paths.push(path); return paths.length === 1 ? { ...list([]), total: 25 } : { ...list([problem('甲')]), total: 25 };
  } });
  m.s.offset = 25; m.s.query = '数学'; await m.load();
  assert.equal(m.s.offset, 0); assert.equal(m.s.items[0].id, '甲');
  assert.equal(new URLSearchParams(paths[1].split('?')[1]).get('query'), '数学');
});

test('卸载后读取和写入结果不再更新页面', async () => {
  const pending = deferred(); let paints = 0;
  const m = createWorkspace(() => { paints++; }, { read: () => pending.promise });
  const result = m.load(); m.dispose(); const before = paints;
  pending.resolve(list([problem('迟到')])); await result;
  assert.equal(paints, before); assert.equal(m.s.items.length, 0);
});

test('写回执先确认正式身份，详情刷新失败不会把已创建问题当作新草稿', async () => {
  let writes = 0;
  const m = createWorkspace(() => {}, { read: async () => { throw new Error('详情不可用'); }, write: async () => { writes++; return { problem: problem('已创建') }; } });
  m.create(); m.s.draft.title = '待保存';
  const result = await m.mutate('create_problem', { title: m.s.draft.title });
  m.accept(result.problem); await m.open(result.problem.id);
  assert.equal(m.s.creating, false); assert.equal(m.s.detail.id, '已创建');
  assert.equal(m.dirty(), false); assert.equal(m.s.detailError, '详情不可用');
  assert.equal(writes, 1);
});
