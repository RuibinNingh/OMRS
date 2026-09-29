/** 收件箱网格、状态筛选和批量条；框位预览用 SVG 坐标，模板不写 style。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { icon } from '../../ui/icon.js';

export const FILTERS = Object.freeze([
  ['all', '全部'], ['pending', '待处理'], ['boxed', '已框选'], ['ready', '待创建'], ['done', '已录入'],
]);
export const STATUS = Object.freeze(Object.fromEntries(FILTERS.slice(1).map(([key, label]) => [key, label])));

export const liveItems = items => (items || []).filter(item => item.status !== 'discarded');
export const visibleItems = (items, filter) => liveItems(items).filter(item => filter === 'all' || item.status === filter);
export const selectableItems = items => (items || []).filter(item => item.status !== 'done');
export const selectedCount = (items, selected) => liveItems(items).filter(item => item.status !== 'done' && selected.has(item.id)).length;

function boxesOf(item) {
  const ratio = item.height / item.width;
  const shown = Math.min(1, (150 / 178) / ratio);
  return (item.regions || []).flatMap(region => {
    const top = region.y / shown * 100;
    if (top > 100) return [];
    return [{ x: region.x * 100, y: top, width: region.w * 100, height: Math.min(100 - top, region.h / shown * 100), role: region.role }];
  });
}

function bytes(value) { return value > 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${Math.round(value / 1024)} KB`; }
function sourceName(source) { return source === 'phone' ? '手机' : source === 'paste' ? '剪贴板' : '电脑'; }

function gridItem(item, selected) {
  const done = item.status === 'done';
  const boxes = boxesOf(item);
  const preview = item.status === 'done' ? `→ ${item.link?.uid || ''}` : boxes.length ? `${item.regions.length} 框${item.regions.some(region => region.origin === 'ai') ? ' · AI 待确认' : ''}` : '';
  return html`<article class="crw-grid-item${selected.has(item.id) ? ' is-selected' : ''}${done ? ' is-done' : ''}" data-key="${item.id}">
    <label class="crw-grid-item__check"><input type="checkbox" data-change="create.gridSelect" data-arg="${item.id}" aria-label="选择 ${item.file}"${selected.has(item.id) ? html` checked` : ''}${done ? html` disabled` : ''}></label>
    <span class="crw-grid-item__source">${sourceName(item.source)}</span>
    <button type="button" class="crw-grid-item__open" data-action="create.gridOpen" data-arg="${item.id}" aria-label="${done ? '查看' : '处理'} ${item.file}">
      <span class="crw-grid-item__thumb"><img src="/api/inbox/raw?id=${encodeURIComponent(item.id)}" alt="" loading="lazy">
        ${boxes.length ? html`<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">${boxes.map(box => html`<rect x="${box.x}" y="${box.y}" width="${box.width}" height="${box.height}" data-role="${box.role}"></rect>`)}</svg>` : ''}
        ${item.height / item.width > 2 ? html`<span class="crw-grid-item__tall">长图 ${item.width}×${item.height}</span>` : ''}
      </span>
      <span class="crw-grid-item__body"><strong title="${item.file}">${item.file}</strong>
        <span class="crw-grid-item__sub">${item.width}×${item.height} · ${bytes(item.bytes)}<span>${String(item.uploaded_at || '').slice(5, 16).replace('T', ' ')}</span></span>
        <span class="crw-grid-item__status"><b data-status="${item.status}">${STATUS[item.status] || item.status}</b>${preview ? html`<small>${preview}</small>` : ''}</span>
      </span>
    </button>
  </article>`;
}

export function gridView({ items = [], selected = new Set(), filter = 'all', stage = 'upload', busy = false, error = '' } = {}) {
  const live = liveItems(items);
  const shown = visibleItems(items, filter);
  const selectable = selectableItems(shown);
  const count = selectedCount(items, selected);
  return html`<div class="crw-inbox">
    <div class="crw-inbox__head">
      <label class="crw-inbox__all"><input type="checkbox" data-change="create.gridAll" aria-label="全选当前筛选图片"${selectable.length && selectable.every(item => selected.has(item.id)) ? html` checked` : ''}>全选当前筛选</label>
      <span class="crw-inbox__count">${shown.length} / ${live.length} 张</span>
      <div class="crw-inbox__filters" role="group" aria-label="收件箱状态筛选">${FILTERS.map(([key, label]) => button({ label, size: 'sm', variant: filter === key ? 'primary' : 'default', action: 'create.gridFilter', arg: key, pressed: filter === key }))}</div>
    </div>
    ${error ? html`<p class="crw-inbox__error" role="alert">${error}</p>` : ''}
    <div class="crw-inbox__grid">${each(shown, item => item.id, item => gridItem(item, selected))}${shown.length ? '' : html`<p class="crw-inbox__empty">这个筛选下没有图片。<br>从手机或电脑上传截图后会出现在这里。</p>`}</div>
    <div class="crw-inbox__help"><section><h3>${icon('upload')}手机直接上传</h3><p>同一 Wi-Fi 下用手机浏览器打开 <code id="ib-lan-url">http://&lt;本机局域网 IP&gt;:8471/m</code>（需在「设置 → 访问与安全」打开允许外部访问，启动时控制台会打印地址）。手机端只上传不裁剪，进的就是这个收件箱。</p></section>
      <section><h3>这一步做什么</h3><p>收件箱是<strong>暂存区</strong>，不写题库、不进 Ledger。原图存在 <code>错题/.omrs/inbox/raw/</code>；即使题目之后转成文本、不再需要图，原图和你框的位置也留作训练数据（「AI 训练」页可导出）。</p><p>勾选几张后底部会出现批量操作：<strong>AI 框选</strong>只对勾选的图跑；<strong>整图即题目</strong>适合已裁好的题图。</p></section></div>
    <div class="crw-inbox__batch${count && stage === 'upload' ? ' is-open' : ''}" role="group" aria-label="已选图片批量操作">
      <strong>${count} 张已选</strong>
      ${button({ label: 'AI 框选', action: 'create.gridDetect', disabled: busy || !count })}
      ${button({ label: '整图即题目', action: 'create.gridWhole', disabled: busy || !count })}
      ${button({ label: '去处理', variant: 'primary', action: 'create.gridOpenSelected', disabled: busy || !count })}
      ${button({ label: '丢弃', variant: 'danger', action: 'create.gridDiscard', disabled: busy || !count })}
      ${button({ label: '清空选择', action: 'create.gridClear', disabled: busy || !count })}
    </div>
  </div>`;
}
