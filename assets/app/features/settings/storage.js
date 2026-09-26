/** 数据与存储：备份、占用、图片扫描与压缩任务。 */
import { get, post } from '../../core/api.js';
import { downloadResponse } from '../../core/download.js';
import { reloadData } from '../../domain/data.js';
import { confirm } from '../../ui/dialog.js';
import { formatBytes, optValues } from './storage-state.js';

let activeJob = null;
let lastScan = null;
let lastBackupToken = '';

export function createStorage(root) {
  const el = id => root.querySelector(`#${id}`);
  const s = { summary: null, scan: lastScan, backupToken: lastBackupToken, job: null, busy: false };
  let alive = true;
  let timer = 0;
  let backupBusy = false;
  let confirmingCompress = false;
  const note = (id, text, tone = '') => {
    const target = el(id);
    if (target && alive) { target.textContent = text; target.dataset.tone = tone; }
  };
  const number = value => Number.isFinite(Number(value)) ? Number(value) : 0;

  function chart() {
    if (!alive || !s.summary) return;
    const spec = optValues(s.summary, s.scan, s.job);
    const total = Math.max(1, spec.items.reduce((sum, item) => sum + number(item.bytes), 0));
    note('opt-total', spec.center);
    for (const item of spec.items) {
      const key = item.key;
      note(`opt-l-${key}`, item.label);
      note(`opt-v-${key}`, formatBytes(item.bytes));
      note(`opt-d-${key}`, `${item.files} 个文件${item.note ? ` · ${item.note}` : ''}`);
      const bar = el(`opt-b-${key}`);
      if (bar) bar.value = Math.round(number(item.bytes) / total * 100);
    }
    const deps = s.summary.dependencies || {};
    const pills = [
      [deps.pillow?.available ? 'ok' : 'no', `Pillow ${deps.pillow?.available ? deps.pillow.version || '已安装' : '未安装'}`],
      [deps.jpegtran?.available ? 'ok' : 'no', `jpegtran ${deps.jpegtran?.available ? '已可用' : '未安装'}`],
      ['muted', `题图 ${formatBytes(s.summary.images?.bytes)} · ${number(s.summary.images?.count)} 张`],
    ];
    const host = el('opt-deps');
    if (host) host.replaceChildren(...pills.map(([tone, text]) => {
      const item = document.createElement('span');
      item.className = `opt-pill ${tone}`;
      item.textContent = text;
      return item;
    }));
    controls();
  }

  function controls() {
    const pillow = !!s.summary?.dependencies?.pillow?.available;
    const candidates = number(s.scan?.candidate_count);
    for (const [id, disabled] of [['opt-a-scan', !pillow || s.busy], ['opt-a-compress', !pillow || !candidates || s.busy]]) {
      const card = el(id);
      if (card) {
        card.classList.toggle('disabled', disabled);
        card.classList.toggle('busy', s.busy);
        card.setAttribute('aria-disabled', String(disabled));
      }
    }
    note('opt-compress-hint', !pillow ? '需要安装 Pillow 才能压缩'
      : !s.scan ? '扫描图片后可压缩' : !candidates ? '没有可压缩的图片'
        : `${candidates} 张候选，约 ${formatBytes(s.scan.potential_bytes)}`);
    el('opt-m-images')?.classList.toggle('scanning', s.busy);
    note('opt-head-sub', s.busy ? activeJob?.mode === 'compress' ? '压缩中…' : '扫描中…'
      : candidates ? '快扫完成' : '刚刚更新');
  }

  function progress(show, label = '准备中', pct = 0, file = '') {
    const host = el('opt-progress');
    if (host) host.hidden = !show;
    note('opt-progress-text', label);
    note('opt-progress-percent', `${pct}%`);
    if (el('opt-progress-fill')) el('opt-progress-fill').value = pct;
    note('opt-progress-file', file);
  }

  async function load() {
    const result = await get('/api/optimize/summary');
    if (!alive) return result;
    if (!result.ok) { note('opt-status', `无法读取优化状态：${result.error?.message || '未知错误'}`, 'danger'); return result; }
    s.summary = result.data;
    chart();
    if (!s.summary?.dependencies?.pillow?.available) note('opt-status', 'Pillow 不可用，图片压缩功能已禁用。', 'warning');
    if (activeJob && !timer) { s.busy = true; controls(); pollJob(); }
    return result;
  }

  async function backupExport() {
    if (s.busy || backupBusy) return;
    backupBusy = true;
    note('svc-backup-status', '正在打包错题备份…', 'busy');
    try {
      const response = await fetch('/api/backup/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}', credentials: 'same-origin' });
      if (!response.ok) {
        let message = '导出备份失败';
        try { message = (await response.json()).msg || message; } catch { /* 非 JSON 错误体 */ }
        throw new Error(message);
      }
      s.backupToken = response.headers.get('X-OMRS-Backup-Token') || '';
      lastBackupToken = s.backupToken;
      await downloadResponse(response, `OMRS-backup-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, '')}.zip`);
      note('svc-backup-status', '备份已下载', 'success');
    } catch (error) { note('svc-backup-status', `导出失败：${error.message}`, 'danger'); }
    finally { backupBusy = false; }
  }

  async function backupImport(event) {
    const input = event.target;
    const file = input.files?.[0];
    input.value = '';
    if (!file || backupBusy) return;
    backupBusy = true;
    try {
    if (!await confirm(`导入备份 ${file.name}？`, {
      hint: '会先校验，随后可选择恢复并覆盖当前错题目录。', okText: '继续导入',
    }) || !alive) return;
    note('svc-backup-status', '正在上传并校验备份…', 'busy');
    const form = new FormData();
    form.append('file', file, file.name);
    const prepared = await post('/api/backup/import', form);
    if (!alive) return;
    if (!prepared.ok) { note('svc-backup-status', `校验失败：${prepared.error?.message || '未知错误'}`, 'danger'); return; }
    const preview = prepared.data?.preview || {};
    const hint = `备份校验通过：${preview.files || 0} 个文件，${formatBytes(preview.bytes)}，Markdown ${preview.md_files || 0}，图片 ${preview.image_files || 0}。恢复会覆盖当前“错题”目录，且不可在页面内撤销。`;
    if (!await confirm('恢复备份并覆盖当前错题目录？', { hint, okText: '恢复', danger: true })) {
      note('svc-backup-status', '已取消恢复，当前数据未改变。');
      return;
    }
    if (!alive) return;
    const restored = await post('/api/backup/restore', { restore_id: prepared.data.restore_id, confirm: true });
    if (!alive) return;
    if (!restored.ok) { note('svc-backup-status', `恢复失败：${restored.error?.message || '未知错误'}`, 'danger'); return; }
    note('svc-backup-status', `已恢复备份，当前索引 ${restored.data?.question_count || 0} 题。建议刷新页面。`, 'success');
    await reloadData();
    s.scan = null; lastScan = null;
    s.backupToken = ''; lastBackupToken = '';
    await load();
    } finally { backupBusy = false; }
  }

  function schedulePoll(delay = 500) {
    clearTimeout(timer);
    timer = setTimeout(() => { timer = 0; pollJob(); }, delay);
  }

  async function pollJob() {
    if (!activeJob || !alive) return;
    const { id, mode } = activeJob;
    const result = await get(`/api/optimize/job?id=${encodeURIComponent(id)}`);
    if (!alive || activeJob?.id !== id) return;
    if (!result.ok) {
      activeJob = null;
      s.busy = false;
      progress(false);
      note('opt-status', `读取任务进度失败：${result.error?.message || '未知错误'}`, 'danger');
      controls();
      return;
    }
    const job = result.data?.job || {};
    s.job = mode === 'compress' ? job : null;
    const pct = Math.min(100, Math.round(number(job.processed) / Math.max(1, number(job.total)) * 100));
    const label = mode === 'scan' ? job.done ? '快扫完成' : '快扫中'
      : job.status === 'running' ? '深扫压缩中' : job.status || '准备中';
    const file = job.current_file ? `当前：${job.current_file}`
      : mode === 'scan' ? `已扫描 ${number(job.processed)} / ${number(job.total)} 个图片文件`
        : `已检查 ${number(job.processed)} / ${number(job.total)}，已压缩 ${number(job.candidate_count)} 张，节省 ${formatBytes(job.saved_bytes)}`;
    progress(true, label, pct, file);
    chart();
    if (!job.done) { schedulePoll(mode === 'scan' ? 500 : 900); return; }
    activeJob = null;
    s.busy = false;
    if (mode === 'scan') {
      s.scan = job.result || null;
      lastScan = s.scan;
      const skipped = Object.entries(s.scan?.skipped || {}).map(([key, count]) => `${key}：${count}`).join('；');
      note('opt-status', `快扫完成：${number(s.scan?.candidate_count)} 张图片可进入深扫压缩，范围 ${formatBytes(s.scan?.potential_bytes)}。${skipped ? `跳过：${skipped}` : ''}`, 'success');
    } else {
      note('opt-status', `深扫压缩完成：实际压缩 ${number(job.candidate_count)} 张，节省 ${formatBytes(job.saved_bytes)}${job.errors?.length ? `，有 ${job.errors.length} 个错误` : '。'}`, 'success');
      s.scan = null;
      lastScan = null;
      s.backupToken = ''; lastBackupToken = '';
      await load();
    }
    chart();
    controls();
  }

  async function scanImages() {
    if (s.busy || !s.summary?.dependencies?.pillow?.available) return;
    s.busy = true;
    controls();
    s.scan = null; lastScan = null;
    progress(true, '快扫中', 0, '正在统计图片格式和可深扫范围');
    note('opt-status', '正在快扫图片，不会生成优化副本…', 'busy');
    const result = await post('/api/optimize/scan', {});
    if (!result.ok || !result.data?.job?.job_id) {
      if (!alive) return;
      s.busy = false;
      progress(false);
      note('opt-status', `快扫失败：${result.error?.message || '未知错误'}`, 'danger');
      controls();
      return;
    }
    activeJob = { id: result.data.job.job_id, mode: 'scan' };
    if (!alive) return;
    s.busy = true;
    controls();
    pollJob();
  }

  async function compress() {
    if (s.busy || confirmingCompress || !s.scan || !number(s.scan.candidate_count)) return;
    const hint = `即将深扫并无损压缩 ${s.scan.candidate_count} 张候选图片（约 ${formatBytes(s.scan.potential_bytes)}）。压缩会改写图片文件；如需保险，可先导出备份。`;
    confirmingCompress = true;
    const confirmed = await confirm('确认开始压缩？', { hint, okText: '开始压缩' });
    confirmingCompress = false;
    if (!confirmed || !alive) return;
    s.busy = true;
    controls();
    const result = await post('/api/optimize/compress', { scan_id: s.scan.scan_id, backup_token: s.backupToken, confirm: true });
    if (!result.ok || !result.data?.job?.job_id) { if (alive) { s.busy = false; controls(); note('opt-status', `压缩失败：${result.error?.message || '未知错误'}`, 'danger'); } return; }
    activeJob = { id: result.data.job.job_id, mode: 'compress' };
    if (!alive) return;
    s.busy = true;
    progress(true, '准备压缩', 0);
    controls();
    pollJob();
  }

  return { s, load, chart, backupExport, backupImport, scanImages, compress,
    dispose() { alive = false; clearTimeout(timer); } };
}
