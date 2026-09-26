import test from 'node:test';
import assert from 'node:assert/strict';
import { buildReportAiPrompt, fileError, formatSize, materialHint } from '../../assets/app/features/reports/state.js';
import { view } from '../../assets/app/features/reports/view.js';

const state = () => ({ reports: [], loaded: true, loading: false, listError: '', selectedId: '', includeImages: false,
  name: '', file: null, fileError: '', uploading: false, downloading: false, status: '', statusTone: '' });

test('上传只接受非空 HTML 文件', () => {
  assert.match(fileError(null), /请选择/);
  assert.match(fileError({ name: 'report.txt', size: 50 }), /只支持/);
  assert.match(fileError({ name: 'report.html', size: 0 }), /为空/);
  assert.equal(fileError({ name: 'report.HTM', size: 50 }), '');
});

test('材料提示与提示词按题图选项切换', () => {
  assert.match(materialHint(false), /Markdown/);
  assert.match(materialHint(true), /ZIP/);
  assert.match(buildReportAiPrompt(false), /不要猜测题图/);
  assert.match(buildReportAiPrompt(true), /api\/image/);
  assert.match(buildReportAiPrompt(true), /禁止虚构/);
});

test('文件大小格式与页面契约', () => {
  assert.equal(formatSize(500), '500 B');
  assert.equal(formatSize(2048), '2.0 KB');
  assert.equal(formatSize(1048576), '1.0 MB');
});

test('报告名称转义，预览 iframe 不给同源权限', () => {
  const s = state();
  s.reports = [{ id: 'a&b', name: '<script>恶意</script>', size: 100, created_at: '今天' }];
  s.selectedId = 'a&b';
  const markup = String(view(s));
  assert.match(markup, /&lt;script&gt;恶意&lt;\/script&gt;/);
  assert.match(markup, /sandbox="allow-scripts allow-downloads allow-popups"/);
  assert.doesNotMatch(markup, /allow-same-origin| on\w+=| style=/);
  assert.match(markup, /id=a%26b/);
});
