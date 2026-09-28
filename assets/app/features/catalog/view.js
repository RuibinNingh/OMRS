/** 目录页模板。递归节点用带 key 的 each()，展开状态不写进 DOM 全局。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { empty } from '../../ui/empty.js';
import { icon } from '../../ui/icon.js';
import { progress } from '../../ui/progress.js';
import { skeleton } from '../../ui/skeleton.js';
import { stat } from '../../ui/stat.js';
import { formatSize, matches, treeSummary } from './state.js';
import { formatPercent } from '../../core/format.js';

const tone = value => value > .8 ? 'success' : value > .4 ? 'warning' : 'danger';
const masteryOf = item => Math.max(0, Math.min(1, Number(item?.mastery) || 0));

function fileRow(file, env) {
  const item = file.kind === 'question' ? env.byUid.get(String(file.uid)) : null;
  const openable = !!(file.kind === 'question' && file.uid && item);
  const mastery = item ? masteryOf(item) : null;
  const due = item ? env.dueDays(item) : null;
  const badge = item && due != null && due <= 0
    ? html`<span class="catw-badge" data-tone="${due < 0 ? 'danger' : 'warning'}">${due < 0 ? `逾期${Math.abs(due)}天` : '今日到期'}</span>`
    : file.kind === 'question' && file.indexed === false
      ? html`<span class="catw-badge" data-tone="muted">未入库</span>` : '';
  const content = html`${icon(file.kind === 'image' ? 'image' : 'file')}<span class="catw-name">${file.name}</span>
    ${badge}<span class="catw-meter">${mastery != null ? progress({ value: mastery, max: 1, label: `${file.name} 熟练度`, tone: tone(mastery), size: 'sm' }) : ''}</span>
    <span class="catw-number">${mastery != null ? formatPercent(mastery) : file.size ? formatSize(file.size) : ''}</span>`;
  return html`<div class="catw-file" data-key="file:${file.path}">
    ${openable ? html`<button class="catw-row catw-row--file" data-action="catalog.open" data-arg="${file.uid}" title="打开题目 ${file.name}">${content}</button>`
      : html`<div class="catw-row catw-row--file">${content}</div>`}
  </div>`;
}

function folder(node, env) {
  const open = env.query || env.open.has(node.path);
  const statRow = env.stats.get(node.path);
  const average = statRow?.count ? Math.max(0, Math.min(1, statRow.masterySum / statRow.count)) : null;
  const children = (node.children || []).filter(child => matches(child, env.query));
  const files = (node.files || []).filter(file => env.showAll || file.kind === 'question')
    .filter(file => !env.query || node.name.toLocaleLowerCase().includes(env.query)
      || file.name.toLocaleLowerCase().includes(env.query));
  return html`<div class="catw-folder" data-key="dir:${node.path}">
    <div class="catw-folder__line"><button class="catw-row catw-row--dir" data-action="catalog.toggle" data-arg="${node.path}" aria-expanded="${open ? 'true' : 'false'}">
      ${icon(open ? 'chevron-down' : 'chevron-right')}${icon('folder')}<span class="catw-name">${node.name}</span>
      <span class="catw-badges">${node.question_count ? html`<span class="catw-badge">${node.question_count} 题</span>` : ''}
        ${statRow?.due ? html`<span class="catw-badge" data-tone="warning">${statRow.due} 待复习</span>` : ''}
        ${statRow?.leech ? html`<span class="catw-badge" data-tone="danger">${statRow.leech} 顽固</span>` : ''}</span>
      <span class="catw-meter">${average != null ? progress({ value: average, max: 1, label: `${node.name} 平均熟练度`, tone: tone(average), size: 'sm' }) : ''}</span>
      <span class="catw-number">${average != null ? formatPercent(average) : ''}</span>
    </button>${button({ label: `复制${node.name}的相对路径`, icon: 'copy', iconOnly: true, size: 'sm', action: 'catalog.copy', arg: node.path, title: '复制相对路径' })}</div>
    ${open ? html`<div class="catw-children">${each(children, child => child.path, child => folder(child, env))}
      ${each(files, file => file.path, file => fileRow(file, env))}</div>` : ''}
  </div>`;
}

export function view(s, items, dueDays) {
  const summary = treeSummary(s.tree, s.summary);
  const env = { open: s.open, query: s.query, showAll: s.showAll, stats: s.stats,
    byUid: new Map(items.map(item => [String(item.uid), item])), dueDays };
  const note = [s.source === 'fallback' && '后端未响应，当前树由题库路径推算，只包含题目文件。',
    summary.orphans && `${summary.orphans} 个题目文件还没进题库，点工具栏的「重新扫描」可以收进来。`,
    summary.truncated && '目录层级过深，已截断显示。', s.query && `正在筛选「${s.query}」。`].filter(Boolean).join(' ');
  const hasMatches = s.tree && matches(s.tree, s.query);
  return html`<section class="catw" data-key="catalog-view">
    <div class="catw-stats" id="catalog-stat">${[
      ['文件夹', summary.dirs], ['题目文件', summary.questions], ['全部文件', summary.files], ['占用', formatSize(summary.size)],
    ].map(([label, value]) => stat({ label, value }))}</div>
    <div class="catw-card"><header class="catw-toolbar"><div><h2>工作区目录</h2><p>目录直接读取「错题/」磁盘结构；点题目文件可打开详情。</p></div>
      <div class="catw-tools"><label class="catw-search">搜索文件夹 / 文件名<input id="catalog-search" type="search" placeholder="搜索文件夹 / 文件名…" value="${s.query}" data-input="catalog.search"></label>
        <label class="catw-check"><input type="checkbox" id="catalog-all-files" data-change="catalog.showAll"${s.showAll ? html` checked` : ''}>显示图片等其他文件</label>
        ${button({ label: '全部展开', size: 'sm', action: 'catalog.expand' })}${button({ label: '全部折叠', size: 'sm', action: 'catalog.collapse' })}
        ${button({ label: '重新读取', size: 'sm', icon: 'refresh', action: 'catalog.refresh', loading: s.loading })}
        ${button({ label: '重新扫描', size: 'sm', icon: 'refresh', action: 'app.scan', title: '把在 Obsidian 里新增或改动的题目文件收进题库' })}
      </div></header>
      ${s.error ? html`<p class="catw-alert" role="alert">目录读取失败：${s.error}。已保留可用的目录结构。</p>` : ''}
      <p class="catw-note" id="catalog-status" role="status">${s.copyMessage || note}</p>
      <div class="catw-tree" id="catalog-tree" role="tree" aria-label="工作区目录">
        ${s.loading && !s.tree ? skeleton({ lines: 4 })
          : !s.tree || !hasMatches || (!summary.files && !(s.tree.children || []).length)
            ? empty({ icon: 'folder', title: s.query ? '没有匹配的文件' : '目录里还没有文件',
              hint: s.query ? '试试别的关键词，或清空搜索。' : '在 Obsidian 中添加题目文件，然后重新读取目录。',
              action: { label: '重新读取', action: 'catalog.refresh' } })
            : folder(s.tree, env)}
      </div>
    </div>
  </section>`;
}
