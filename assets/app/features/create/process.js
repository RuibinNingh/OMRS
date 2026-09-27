/** 收件箱处理工作区的队列、区域面板和框选画布；旧 AI 任务暂经适配器共用数据。 */
import { morph } from '../../core/dom.js';
import { groupCards } from './process-state.js';
import { queueView, sideView } from './process-content.js';
import { createCanvasController } from './process-canvas.js';
import { processLegacy } from './legacy-inbox.js';

export function createProcess(root, bus) {
  const host = root.querySelector('#ib-stage-process');
  const queue = host.querySelector('#ib-pq-list');
  const side = host.querySelector('#ib-ps-body');
  const state = () => processLegacy('state');
  let alive = true;
  let scheduled = false;
  const canvas = createCanvasController(host, state, () => processLegacy('afterEdit'));

  function paint() {
    if (!alive) return;
    const data = state();
    const items = data.items || [];
    const current = items.find(item => item.id === data.cur) || null;
    const queued = items.filter(item => item.status !== 'discarded' && item.status !== 'done');
    const selected = queued.filter(item => data.sel.has(item.id)).length;
    morph(queue, queueView({ items, selected: data.sel, currentId: data.cur }));
    morph(side, sideView({ item: current, selectedRegion: data.selR }));
    host.querySelector('#ib-pq-n').textContent = `${queued.length} 张`;
    host.querySelector('#ib-pq-all').checked = !!queued.length && selected === queued.length;
    host.querySelector('#ib-pq-sel-n').textContent = selected ? `（${selected}）` : '';
    host.querySelector('#ib-ps-meta').textContent = current
      ? `${current.id} · ${current.width}×${current.height} · ${current.source === 'phone' ? '手机上传' : '电脑上传'}${current.blind ? ' · 盲标（AI 框已隐藏，请直接手画）' : ''}` : '';
    host.querySelector('#ib-ps-card-n').textContent = groupCards(current).length > 1 ? `· ${groupCards(current).length} 张题卡` : '';
    host.querySelector('#ib-layout').value = current?.layout || 'zuoyebang';
    host.querySelectorAll('#ib-role-seg button').forEach(button => button.classList.toggle('on', button.dataset.v === data.drawRole));
    canvas.paint();
    side.querySelector('.ib-rg.sel')?.scrollIntoView({ block: 'nearest' });
  }
  function schedule() {
    if (!alive || scheduled) return;
    scheduled = true;
    queueMicrotask(() => { scheduled = false; paint(); });
  }
  const off = bus.on('inbox:process', schedule);
  paint();

  function active() { return alive && root.classList.contains('active') && state()?.stage === 'process'; }
  function key(name) {
    if (!active()) return false;
    const data = state();
    if (name === 'q' || name === 'a' || name === 'x') processLegacy('role', { q: 'question', a: 'answer', x: 'ignore' }[name]);
    else if (name === 'delete' || name === 'backspace') {
      if (!data.selR) return false;
      processLegacy('deleteRegion', data.selR);
    } else if (name === 'mod+enter') processLegacy('extractAll');
    else if (name === 'enter') processLegacy('step', 1);
    else if (name === 'escape') {
      if (!data.selR) return false;
      data.selR = null; schedule();
    } else return false;
    return true;
  }

  return { paint, key, dispose() { alive = false; off(); canvas.dispose(); } };
}
