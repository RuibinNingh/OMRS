/**
 * 组件陈列页入口：/assets/app/gallery.html?theme=light|dark&density=comfortable|compact
 * 渲染 ui/ 全部组件的状态矩阵（design-system §4.5）；页头切换浅深色与密度（同步到地址栏，便于截图）。
 * 截图与审阅流程见 AI/frontend/components.md。
 */
import { html } from './core/html.js';
import { render } from './core/dom.js';
import { installIcons } from './ui/icon.js';
import { bindTooltips } from './ui/tooltip.js';
import { bindTabs } from './ui/tabs.js';
import { bindFileDrop } from './ui/filedrop.js';
import { segmented } from './ui/segmented.js';
import { button } from './ui/button.js';
import { SECTIONS_A } from './gallery-sections.js';
import { SECTIONS_B } from './gallery-sections-2.js';
import { DEMOS } from './gallery-demos.js';

const SECTIONS = [...SECTIONS_A, ...SECTIONS_B];
const root = document.documentElement;

function apply(theme, density) {
  root.dataset.theme = theme;
  root.dataset.density = density;
  history.replaceState(null, '', `?${new URLSearchParams({ theme, density })}${location.hash}`);
}

const params = new URLSearchParams(location.search);
apply(params.get('theme') === 'dark' ? 'dark' : 'light', params.get('density') === 'compact' ? 'compact' : 'comfortable');

const header = html`<header class="gl-top"><div><h1 class="gl-title">OMRS 组件陈列</h1><div class="gl-sub">assets/app/ui · ${SECTIONS.length} 节 · 每节覆盖默认、悬停、按下、焦点、禁用、加载、空、错误、溢出</div></div><span class="gl-spacer"></span>
${segmented({ name: 'gl-theme', label: '主题', value: root.dataset.theme, options: [{ value: 'light', label: '浅色', icon: 'sun' }, { value: 'dark', label: '深色', icon: 'moon' }] })}
${segmented({ name: 'gl-density', label: '密度', value: root.dataset.density, options: [{ value: 'comfortable', label: '舒适' }, { value: 'compact', label: '紧凑' }] })}</header>`;

const sections = SECTIONS.map(s => html`<section class="gl-section" id="s-${s.id}" aria-labelledby="h-${s.id}"><h2 id="h-${s.id}">${s.title}</h2><p class="gl-desc">${s.desc}</p>
${s.demos ? html`<div class="gl-demos">${s.demos.map(([id, label]) => button({ label, action: `demo.${id}`, size: 'sm' }))}</div>` : ''}
<div class="gl-grid">${s.cells.map(c => html`<figure class="gl-cell${c.wide ? ' is-wide' : ''}"><div class="gl-stage${c.stage ? ` ${c.stage}` : ''}">${c.content}</div><figcaption>${c.label}</figcaption></figure>`)}</div></section>`);

render(document.getElementById('gallery'), html`${header}<div class="gl-layout"><nav class="gl-nav" aria-label="组件目录">${SECTIONS.map(s => html`<a href="#s-${s.id}">${s.title}</a>`)}</nav><main class="gl-main">${sections}</main></div>`);

installIcons(document);
bindTooltips(document);
document.querySelectorAll('.gl-main .ui-tabs').forEach(bindTabs);
const live = document.getElementById('gfd-live')?.closest('[data-filedrop]');
if (live) {
  bindFileDrop(live, files => {
    render(document.getElementById('gfd-out'), html`已选择 ${files.length} 个文件：${files.map(f => f.name).join('、')}`);
  });
}
document.addEventListener('change', event => {
  if (event.target.name === 'gl-theme') apply(event.target.value, root.dataset.density);
  if (event.target.name === 'gl-density') apply(root.dataset.theme, event.target.value);
});
document.addEventListener('click', event => {
  const trigger = event.target.closest('[data-action^="demo."]');
  if (trigger) DEMOS[trigger.dataset.action.slice(5)]?.(trigger);
});
root.dataset.ready = '1';
