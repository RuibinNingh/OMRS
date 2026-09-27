/** 题卡工作区：就绪图片按题卡逐张核对、识别、创建。字段去抖 600ms 存进收件箱的 cards，创建走 /api/inbox/commit。 */
import { morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { itemsOf } from '../../domain/items.js';
import { openCreateLabelPicker } from '../../domain/labels/index.js';
import { boardChooseAndAdd } from '../../domain/board/index.js';
import { reloadData } from '../../domain/data.js';
import { notifyHistoryChanged } from '../../domain/history.js';
import { inbox, notify } from './inbox.js';
import { cropDataUrl, paintCrops } from './crop.js';
import { classifyCards } from './inbox-ops.js';
import { readyCards, parseKey, cardValue, missingRequired, commitSummary, suggestions } from './cards-state.js';
import { cardsView } from './cards-view.js';

const S = inbox.state;

/** 提示条上的「加入展示板」：一张或一批都加进最近用过的板（没有板先新建）。 */
function boardAction(uids) {
  const clean = (uids || []).filter(Boolean);
  if (!clean.length) return null;
  return { label: clean.length > 1 ? `加入展示板（${clean.length} 题）` : '加入展示板', onClick: () => boardChooseAndAdd(clean) };
}

export function createCards(root, ctx) {
  const host = root.querySelector('#ib-stage-create');
  let alive = true;
  let scheduled = false;
  let batch = false;
  const busy = new Set();

  function entry(key) {
    const { id, card } = parseKey(key);
    const item = inbox.item(id);
    const form = item?.cards?.[String(card)];
    return item && form ? { item, card, form } : null;
  }

  function paint() {
    if (!alive || S.stage !== 'create') return;
    const cards = readyCards(S.items);
    morph(host, cardsView({ cards, selected: S.csel, busy, batch, loaded: S.loaded, suggest: suggestions(itemsOf(ctx.store.get().data)) }));
    paintCrops(host, id => inbox.item(id));
  }
  function schedule() {
    if (!alive || scheduled) return;
    scheduled = true;
    queueMicrotask(() => { scheduled = false; paint(); });
  }

  function field(arg, value) {
    const [key, name] = String(arg).split('|');
    const found = entry(key);
    if (!found) return;
    found.form[name] = cardValue(name, value);
    inbox.saveSoon(found.item, { cards: { [found.card]: found.form } }, 600);
    schedule();
  }

  function openLabels(key, anchor) {
    const found = entry(key);
    if (!found) return;
    openCreateLabelPicker(anchor, {
      get: () => entry(key)?.form.labels || [],
      onSave: values => {
        const current = entry(key);
        if (!current) return;
        current.form.labels = cardValue('labels', (values || []).join(','));
        inbox.saveSoon(current.item, { cards: { [current.card]: current.form } }, 600);
        schedule();
      },
    });
  }

  async function commit(key, { quiet = false } = {}) {
    const found = entry(key);
    if (!found || busy.has(key)) return null;
    const { item, card, form } = found;
    if (missingRequired(form)) { notify(`${quiet ? `题卡 ${card}：` : ''}科目和分类是必填项`, 'warn'); return null; }
    busy.add(key); schedule();
    try {
      await inbox.flush();
      const crops = {};
      for (const region of item.regions.filter(row => Number(row.card) === card && row.role !== 'ignore' && row.convert === 'image')) {
        crops[region.id] = await cropDataUrl(item, region);
      }
      const result = await post('/api/inbox/commit', { id: item.id, card, form, crops });
      if (!result.ok) { notify(`创建失败：${result.error?.message || '未知错误'}`, 'warn'); return null; }
      const data = result.data || {};
      S.csel.delete(key);
      if (!quiet) notify(`已创建 ${data.uid}（${data.file_path}）；原图与框位已存入数据集`, undefined, boardAction([data.uid]));
      await inbox.load();
      if (!quiet) refreshAfterCreate();
      return data;
    } catch (error) {
      notify(`创建失败：${error.message || error}`, 'warn');
      return null;
    } finally { busy.delete(key); schedule(); }
  }

  function refreshAfterCreate() {
    notifyHistoryChanged('create');
    ctx.bus.emit('catalog:refresh');
    reloadData().then(result => { if (!result?.ok) notify('题目已创建，统计刷新失败，请刷新页面', 'warn'); });
  }

  /** 批量创建：逐张提交，最后只弹一条汇总，「加入展示板」一次加入这批新题。 */
  async function commitSelected() {
    const keys = [...S.csel].filter(key => entry(key));
    if (!keys.length) { notify('先勾选要创建的题卡', 'warn'); return; }
    if (batch) return;
    batch = true; schedule();
    const created = [];
    let failed = 0;
    for (const key of keys) {
      const data = await commit(key, { quiet: true });
      if (data?.uid) created.push(data.uid); else failed += 1;
    }
    batch = false; schedule();
    if (created.length) {
      notify(commitSummary(created.length, failed), failed ? 'warn' : undefined, boardAction(created));
      refreshAfterCreate();
    }
  }

  async function back(id) {
    const item = inbox.item(id);
    if (!item) return;
    item.status = 'boxed';
    await inbox.save(item, { status: 'boxed' });
    inbox.open(id);
    inbox.go('process');
  }

  const stop = ctx.bus.on('inbox:changed', schedule);
  const stopLabels = ctx.bus.on('labels', schedule);
  const stopData = ctx.store.subscribe(schedule, value => value.data);
  paint();

  return {
    paint, field, openLabels, commit: key => commit(key), commitSelected, back,
    select(key, checked) { if (checked) S.csel.add(key); else S.csel.delete(key); schedule(); },
    selectAll(checked) { readyCards(S.items).forEach(card => (checked ? S.csel.add(card.key) : S.csel.delete(card.key))); schedule(); },
    classify(key) { const found = entry(key); if (found) classifyCards([found]); },
    classifySelected() {
      const found = [...S.csel].map(entry).filter(Boolean);
      if (!found.length) { notify('先勾选要识别的题卡', 'warn'); return; }
      classifyCards(found);
    },
    dispose() { alive = false; stop(); stopLabels(); stopData(); },
  };
}
