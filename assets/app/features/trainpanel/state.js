/** 训练面板的纯显示模型。 */
import { formatDuration, formatPercent } from '../../core/format.js';
export const roles = [{ key: 'question', label: '题目', target: .9 }, { key: 'answer', label: '答案', target: .8 }];
export const stateLabels = { running: '训练中', done: '已完成', failed: '失败', interrupted: '已中断' };
export const pct = value => formatPercent(value, { digits: 1 });
export const duration = formatDuration;
export function remaining(status) {
  if (status?.state !== 'running' || !status.epoch_seconds) return '—';
  return duration(Math.max(0, status.epochs - status.epoch) * status.epoch_seconds);
}
export function mergeMetrics(previous, incoming) {
  const byEpoch = new Map(previous.map(row => [row.epoch, row]));
  incoming.forEach(row => { if (Number.isFinite(row.epoch)) byEpoch.set(row.epoch, row); });
  return [...byEpoch.values()].sort((a, b) => a.epoch - b.epoch);
}
export function ticks(max, steps = 4) {
  const limit = Number.isFinite(max) && max > 0 ? max : 1;
  return Array.from({ length: steps + 1 }, (_, i) => limit * i / steps);
}
export function point(x, y, maxX, maxY) {
  return [48 + Math.max(0, Number(x) || 0) / Math.max(1, maxX) * 516,
    196 - Math.max(0, Number(y) || 0) / Math.max(.001, maxY) * 166];
}
