/** Scan the Vault and refresh the two snapshots it can change. */
import { post } from '../core/api.js';
import { toast } from '../ui/toast.js';
import { reloadData } from './data.js';
import { refreshSessions } from './sessions.js';

export async function scanVault() {
  const res = await post('/api/scan', {});
  if (!res.ok || res.data?.status !== 'ok') {
    toast(`扫描失败：${res.error?.message || res.data?.msg || '未知错误'}`, { kind: 'error' });
    return false;
  }
  toast(`扫描完成，共 ${res.data.count} 道题目`, { kind: 'ok' });
  await Promise.all([reloadData(), refreshSessions()]);
  return true;
}
