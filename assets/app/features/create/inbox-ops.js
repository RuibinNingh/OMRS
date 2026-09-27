/** 收件箱的批量与 AI 操作：网格批量条、处理区与题卡共用。长图先切条带再交给 detect；提取只同步本次提取的区域。 */
import { get } from '../../core/api.js';
import { inbox, notify } from './inbox.js';
import { cropDataUrl } from './crop.js';
import { newRegion, transferBoxes } from './process-state.js';

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
  const ready = rows.filter(row => row.auto && row.auto.ready).length;
  const errors = job.errors || [];
  let text = `框选完成：${count} 张，共 ${boxes} 框，请逐张确认`;
  if (blind) text += `；其中 ${blind} 张为盲标（不展示 AI 框，请直接手画）`;
  if (ready) text += `；${ready} 张已按自动策略转文本并就绪`;
  if (errors.length) text += `；${errors.length} 张失败：${errors[0].msg}`;
  return { text, warn: errors.length > 0 };
}

/** provider 不传时服务端按设置里的 inbox_detect_provider 选；'template' 零联网，不切片。 */
export async function detect(ids, provider) {
  const units = [];
  for (const id of ids) {
    const item = inbox.item(id);
    if (!item || item.status === 'done') continue;
    try {
      const unit = { item_id: id, replace: !(item.regions || []).length };
      if (provider) unit.provider = provider;
      if (provider !== 'template') unit.strips = await strips(item);
      units.push(unit);
    } catch (error) { notify(error.message || String(error), 'warn'); }
  }
  if (!units.length) return;
  notify(provider === 'template' ? `按版式模板给 ${units.length} 张打初始框…` : `已提交 ${units.length} 张给 AI 框选（长图已切成条带），完成后自动回填`);
  try {
    await inbox.job('detect', { items: units }, async job => {
      await inbox.load();
      const summary = detectSummary(units.length, job);
      notify(summary.text, summary.warn ? 'warn' : undefined);
    });
  } catch (error) { notify(`AI 框选失败：${error.message || error}`, 'warn'); }
}

export function detectSelected(provider) {
  const ids = [...S.sel];
  if (!ids.length) { notify('先勾选要框选的图', 'warn'); return; }
  detect(ids, provider);
}

export async function applyLastSelected() {
  const last = S.last;
  if (!last) { notify('还没有处理过的上一张', 'warn'); return; }
  let count = 0;
  for (const id of S.sel) {
    const item = inbox.item(id);
    if (!item || item.status === 'done' || item.id === last.id) continue;
    item.regions = transferBoxes(last, item);
    await inbox.save(item);
    count += 1;
  }
  notify(`已给 ${count} 张沿用 ${last.file} 的框位`);
  inbox.changed();
}

export async function wholeSelected() {
  let count = 0;
  for (const id of S.sel) {
    const item = inbox.item(id);
    if (!item || item.status === 'done') continue;
    item.regions = [newRegion(1, 'question', 0, 0, 1, 1)];
    item.layout = 'plain';
    await inbox.save(item);
    count += 1;
  }
  notify(`已把 ${count} 张整图标为题目区域`);
  inbox.changed();
}

/** 提取文本：只同步本次提取的区域字段；当前图正在拖动时字段先合并，拖完再重绘。 */
export async function extractRegions(item, regionIds) {
  if (!item) return;
  const crops = [];
  for (const id of regionIds) {
    const region = item.regions.find(row => row.id === id);
    if (!region || region.role === 'ignore' || region.convert === 'image') continue;
    region.text_status = 'running';
    crops.push({ region_id: id, crop: await cropDataUrl(item, region) });
  }
  if (!crops.length) { notify('没有需要提取的区域（都已提取或选择保留图片）', 'warn'); return; }
  await inbox.save(item);
  inbox.changed();
  const extracted = new Set(crops.map(row => row.region_id));
  try {
    await inbox.job('extract', { regions: crops }, async () => {
      const result = await get(`/api/inbox/item?id=${encodeURIComponent(item.id)}`);
      if (!result.ok) throw new Error(result.error?.message || '未知错误');
      const fresh = result.data?.item;
      const index = S.items.findIndex(row => row.id === item.id);
      if (index >= 0 && fresh) {
        if (S.cur === item.id) {
          const local = S.items[index];
          for (const row of fresh.regions || []) {
            const target = local.regions.find(region => region.id === row.id);
            if (target && extracted.has(row.id) && target.text_status === 'running') {
              for (const key of ['convert', 'text', 'text_status', 'judge', 'judge_overridden']) target[key] = row[key];
            }
          }
          local.status = fresh.status;
        } else S.items[index] = fresh;
      }
      inbox.changed();
      notify('文本提取完成，请核对预览；确认后原图不再嵌入题目');
    });
  } catch (error) {
    item.regions.forEach(region => { if (region.text_status === 'running') region.text_status = 'none'; });
    inbox.changed();
    notify(`提取失败：${error.message || error}`, 'warn');
  }
}

/** 题卡分类识别：用每张题卡的第一个题目区域；只填空缺项，由服务端合并。 */
export async function classifyCards(entries) {
  const cards = [];
  for (const { item, card } of entries) {
    const question = item.regions.find(region => Number(region.card) === card && region.role === 'question');
    if (question) cards.push({ item_id: item.id, card, crop: await cropDataUrl(item, question) });
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
