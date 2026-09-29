/** 收件箱的批量与 AI 操作：网格批量条、处理区与题卡共用。长图先切条带再交给 detect；提取只同步本次提取的区域。 */
import { get } from '../../core/api.js';
import { inbox, notify } from './inbox.js';
import { cropDataUrl } from './crop.js';
import { newRegion } from './process-state.js';

const S = inbox.state;

async function strips(item) {
  const result = await get(`/api/inbox/slice-plan?width=${item.width}&height=${item.height}`);
  if (!result.ok) throw new Error(`切片失败：${result.error?.message || '未知错误'}`);
  const out = [];
  for (const strip of result.data?.strips || []) {
    out.push({ y0: strip.y0, y1: strip.y1, data: await cropDataUrl(item, { x: 0, y: strip.y0, w: 1, h: strip.y1 - strip.y0 }, 'image/jpeg', 0.85) });
  }
  return out;
}

export function detectSummary(count, job) {
  const rows = job.result || [];
  const boxes = rows.reduce((sum, row) => sum + (row.boxes || 0), 0);
  const blind = rows.filter(row => row.blind).length;
  const extracted = rows.filter(row => row.auto?.extracted).length;
  const errors = job.errors || [];
  let text = `框选完成：${count} 张，共 ${boxes} 框，请逐张确认`;
  if (blind) text += `；其中 ${blind} 张为盲标（不展示 AI 框，请直接手画）`;
  if (extracted) text += `；${extracted} 张已自动提取，待人工审核`;
  if (errors.length) text += `；${errors.length} 张失败：${errors[0].msg}`;
  return { text, warn: errors.length > 0 };
}

/** 服务端按设置里的 inbox_detect_provider 选框选提供方。 */
export async function detect(ids) {
  const units = [];
  for (const id of ids) {
    const item = inbox.item(id);
    if (!item || item.status === 'done' || item.regions?.some(row => row.text_status === 'running')) continue;
    try {
      const unit = { item_id: id, reset_epoch: item.reset_epoch, replace: !(item.regions || []).length };
      unit.strips = await strips(item);
      units.push(unit);
    } catch (error) { notify(error.message || String(error), 'warn'); }
  }
  if (!units.length) return;
  notify(`已提交 ${units.length} 张给 AI 框选（长图已切成条带），完成后自动回填`);
  try {
    await inbox.job('detect', { items: units }, async job => {
      await inbox.load();
      const summary = detectSummary(units.length, job);
      notify(summary.text, summary.warn ? 'warn' : undefined);
    });
  } catch (error) { notify(`AI 框选失败：${error.message || error}`, 'warn'); }
}

export function detectSelected() {
  const ids = [...S.sel];
  if (!ids.length) { notify('先勾选要框选的图', 'warn'); return; }
  detect(ids);
}

export async function wholeSelected() {
  let count = 0;
  for (const id of S.sel) {
    const item = inbox.item(id);
    if (!item || item.status === 'done' || item.regions?.some(row => row.text_status === 'running')) continue;
    item.regions = [newRegion(1, 'question', 0, 0, 1, 1)];
    item.layout = 'plain';
    if (await inbox.save(item, { regions: item.regions, layout: item.layout })) count += 1;
  }
  notify(`已把 ${count} 张整图标为题目区域`);
  inbox.changed();
}

/** 一次提交当前图的待提取区域；已完成的人工决定不会被批量操作覆盖。 */
export async function extractRegions(item, regionIds) {
  if (!item || item.regions.some(row => row.text_status === 'running')) return;
  const epoch = item.reset_epoch;
  const regions = item.regions.filter(row => regionIds.includes(row.id) && row.role !== 'ignore');
  if (!regions.length) { notify('各区域已提取，请审核结果后标记就绪'); return; }
  const extracted = new Set(regions.map(row => row.id));
  const fail = async error => {
    const local = inbox.item(item.id);
    if (local && local.reset_epoch === epoch) {
      for (const row of local.regions) {
        if (extracted.has(row.id) && row.text_status === 'running') row.text_status = 'error';
      }
      await inbox.save(local, { regions: local.regions, status: 'boxed' });
    }
    inbox.changed();
    notify(`提取失败：${error.message || error}，请重试`, 'warn');
  };
  // 在裁图和请求之前锁定，避免快速连点重复提交。
  regions.forEach(row => { row.text_status = 'running'; });
  inbox.changed();
  try {
    const crops = [];
    for (const region of regions) crops.push({ region_id: region.id, crop: await cropDataUrl(item, region) });
    if (inbox.item(item.id)?.reset_epoch !== epoch) return;
    if (!await inbox.save(item, { regions: item.regions, status: 'boxed' })) throw new Error('区域未保存');
    if (inbox.item(item.id)?.reset_epoch !== epoch) return;
    await inbox.job('extract', { regions: crops.map(row => ({ ...row, reset_epoch: epoch })) }, async job => {
      const failed = new Set((job.errors || []).map(row => row.unit?.region_id));
      if (!await inbox.load()) throw new Error('读取提取结果失败');
      inbox.changed();
      notify(failed.size ? '部分区域提取失败，请重试；成功结果已保留' : '提取完成，请审核文本或图片后标记就绪', failed.size ? 'warn' : undefined);
    }, fail);
  } catch (error) { await fail(error); }
}

/** 题卡分类识别：用每张题卡的第一个题目区域；只填空缺项，由服务端合并。 */
export async function classifyCards(entries) {
  const cards = [];
  for (const { item, card } of entries) {
    const question = item.regions.find(region => Number(region.card) === card && region.role === 'question');
    if (question) cards.push({ item_id: item.id, reset_epoch: item.reset_epoch, card, crop: await cropDataUrl(item, question) });
  }
  if (!cards.length) { notify('没有可识别的题卡', 'warn'); return; }
  notify(`AI 识别 ${cards.length} 张题卡的科目 / 分类 / 难度 / 知识点…`);
  try {
    await inbox.job('classify', { cards }, async () => {
      await inbox.load();
      notify('已填科目 / 分类 / 难度 / 知识点（只填空缺项，不覆盖已填）');
    });
  } catch (error) { notify(`识别失败：${error.message || error}`, 'warn'); }
}
