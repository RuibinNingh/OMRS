/** 收件箱上传阶段的网格和批量操作；处理区迁移期间共用旧控制器的数据。 */
import { morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { viewQ } from '../../domain/question/index.js';
import { FILTERS, visibleItems, selectableItems, gridView } from './grid-view.js';
import { snapshot, refreshLegacy, openLegacy, reloadLegacy, detectLegacy, applyLastLegacy, wholeLegacy } from './legacy-inbox.js';

let filter = 'all';

export function createGrid(root, bus) {
  const host = root.querySelector('#create-grid');
  let alive = true;
  let busy = false;
  let error = '';

  function paint() {
    if (!alive) return;
    const current = snapshot();
    morph(host, gridView({ ...current, filter, busy, error }));
  }

  function selected() { return snapshot().selected; }
  function updateSelection() { refreshLegacy(); }

  const stop = bus.on('inbox:grid', paint);
  paint();
  return {
    filter(value) { if (!FILTERS.some(([key]) => key === value)) return; filter = value; paint(); },
    select(id, checked) { if (checked) selected().add(id); else selected().delete(id); updateSelection(); },
    selectAll(checked) {
      const current = snapshot();
      selectableItems(visibleItems(current.items, filter)).forEach(item => checked ? current.selected.add(item.id) : current.selected.delete(item.id));
      updateSelection();
    },
    clear() { selected().clear(); updateSelection(); },
    open(id) {
      const item = snapshot().items.find(row => row.id === id && row.status !== 'discarded');
      if (!item) { toast('图片已不在收件箱，请刷新列表', { kind: 'warn' }); return; }
      if (item.status === 'done') {
        if (item.link?.uid) viewQ(item.link.uid, 'q');
        else toast('这条记录没有关联的题目详情', { kind: 'warn' });
      } else openLegacy(item.id);
    },
    openSelected() { const first = [...selected()][0]; if (first) this.open(first); },
    detect(provider) { detectLegacy(provider); },
    applyLast() { applyLastLegacy(); },
    whole() { wholeLegacy(); },
    async discard() {
      if (busy) return;
      const current = snapshot();
      const ids = [...current.selected].filter(id => current.items.some(item => item.id === id && item.status !== 'done' && item.status !== 'discarded'));
      if (!ids.length) return;
      if (!await confirm(`丢弃 ${ids.length} 张？原图会保留在收件箱数据目录，不进题库。`, { danger: true })) return;
      busy = true; error = ''; paint();
      const result = await post('/api/inbox/discard', { ids });
      busy = false;
      if (!alive) return;
      if (!result.ok) { error = `丢弃失败：${result.error?.message || '未知错误'}`; paint(); return; }
      current.selected.clear();
      await reloadLegacy();
      paint();
    },
    dispose() { alive = false; stop(); },
  };
}
