import { imageValue } from '../../core/uploads.js';
/** 题卡工作区：就绪图片按题卡逐张核对、识别、创建。字段去抖 600ms 存进收件箱的 cards，创建走 /api/inbox/commit。 */
import { morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { createCombobox } from '../../ui/combobox.js';
import { itemsOf } from '../../domain/items.js';
import { openCreateLabelPicker } from '../../domain/labels/index.js';
import { boardChooseAndAdd } from '../../domain/board/index.js';
import { reloadData } from '../../domain/data.js';
import { loadTaxonomy, mergeTaxonomy } from '../../domain/taxonomy.js';
import { notifyHistoryChanged } from '../../domain/history.js';
import { inbox as sharedInbox, notify } from './inbox.js';
import { cropDataUrl, paintCrops } from './crop.js';
import { classifyCards } from './inbox-ops.js';
import { readyCards, parseKey, cardValue, missingRequired, commitSummary, suggestions } from './cards-state.js';
import { cardsView } from './cards-view.js';

/** 提示条上的「加入展示板」：一张或一批都加进最近用过的板（没有板先新建）。 */
function boardAction(uids) {
  const clean = (uids || []).filter(Boolean);
  if (!clean.length) return null;
  return { label: clean.length > 1 ? `加入展示板（${clean.length} 题）` : '加入展示板', onClick: () => boardChooseAndAdd(clean) };
}

export function createCards(root, ctx, services = {}) {
  const inbox = services.inbox || sharedInbox;
  const S = inbox.state;
  const io = { post, cropDataUrl, reloadData, notify, createCombobox, ...services };
  void loadTaxonomy();
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
    if (services.paint) { services.paint(S); return; }
    const cards = readyCards(S.items);
    morph(host, cardsView({ cards, selected: S.csel, busy, batch, loaded: S.loaded }));
    combobox.sync();
    paintCrops(host, id => inbox.item(id));
  }
  function schedule() {
    if (!alive || scheduled) return;
    scheduled = true;
    queueMicrotask(() => { scheduled = false; paint(); });
  }

  function field(arg, value) {
    if (batch) return;
    const [key, name] = String(arg).split('|');
    const found = entry(key);
    if (!found) return;
    found.form[name] = cardValue(name, value);
    found.form.manual_fields = { ...(found.form.manual_fields || {}), [name]: true };
    if (found.form.field_sources) delete found.form.field_sources[name];
    inbox.saveSoon(found.item, { cards: { [found.card]: found.form } }, 600);
    schedule();
  }

  function openLabels(key, anchor) {
    if (batch || busy.has(key)) return;
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
    if (batch && !quiet) return null;
    const found = entry(key);
    if (!found || busy.has(key)) return null;
    const { item, card, form } = found;
    if (missingRequired(form)) { io.notify(`${quiet ? `题卡 ${card}：` : ''}科目和分类是必填项`, 'warn'); return null; }
    busy.add(key); schedule();
    try {
      if (!await inbox.flush()) { io.notify('还有未保存的修改，创建已取消', 'warn'); return null; }
      const fresh = inbox.item(item.id);
      if (!fresh || fresh.status !== 'ready') { io.notify('题卡状态已变化，请核对后重新创建', 'warn'); return null; }
      const snapshot = JSON.parse(JSON.stringify(fresh));
      const currentForm = snapshot.cards?.[String(card)];
      if (!currentForm || missingRequired(currentForm)) { io.notify('题卡内容已变化，请核对后重新创建', 'warn'); return null; }
      if (currentForm.created_question_id || currentForm.created_uid) {
        return { uid: currentForm.created_uid, question_id: currentForm.created_question_id, reused: true };
      }
      const crops = {};
      for (const region of snapshot.regions.filter(row => Number(row.card) === card && row.role !== 'ignore' && row.convert === 'image')) {
        crops[region.id] = await imageValue(await io.cropDataUrl(snapshot, region), 'inbox');
      }
      if (!await inbox.flush()) { io.notify('还有未保存的修改，创建已取消', 'warn'); return null; }
      if (inbox.item(item.id)?.revision !== snapshot.revision) {
        io.notify('裁图期间题卡内容发生变化，请核对后重新创建', 'warn'); return null;
      }
      const result = await io.post('/api/inbox/commit', { id: snapshot.id, card, form: currentForm, crops,
        expected_revision: snapshot.revision, reset_epoch: snapshot.reset_epoch });
      if (!result.ok) { io.notify(`创建失败：${result.error?.message || '未知错误'}`, 'warn'); return null; }
      const data = result.data || {};
      S.csel.delete(key);
      if (!quiet) io.notify(`${data.reused ? '已恢复既有题目' : '已创建'} ${data.uid}（${data.file_path}）；原图与框位已存入数据集`, undefined, boardAction([data.uid]));
      await inbox.load();
      if (!quiet) refreshAfterCreate();
      return data;
    } catch (error) {
      io.notify(`创建失败：${error.message || error}`, 'warn');
      return null;
    } finally { busy.delete(key); schedule(); }
  }

  function refreshAfterCreate() {
    notifyHistoryChanged('create');
    ctx.bus.emit('catalog:refresh');
    io.reloadData().then(result => { if (!result?.ok) io.notify('题目已创建，统计刷新失败，请刷新页面', 'warn'); });
  }

  /** 批量创建：逐张提交，最后只弹一条汇总，「加入展示板」一次加入这批新题。 */
  async function commitSelected() {
    const keys = [...S.csel].filter(key => entry(key));
    if (!keys.length) { io.notify('先勾选要创建的题卡', 'warn'); return; }
    if (batch) return;
    if (busy.size) { io.notify('请等当前题卡创建完成后再批量创建', 'warn'); return; }
    batch = true; schedule();
    const created = [];
    let reused = 0;
    let failed = 0;
    for (const key of keys) {
      const data = await commit(key, { quiet: true });
      if (data?.reused) reused += 1;
      else if (data?.uid) created.push(data.uid); else failed += 1;
    }
    batch = false; schedule();
    if (created.length || reused) {
      io.notify(`${commitSummary(created.length, failed)}${reused ? `；${reused} 张已创建题卡未重复写入` : ''}`, failed ? 'warn' : undefined, boardAction(created));
      refreshAfterCreate();
    }
  }

  async function back(id) {
    if (batch || busy.size) return;
    const item = inbox.item(id);
    if (!item) return;
    item.status = 'boxed';
    if (!await inbox.save(item, { status: 'boxed' })) return;
    inbox.open(id);
    inbox.go('process');
  }

  const combobox = io.createCombobox(host, { options(name, input) {
    const data = mergeTaxonomy(suggestions(itemsOf(ctx.store.get().data)));
    if (name === 'subject') return data.subjects;
    if (name === 'category') {
      const [key] = String(input.dataset.arg || '').split('|');
      return data.categoriesBySubject[entry(key)?.form.subject?.trim()] || [];
    }
    return data.tags;
  } });
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
      if (!found.length) { io.notify('先勾选要识别的题卡', 'warn'); return; }
      classifyCards(found);
    },
    dispose() { alive = false; combobox.dispose(); stop(); stopLabels(); stopData(); },
  };
}
