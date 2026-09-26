/** 服务与运行：状态、重启就绪确认、脱敏源码导出。 */
import { get, post } from '../../core/api.js';
import { downloadResponse } from '../../core/download.js';

export const RESTART_READY_TIMEOUT_MS = 90_000;

/** 只认新的 instance_id；连接失败与探测超时均视为重启中。 */
export async function waitForRestartReady(previousInstanceId, {
  timeoutMs = RESTART_READY_TIMEOUT_MS,
  intervalMs = 500,
  probeTimeoutMs = 1_500,
  request = async (path, options) => {
    const result = await get(path, { ...options, timeout: probeTimeoutMs });
    return result.ok ? result.data : null;
  },
  now = () => Date.now(),
  sleep = ms => new Promise(resolve => setTimeout(resolve, ms)),
} = {}) {
  if (!previousInstanceId) return false;
  const deadline = now() + timeoutMs;
  while (now() < deadline) {
    const controller = new AbortController();
    const abortTimer = setTimeout(() => controller.abort(), probeTimeoutMs);
    try {
      const state = await request('/api/auth/session', { signal: controller.signal });
      if (state?.status === 'ok' && state.instance_id && state.instance_id !== previousInstanceId) return true;
    } catch { /* 服务尚未就绪。 */ }
    finally { clearTimeout(abortTimer); }
    const remaining = deadline - now();
    if (remaining <= 0) break;
    await sleep(Math.min(intervalMs, remaining));
  }
  return false;
}

export function formatUptime(seconds) {
  let value = Math.max(0, Math.floor(Number(seconds) || 0));
  const days = Math.floor(value / 86400); value %= 86400;
  const hours = Math.floor(value / 3600); value %= 3600;
  const minutes = Math.floor(value / 60);
  if (days) return `${days}天 ${hours}小时`;
  if (hours) return `${hours}小时 ${minutes}分钟`;
  return `${minutes}分钟`;
}

export function createService(root) {
  const el = id => root.querySelector(`#${id}`);
  let alive = true;
  let restarting = false;
  let exporting = false;
  const note = (id, text, tone = '') => {
    const target = el(id);
    if (target && alive) { target.textContent = text; target.dataset.tone = tone; }
  };

  async function load() {
    note('st-runtime-state', '加载中');
    const result = await get('/api/status');
    if (!alive) return result;
    if (!result.ok) {
      note('st-runtime-state', '无法读取', 'danger');
      note('st-runtime-vault', result.error?.message || '未知错误', 'danger');
      return result;
    }
    const info = result.data || {};
    note('st-runtime-version', info.version || '—');
    note('st-runtime-uptime', formatUptime(info.uptime_seconds));
    note('st-runtime-count', `${Number(info.question_count) || 0} 题`);
    note('st-runtime-state', info.status === 'ok' ? '运行中' : info.status || '未知');
    note('st-runtime-vault', `Vault: ${info.vault_path || ''}`);
    return result;
  }

  async function restart(statusId = 'st-status', options = {}) {
    if (restarting) return false;
    restarting = true;
    note(statusId, '正在读取当前服务实例…', 'busy');
    try {
      const before = await get('/api/auth/session');
      if (!before.ok || !before.data?.instance_id) throw new Error('无法读取当前服务实例 ID');
      const requested = await post('/api/restart', {});
      if (!requested.ok) throw new Error(requested.error?.message || '重启请求失败');
      note(statusId, '重启指令已发出，等待新服务就绪…', 'busy');
      if (await waitForRestartReady(before.data.instance_id, options)) {
        if (alive) window.location.reload();
        return true;
      }
      note(statusId, '90 秒内未检测到新服务实例。请勿连续点击重启，检查 omrs.service 状态和日志。', 'danger');
    } catch (error) { note(statusId, `重启未完成：${error.message || '请求失败'}`, 'danger'); }
    finally { restarting = false; }
    return false;
  }

  async function sourceExport() {
    if (exporting) return;
    exporting = true;
    note('svc-source-status', '正在生成脱敏源码包…', 'busy');
    try {
      const response = await fetch('/api/source/export', { credentials: 'same-origin' });
      if (!response.ok) {
        let message = '下载脱敏源码失败';
        try { message = (await response.json()).msg || message; } catch { /* 非 JSON 错误体 */ }
        throw new Error(message);
      }
      await downloadResponse(response, 'OMRS-source-sanitized.zip');
      note('svc-source-status', '已下载。包内含 SOURCE_EXPORT_MANIFEST.txt，可核对排除范围。', 'success');
    } catch (error) { note('svc-source-status', `下载失败：${error.message || '未知错误'}`, 'danger'); }
    finally { exporting = false; }
  }

  return { load, restart, sourceExport, dispose() { alive = false; } };
}
