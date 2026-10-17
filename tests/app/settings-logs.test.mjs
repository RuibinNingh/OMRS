import test from 'node:test';
import assert from 'node:assert/strict';
import { filterLogs, logListView } from '../../assets/app/features/settings/logs-view.js';

const files = [
  { id: 'runtime:one.log', name: 'one.log', kind: 'runtime', modified_day: '2026-10-16', modified_at: '2026-10-16T12:00:00Z', size_bytes: 10 },
  { id: 'runtime:two.log', name: 'two.log', kind: 'runtime', modified_day: '2026-10-17', modified_at: '2026-10-17T12:00:00Z', size_bytes: 20 },
  { id: 'ai:agent.jsonl', name: 'agent.jsonl', kind: 'ai', modified_day: '2026-10-17', modified_at: '2026-10-17T12:00:00Z', size_bytes: 30 },
];

test('日志类型、文件名和日期可组合，日期边界包含当天', () => {
  assert.deepEqual(filterLogs(files, { kind: 'runtime', since: '2026-10-17', until: '2026-10-17', q: ' TWO ' }), [files[1]]);
  assert.deepEqual(filterLogs(files, { kind: 'ai' }), [files[2]]);
  assert.deepEqual(filterLogs(files, { q: 'missing' }), []);
  assert.equal(files.length, 3);
});

test('筛选不会更改已有选择，回到原筛选后仍显示勾选', () => {
  const selected = new Set(['runtime:one.log', 'ai:agent.jsonl']);
  const hidden = filterLogs(files, { kind: 'runtime', since: '2026-10-17' });
  assert.doesNotMatch(String(logListView(hidden, selected)), /checked/);
  assert.equal(selected.size, 2);
  assert.match(String(logListView(filterLogs(files, { kind: 'ai' }), selected)), /checked/);
});

test('日志文件名只作为文本显示，空列表有明确原因', () => {
  const unsafe = { ...files[0], id: 'runtime:<img>.log', name: '<img src=x onerror="x">.log' };
  const output = String(logListView([unsafe], new Set()));
  assert.doesNotMatch(output, /<img/);
  assert.match(output, /&lt;img/);
  assert.match(String(logListView([], new Set(), '暂无日志')), /暂无日志/);
});
