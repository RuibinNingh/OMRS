/** 收件箱上传阶段的网格和批量操作；图片列表与勾选来自 inbox.js 单例，与处理区共用。 */
import { morph } from '../../core/dom.js';
import { post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';
import { toast } from '../../ui/toast.js';
import { viewQ } from '../../domain/question/index.js';
import { FILTERS, visibleItems, selectableItems, gridView } from './grid-view.js';
import { inbox } from './inbox.js';
import { detectSelected, wholeSelected } from './inbox-ops.js';

const S = inbox.state;
let filter = 'all';

export function createGrid(root, bus) {
  const host = root.querySelector('#create-grid');
  let alive = true;
  let busy = false;
  let error = '';

  function paint() {
    if (!alive) return;
    morph(host, gridView({ items: S.items, selected: S.sel, stage: S.stage, filter, busy, error }));
  }

  const stop = bus.on('inbox:changed', paint);
  paint();
  return {
    filter(value) { if (!FILTERS.some(([key]) => key === value)) return; filter = value; paint(); },
    select(id, checked) { if (checked) S.sel.add(id); else S.sel.delete(id); inbox.changed(); },
    selectAll(checked) {
      selectableItems(visibleItems(S.items, filter)).forEach(item => checked ? S.sel.add(item.id) : S.sel.delete(item.id));
      inbox.changed();
    },
    clear() { S.sel.clear(); inbox.changed(); },
    open(id) {
      const item = S.items.find(row => row.id === id && row.status !== 'discarded');
      if (!item) { toast('图片已不在收件箱，请刷新列表', { kind: 'warn' }); return; }
      if (item.status === 'done') {
        if (item.link?.uid) viewQ(item.link.uid, 'q');
        else toast('这条记录没有关联的题目详情', { kind: 'warn' });
        return;
      }
      inbox.open(item.id);
      inbox.go('process');
    },
    openSelected() { const first = [...S.sel][0]; if (first) this.open(first); },
    detect() { detectSelected(); },
    whole() { wholeSelected(); },
    async discard() {
      if (busy) return;
      const ids = [...S.sel].filter(id => S.items.some(item => item.id === id && item.status !== 'done' && item.status !== 'discarded'));
      if (!ids.length) return;
      if (!await confirm(`丢弃 ${ids.length} 张？原图会保留在收件箱数据目录，不进题库。`, { danger: true })) return;
      busy = true; error = ''; paint();
      const result = await post('/api/inbox/discard', { ids });
      busy = false;
      if (!alive) return;
      if (!result.ok) { error = `丢弃失败：${result.error?.message || '未知错误'}`; paint(); return; }
      S.sel.clear();
      await inbox.load();
    },
    dispose() { alive = false; stop(); },
  };
}
