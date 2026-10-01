/** MCP 密钥元数据投影；到期状态与日期均以设备当前时间为准。 */
import { formatDate } from '../../core/format.js';

export function keyStatus(key, now = Date.now()) {
  if (key.revoked_at) return 'revoked';
  const expiry = key.expires_at ? Date.parse(key.expires_at) : NaN;
  return Number.isFinite(expiry) && expiry <= now ? 'expired' : 'active';
}

export function splitKeys(keys, now = Date.now()) {
  const active = [], inactive = [];
  for (const key of keys) (keyStatus(key, now) === 'active' ? active : inactive).push(key);
  return { active, inactive };
}

export function keyTime(value, compact = false, now = Date.now()) {
  const date = formatDate(value, 'datetime');
  if (date === '—' || !compact) return date;
  return formatDate(value) === formatDate(now) ? `今天 ${formatDate(value, 'time')}` : date;
}
