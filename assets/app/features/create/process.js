/**
 * 收件箱处理工作区：队列、框选画布、区域面板与本张图的全部编辑。数据在 inbox.js 单例里；
 * 每次编辑先改本地再重绘，去抖 500ms 写回（inbox.saveSoon），离开处理区或离开本页时 flush。
 */
import { morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';
import { inbox, notify } from './inbox.js';
import { paintCrops } from './crop.js';
import { detect, detectSelected, extractRegions } from './inbox-ops.js';
import { groupCards, hasExtraction, newRegion, statusAfterEdit } from './process-state.js';
import { queueView, sideView } from './process-content.js';
import { createCanvasController } from './process-canvas.js';

const S = inbox.state;
const ROLE_KEYS = { q: 'question', a: 'answer', x: 'ignore' };
const skip = event => !!event?.target?.closest?.('textarea, input, select, label');

export function createProcess(root, bus) {
  const host = root.querySelector('#ib-stage-process');
  const queue = host.querySelector('#ib-pq-list');
  const side = host.querySelector('#ib-ps-body');
  let alive = true;
  let scheduled = false;
  const busy = () => inbox.current()?.regions.some(row => row.text_status === 'running');
  const canvas = createCanvasController(host, () => S, () => afterEdit(), { canEdit: () => !busy() });

  function paint() {
    if (!alive) return;
    const items = S.items;
    const current = inbox.current();
    const queued = inbox.queue();
    const selected = queued.filter(item => S.sel.has(item.id)).length;
    morph(queue, queueView({ items, selected: S.sel, currentId: S.cur }));
    morph(side, sideView({ item: current, selectedRegion: S.selR }));
    host.querySelector('#ib-pq-n').textContent = `${queued.length} 张`;
    host.querySelector('#ib-pq-all').checked = !!queued.length && selected === queued.length;
    host.querySelector('#ib-pq-sel-n').textContent = selected ? `（${selected}）` : '';
    host.querySelector('#ib-ps-meta').textContent = current
      ? `${current.id} · ${current.width}×${current.height} · ${current.source === 'phone' ? '手机上传' : '电脑上传'}${current.blind ? ' · 盲标（AI 框已隐藏，请直接手画）' : ''}` : '';
    const cards = groupCards(current).length;
    host.querySelector('#ib-ps-card-n').textContent = cards > 1 ? `· ${cards} 张题卡` : '';
    host.querySelector('#ib-layout').value = current?.layout || 'zuoyebang';
    host.querySelectorAll('#ib-role-seg button').forEach(button => {
      const on = button.dataset.v === S.drawRole;
      button.classList.toggle('on', on);
      button.setAttribute('aria-pressed', String(on));
    });
    host.querySelector('[data-action="create.processExtractAll"]').disabled = !current || !!busy();
    canvas.paint();
    paintCrops(side, id => inbox.item(id));
    side.querySelector('.ib-rg.sel')?.scrollIntoView({ block: 'nearest' });
  }
  function schedule() {
    if (!alive || scheduled) return;
    scheduled = true;
    queueMicrotask(() => { scheduled = false; if (S.stage === 'process' && !S.dragging) paint(); });
  }

  /** 本地改动 → 状态随框数变化 → 重绘 → 去抖保存。 */
  function afterEdit(save = true) {
    const item = inbox.current();
    if (!item) return;
    item.status = statusAfterEdit(item);
    inbox.changed();
    if (save) inbox.saveSoon(item, { regions: item.regions, status: item.status });
  }
  const region = id => inbox.current()?.regions.find(row => row.id === id) || null;

  function setRole(role) {
    if (busy()) { notify('请等本图提取完成后再修改框位', 'warn'); return; }
    S.drawRole = role;
    const selected = region(S.selR);
    if (selected && selected.role !== role) { selected.role = role; selected.judge = null; selected.convert = 'auto'; selected.text_status = 'stale'; afterEdit(); } else schedule();
  }
  function step(delta) {
    const list = inbox.queue();
    if (!list.length) return;
    const index = list.findIndex(item => item.id === S.cur);
    inbox.open(list[(index + delta + list.length) % list.length].id);
  }
  function selectRegion(id) {
    S.selR = id;
    const selected = region(id);
    if (selected && selected.role !== 'ignore') S.drawRole = selected.role;
    schedule();
  }
  function deleteRegion(id) {
    if (busy()) { notify('请等本图提取完成后再修改框位', 'warn'); return; }
    const item = inbox.current();
    if (!item) return;
    item.regions = item.regions.filter(row => row.id !== id);
    if (S.selR === id) S.selR = null;
    afterEdit();
  }
  function whole() {
    if (busy()) { notify('请等本图提取完成后再修改框位', 'warn'); return; }
    const item = inbox.current();
    if (!item) return;
    item.regions = [newRegion(1, 'question', 0, 0, 1, 1)];
    item.layout = 'plain';
    S.selR = item.regions[0].id;
    afterEdit();
    notify('整张图作为题目区域；「一键提取」会判断是否需要留图');
  }
  function setConvert(arg) {
    const [id, value] = String(arg).split(':');
    const target = region(id);
    if (!target || !hasExtraction(target) || !['text', 'image'].includes(value)) return;
    const previous = target.convert;
    target.convert = value;
    target.judge_overridden = (value === 'text') !== target.judge.ok;
    if (value !== previous) afterEdit();
  }
  function editText(id, value) {
    const target = region(id);
    if (!target || busy()) return;
    target.text = value;
    target.text_status = String(value).trim() ? 'done' : 'none';
    afterEdit();
  }
  async function discardCurrent() {
    const item = inbox.current();
    if (!item || !await confirm('丢弃这张图？', { danger: true })) return;
    if (!await inbox.flush()) { notify('还有未保存的修改，丢弃已取消', 'warn'); return; }
    const current = inbox.item(item.id);
    const result = await post('/api/inbox/discard', { id: item.id,
      expected_revision: current.revision, reset_epoch: current.reset_epoch });
    if (!result.ok) { notify(result.error?.message || '丢弃失败', 'warn'); return; }
    S.sel.delete(item.id);
    await inbox.load();
    S.cur = inbox.queue()[0]?.id || null;
    inbox.changed();
  }
  async function resetCurrent() {
    const item = inbox.current();
    if (!item || !await confirm('重置这张截图？框选、提取结果和录入信息将清空，原图保留。', { danger: true })) return;
    const fresh = await inbox.reset(item.id);
    if (!fresh) return;
    if (S.cur === item.id) {
      S.selR = null;
      S.drawCard = 1;
      S.drawRole = 'question';
    }
    inbox.changed();
    notify('已重置这张截图，可以重新框选和提取');
  }
  async function markReady() {
    const item = inbox.current();
    if (!item) return;
    if (item.regions.some(row => row.text_status === 'running')) { notify('还有区域在提取中', 'warn'); return; }
    if (item.regions.some(row => row.role !== 'ignore' && !hasExtraction(row))) {
      notify('请先一键提取并核对各区域的文本或图片', 'warn'); return;
    }
    if (!await inbox.flush()) { notify('保存失败，请先核对本地修改', 'warn'); return; }
    const saved = await inbox.save(inbox.item(item.id), { status: 'ready' });
    if (!saved) return;
    const next = inbox.queue().find(row => row.status !== 'ready' && row.id !== item.id);
    notify(`${item.file} 已就绪，进入「录入」；${next ? '已切到下一张' : '队列里没有待处理的图了'}`);
    if (next) inbox.open(next.id); else inbox.changed();
  }

  const stop = bus.on('inbox:changed', schedule);
  const onResize = () => { if (root.classList.contains('active') && S.stage === 'process') schedule(); };
  window.addEventListener('resize', onResize);
  if (S.stage === 'process') paint();

  function active() { return alive && root.classList.contains('active') && S.stage === 'process'; }
  function key(name) {
    if (!active()) return false;
    if (ROLE_KEYS[name]) setRole(ROLE_KEYS[name]);
    else if (name === 'delete' || name === 'backspace') {
      if (!S.selR) return false;
      deleteRegion(S.selR);
    } else if (name === 'mod+enter') extractAll();
    else if (name === 'enter') step(1);
    else if (name === 'escape') {
      if (!S.selR) return false;
      S.selR = null; schedule();
    } else return false;
    return true;
  }
  function extractAll() {
    const item = inbox.current();
    if (!item) return;
    extractRegions(item, item.regions.filter(row => row.role !== 'ignore' && !hasExtraction(row) && row.text_status !== 'running').map(row => row.id));
  }

  return {
    paint, key,
    open(id, event) { if (!skip(event)) inbox.open(id); },
    select(id, checked) { if (checked) S.sel.add(id); else S.sel.delete(id); inbox.changed(); },
    queueAll(checked) { inbox.queue().forEach(item => checked ? S.sel.add(item.id) : S.sel.delete(item.id)); inbox.changed(); },
    layout(value) { const item = inbox.current(); if (item) { item.layout = value; inbox.saveSoon(item, { layout: value }); } },
    role: setRole, step, whole, discardCurrent, resetCurrent, markReady, extractAll,
    region(id, event) { if (!skip(event)) selectRegion(id); },
    deleteRegion,
    clear() { const item = inbox.current(); if (!item || busy()) return; item.regions = []; S.selR = null; afterEdit(); },
    addCard() {
      const item = inbox.current();
      if (!item) return;
      S.drawCard = groupCards(item).length + 1;
      notify(`题卡 ${S.drawCard}：接下来画的框归入它`);
    },
    drawCard(card) { S.drawCard = Number(card) || 1; notify(`接下来画的框归入题卡 ${S.drawCard}`); },
    convert: setConvert, text: editText,
    extract(id) { extractRegions(inbox.current(), [id]); },
    detectCurrent() { if (S.cur && !busy()) detect([S.cur]); },
    detectSelected,
    dispose() { alive = false; stop(); window.removeEventListener('resize', onResize); canvas.dispose(); },
  };
}
