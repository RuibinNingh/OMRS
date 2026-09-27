/** Label definitions, writes and redraw notifications shared by every page. */
import { get, post } from '../../core/api.js';
import { itemsNow, reloadData } from '../data.js';
import { qvInvalidate } from '../question/index.js';
import { toast } from '../../ui/toast.js';
import { sortLabels, upsertLabel, readRecent, touchRecent, quickList, nextColor, applyBatch } from './model.js';
import { presetColors as colors } from './color.js';

let definitions = [];
let emit = () => {};
export const allLabels = () => definitions;
export const listLabels = () => definitions.filter(label => !label.archived);
export function connectLabels(bus) { emit = (type, payload) => bus?.emit(type, payload); }
const storage = () => { try { return globalThis.localStorage; } catch (_) { return null; } };
export const recentLabels = () => readRecent(storage(), definitions);
export const quickLabels = (limit = 4) => quickList(definitions, recentLabels(), limit);
export const nextLabelColor = () => nextColor(definitions, colors());
export const touchLabels = names => touchRecent(storage(), names, definitions);

async function request(path, body) {
  const result = body === undefined ? await get(path) : await post(path, body);
  if (!result.ok) throw new Error(result.error?.message || '请求失败');
  return result.data;
}
export { request as labelRequest };

export async function loadLabels() {
  try { definitions = sortLabels((await request('/api/labels'))?.labels || []); }
  catch (_) { definitions = []; }
  emit('labels', definitions);
  return definitions;
}
export function upsertLocal(label) {
  if (label?.name) definitions = upsertLabel(definitions, label);
  emit('labels', definitions);
}
export async function createLabel(name, selected) {
  const clean = String(name || '').trim();
  if (!clean) return null;
  let found = definitions.find(label => label.name === clean);
  if (!found) {
    found = (await request('/api/label/save', { name: clean, color: nextLabelColor() })).label;
    upsertLocal(found);
  }
  selected?.add(found.name);
  return found;
}
export function refreshLabelViews(uids = []) {
  for (const uid of uids) qvInvalidate(uid);
  emit('labels', definitions);
  emit('questions:render');
  emit('schedule:render');
  emit('feedback:render');
  emit('board:reload');
}
export async function saveQuestionLabels(uid, labels) {
  const item = itemsNow().find(row => row.uid === uid);
  const before = item ? [...(item.labels || [])] : [];
  if (item) item.labels = [...labels];
  refreshLabelViews([uid]);
  try {
    await request('/api/question/labels', { uid, labels });
    touchLabels(labels);
    await loadLabels();
    toast(labels.length ? `已保存标记：${labels.join('、')}` : '已清空标记', { kind: 'ok' });
  } catch (error) {
    if (item) item.labels = before;
    refreshLabelViews([uid]);
    toast(`保存标记失败：${error.message}`, { kind: 'error' });
  }
}
export async function batchLabels(uids, add = [], remove = []) {
  const result = await request('/api/questions/labels', { uids, add, remove });
  const next = applyBatch(itemsNow(), uids, add, remove);
  itemsNow().forEach(item => { if (next[item.uid]) item.labels = next[item.uid]; });
  touchLabels(add);
  await loadLabels();
  refreshLabelViews(uids);
  return result;
}
export async function reloadLabelsAndData() { await reloadData(); await loadLabels(); refreshLabelViews(); }
