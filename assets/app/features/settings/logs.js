/** 日志导出窗口：筛选不丢失勾选，失败保留选择，关闭／离页使旧回调失效。 */
import { get } from '../../core/api.js';
import { morph } from '../../core/dom.js';
import { downloadResponse } from '../../core/download.js';
import { dialog, closeDialog } from '../../ui/dialog.js';
import { formatBytes } from './storage-state.js';
import { filterLogs, logsView, logListView } from './logs-view.js';

export function createLogExport(root) {
  let alive = true;
  let modal = null;
  let generation = 0;
  let downloading = null;

  async function open() {
    if (!alive || modal) return;
    const selected = new Set();
    let files = [];
    let loaded = false;
    let loading = false;
    let busy = false;
    let requestId = 0;
    let maxBytes = Infinity;
    let maxFiles = Infinity;
    const current = ++generation;
    const active = () => alive && generation === current && modal?.open;
    const el = id => modal?.querySelector(`#${id}`);
    const note = (message = '', tone = '') => {
      if (!active()) return;
      el('st-log-status').textContent = message;
      el('st-log-status').dataset.tone = tone;
    };
    const filters = () => ({ q: el('st-log-query').value, kind: el('st-log-kind').value,
      since: el('st-log-since').value, until: el('st-log-until').value });
    function update() {
      if (!active()) return;
      const options = filters();
      const invalid = options.since && options.until && options.since > options.until;
      el('st-log-since').max = options.until;
      el('st-log-until').min = options.since;
      el('st-log-until').setAttribute('aria-invalid', String(!!invalid));
      const shown = invalid ? [] : filterLogs(files, options);
      const empty = loading && !loaded ? '正在读取日志列表…' : !loaded ? '日志列表未能读取，请点击“刷新列表”重试。'
        : invalid ? '开始日期不能晚于结束日期。' : !files.length ? '暂无可导出的日志。AI 请求日志需在助手设置中开启记录后才会产生。' : '没有符合筛选条件的日志，可调整或重置筛选。';
      morph(el('st-log-list'), logListView(shown, selected, empty));
      el('st-log-list').setAttribute('aria-busy', String(loading));
      const visibleSelected = shown.filter(file => selected.has(file.id)).length;
      const chosen = files.filter(file => selected.has(file.id));
      const bytes = chosen.reduce((total, file) => total + file.size_bytes, 0);
      const all = el('st-log-all');
      all.checked = !!shown.length && visibleSelected === shown.length;
      all.indeterminate = visibleSelected > 0 && visibleSelected < shown.length;
      all.disabled = busy || !shown.length;
      el('st-log-clear').disabled = busy || !chosen.length;
      el('st-log-refresh').disabled = busy || loading;
      el('st-log-list').querySelectorAll('input').forEach(input => { input.disabled = busy; });
      const hidden = chosen.length - visibleSelected;
      el('st-log-summary').textContent = `显示 ${shown.length} / ${files.length} 份 · 已选 ${chosen.length} 份 · ${formatBytes(bytes)}${hidden ? `（含筛选外 ${hidden} 份）` : ''}`;
      const ok = modal.querySelector('[data-dialog-ok]');
      ok.textContent = busy ? '正在导出…' : `导出已选（${chosen.length}）`;
      ok.disabled = busy || !chosen.length || bytes > maxBytes || chosen.length > maxFiles;
      if (bytes > maxBytes || chosen.length > maxFiles) note(`每次最多 ${maxFiles} 份、${formatBytes(maxBytes)}，请减少选择后导出。`, 'danger');
    }
    async function load() {
      if (!active() || busy || loading) return;
      const id = ++requestId;
      loading = true;
      note(); update();
      const result = await get('/api/logs');
      if (!active() || id !== requestId) return;
      loading = false;
      if (result.ok) {
        files = result.data.files || [];
        maxBytes = result.data.max_bytes;
        maxFiles = result.data.max_files;
        const available = new Set(files.map(file => file.id));
        let removed = 0;
        for (const id of selected) if (!available.has(id)) { selected.delete(id); removed++; }
        loaded = true;
        note(removed ? `${removed} 份已选日志不再存在，已从选择中移除。` : '');
      } else note(`读取失败：${result.error?.message || '未知错误'}${loaded ? '，保留上次列表。' : ''}`, 'danger');
      update();
    }
    await dialog({
      id: 'st-log-dialog', title: '导出日志', size: 'lg', cancelText: '关闭', okText: '导出已选（0）',
      body: logsView(), focus: '#st-log-query', dismissible: () => !busy,
      onOpen(window) {
        modal = window;
        modal.addEventListener('input', event => {
          if (['st-log-query', 'st-log-kind', 'st-log-since', 'st-log-until'].includes(event.target.id)) { note(); update(); }
        });
        modal.addEventListener('change', event => {
          if (busy) return;
          const input = event.target;
          if (input.dataset.logId) {
            if (input.checked) selected.add(input.dataset.logId); else selected.delete(input.dataset.logId);
          } else if (input.id === 'st-log-all') {
            for (const file of filterLogs(files, filters())) {
              if (input.checked) selected.add(file.id); else selected.delete(file.id);
            }
          }
          note(); update();
        });
        modal.addEventListener('click', event => {
          if (busy) return;
          const id = event.target.closest('button')?.id;
          if (id === 'st-log-refresh') load();
          if (id === 'st-log-clear') { selected.clear(); note(); update(); }
          if (id === 'st-log-reset') {
            for (const id of ['st-log-query', 'st-log-kind', 'st-log-since', 'st-log-until']) el(id).value = '';
            note(); update();
          }
        });
        update(); load();
      },
      async onOk() {
        if (!active() || busy || !selected.size) return false;
        busy = true;
        downloading = new AbortController();
        modal.querySelectorAll('[data-dialog-cancel]').forEach(button => { button.disabled = true; });
        note('正在打包所选日志…'); update();
        try {
          const response = await fetch('/api/logs/export', { method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ files: [...selected] }), signal: downloading.signal });
          if (!response.ok) {
            let message = '日志导出失败';
            try { message = (await response.json()).msg || message; } catch { /* 非 JSON 错误回执。 */ }
            throw new Error(message);
          }
          if (!active()) return false;
          await downloadResponse(response, 'OMRS-logs.zip');
          if (!active()) return false;
          const status = root.querySelector('#svc-log-status');
          if (status) { status.textContent = `已导出 ${selected.size} 份日志。`; status.dataset.tone = 'success'; }
          return true;
        } catch (error) {
          note(`导出失败：${error.message || '未知错误'}，选择已保留。`, 'danger');
          return false;
        } finally {
          busy = false;
          downloading = null;
          if (active()) {
            modal.querySelectorAll('[data-dialog-cancel]').forEach(button => { button.disabled = false; });
            update();
          }
        }
      },
    });
    if (generation === current) { generation++; modal = null; }
  }

  return { open, dispose() {
    alive = false; generation++;
    downloading?.abort(); downloading = null;
    if (modal) {
      modal.querySelectorAll('[data-dialog-cancel]').forEach(button => { button.disabled = false; });
      closeDialog(modal);
    }
    modal = null;
  } };
}
