// === assets/catalog.js — 目录页：树状展示 错题/ 工作区的文件夹结构 ===
// 数据来自 GET /api/tree（只读扫盘，不写 Ledger）。后端不可用时退化为按 DATA.items
// 的 File_Path 拼一棵树，至少还能看到目录层级。
// 熟练度等学习状态不在 /api/tree 里，由本地 DATA.items 按路径前缀聚合后叠加显示。

let CATALOG_TREE = null;
let CATALOG_SUMMARY = null;
let CATALOG_OPEN = new Set();
let CATALOG_STATS = {};
let CATALOG_QUERY = '';
let CATALOG_SHOW_ALL_FILES = false;
let CATALOG_LOADED_FROM = '';

function catalogFormatSize(bytes) {
  const n = asNumber(bytes, 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

// 从 DATA.items 的路径反推一棵树，仅在 /api/tree 拿不到时使用
function catalogFallbackTree() {
  const root = { name: '错题', path: '错题', type: 'dir', children: [], files: [], question_count: 0, file_count: 0, size: 0 };
  const dirIndex = { '错题': root };
  getItems().forEach(item => {
    const parts = String(item.path || '').replace(/\\/g, '/').split('/').filter(Boolean);
    if (parts.length < 2) return;
    let cursor = root;
    let prefix = parts[0];
    for (let i = 1; i < parts.length - 1; i++) {
      prefix += `/${parts[i]}`;
      let next = dirIndex[prefix];
      if (!next) {
        next = { name: parts[i], path: prefix, type: 'dir', children: [], files: [], question_count: 0, file_count: 0, size: 0 };
        dirIndex[prefix] = next;
        cursor.children.push(next);
      }
      cursor = next;
    }
    const fileName = parts[parts.length - 1];
    cursor.files.push({ name: fileName, path: `${prefix}/${fileName}`, type: 'file', kind: 'question', size: 0, uid: item.uid, indexed: true });
  });
  const rollUp = (node) => {
    node.children.forEach(rollUp);
    node.question_count = node.files.filter(f => f.kind === 'question').length
      + node.children.reduce((sum, child) => sum + child.question_count, 0);
    node.file_count = node.files.length + node.children.reduce((sum, child) => sum + child.file_count, 0);
    node.children.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
    node.files.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'));
  };
  rollUp(root);
  return root;
}

// 按路径前缀把题目的学习状态聚合到每一层文件夹上
function catalogBuildStats() {
  const stats = {};
  const touch = (path) => {
    if (!stats[path]) stats[path] = { count: 0, masterySum: 0, killed: 0, due: 0, leech: 0 };
    return stats[path];
  };
  getItems().forEach(item => {
    const parts = String(item.path || '').replace(/\\/g, '/').split('/').filter(Boolean);
    if (parts.length < 2) return;
    const dueDays = getDueDays(item);
    const overdueOrToday = dueDays !== null && dueDays <= 0;
    let prefix = '';
    for (let i = 0; i < parts.length - 1; i++) {
      prefix = i === 0 ? parts[0] : `${prefix}/${parts[i]}`;
      const row = touch(prefix);
      row.count += 1;
      row.masterySum += asNumber(item.decayed_mastery, asNumber(item.mastery, 0));
      if (isKilledItem(item)) row.killed += 1;
      if (overdueOrToday && !isKilledItem(item)) row.due += 1;
      if (item.is_leech) row.leech += 1;
    }
  });
  return stats;
}

async function loadCatalog(force) {
  const box = document.getElementById('catalog-tree');
  if (CATALOG_TREE && !force) { renderCatalog(); return; }
  if (box) box.innerHTML = '<div class="empty-inline">加载目录中…</div>';
  try {
    const result = await api('/api/tree');
    CATALOG_TREE = result.root || null;
    CATALOG_SUMMARY = result.summary || null;
    CATALOG_LOADED_FROM = 'api';
  } catch (error) {
    CATALOG_TREE = catalogFallbackTree();
    CATALOG_SUMMARY = null;
    CATALOG_LOADED_FROM = 'fallback';
  }
  if (CATALOG_TREE && !CATALOG_OPEN.size) {
    // 默认展开根和第一层，再深就让用户自己点，避免一进来就是一屏
    CATALOG_OPEN.add(CATALOG_TREE.path);
    (CATALOG_TREE.children || []).forEach(child => CATALOG_OPEN.add(child.path));
  }
  renderCatalog();
}

function catalogMatches(node, query) {
  if (!query) return true;
  if (node.name.toLowerCase().includes(query)) return true;
  if ((node.files || []).some(file => file.name.toLowerCase().includes(query))) return true;
  return (node.children || []).some(child => catalogMatches(child, query));
}

function catalogToggle(path) {
  if (CATALOG_OPEN.has(path)) CATALOG_OPEN.delete(path); else CATALOG_OPEN.add(path);
  renderCatalog();
}
function catalogExpandAll() {
  const walk = (node) => { CATALOG_OPEN.add(node.path); (node.children || []).forEach(walk); };
  if (CATALOG_TREE) walk(CATALOG_TREE);
  renderCatalog();
}
function catalogCollapseAll() {
  CATALOG_OPEN = new Set(CATALOG_TREE ? [CATALOG_TREE.path] : []);
  renderCatalog();
}
function catalogSearch(value) {
  CATALOG_QUERY = String(value || '').trim().toLowerCase();
  renderCatalog();
}
function catalogToggleAllFiles(checked) {
  CATALOG_SHOW_ALL_FILES = !!checked;
  renderCatalog();
}
async function catalogOpenQuestion(uid) {
  if (typeof viewQ === 'function') await viewQ(uid);
}
async function catalogCopyPath(path) {
  const ok = await copyTextToClipboard(path);
  const status = document.getElementById('catalog-status');
  if (status) status.textContent = ok ? `已复制路径：${path}` : `复制失败，路径：${path}`;
}

function catalogFileRow(file, depth) {
  const isQuestion = file.kind === 'question';
  const icon = isQuestion ? '📄' : file.kind === 'image' ? '🖼' : file.kind === 'markdown' ? '📝' : '📎';
  const item = isQuestion && file.uid ? getItemByUid(file.uid) : null;
  let right = '';
  if (item) {
    const mastery = asNumber(item.mastery, 0);
    const color = mastery > 0.8 ? 'var(--green)' : mastery > 0.4 ? 'var(--yellow)' : 'var(--red)';
    const dueDays = getDueDays(item);
    const due = dueDays === null ? '' : dueDays < 0 ? `<span class="tree-due overdue">逾期${Math.abs(dueDays)}天</span>`
      : dueDays === 0 ? '<span class="tree-due today">今日到期</span>' : '';
    right = `${due}<span class="m-bar"><span class="m-bar-fill" style="width:${mastery * 100}%;background:${color}"></span></span><span class="tree-num">${(mastery * 100).toFixed(0)}%</span>`;
  } else if (isQuestion && file.indexed === false) {
    right = '<span class="tree-due warn">未入库</span>';
  } else if (file.size) {
    right = `<span class="tree-num">${catalogFormatSize(file.size)}</span>`;
  }
  const openable = isQuestion && file.uid && item;
  return `<div class="tree-row tree-file${openable ? ' clickable' : ''}" style="--depth:${depth}"${openable ? ` onclick="catalogOpenQuestion('${escapeAttr(file.uid)}')"` : ''}>
    <span class="tree-caret"></span>
    <span class="tree-ico">${icon}</span>
    <span class="tree-name">${escapeHtml(file.name)}</span>
    <span class="tree-right">${right}</span>
  </div>`;
}

function catalogDirRow(node, depth) {
  const open = CATALOG_OPEN.has(node.path) || !!CATALOG_QUERY;
  const stat = CATALOG_STATS[node.path];
  const avg = stat && stat.count ? stat.masterySum / stat.count : null;
  const color = avg === null ? 'var(--bg4)' : avg > 0.8 ? 'var(--green)' : avg > 0.4 ? 'var(--yellow)' : 'var(--red)';
  const badges = [];
  if (node.question_count) badges.push(`<span class="tree-badge">${node.question_count} 题</span>`);
  if (stat && stat.due) badges.push(`<span class="tree-badge due">${stat.due} 待复习</span>`);
  if (stat && stat.leech) badges.push(`<span class="tree-badge leech">${stat.leech} 顽固</span>`);
  const bar = avg === null ? '' :
    `<span class="m-bar"><span class="m-bar-fill" style="width:${avg * 100}%;background:${color}"></span></span><span class="tree-num">${(avg * 100).toFixed(0)}%</span>`;

  const childrenHtml = open ? [
    ...(node.children || []).filter(child => catalogMatches(child, CATALOG_QUERY)).map(child => catalogDirRow(child, depth + 1)),
    ...(node.files || [])
      .filter(file => CATALOG_SHOW_ALL_FILES || file.kind === 'question')
      .filter(file => !CATALOG_QUERY || file.name.toLowerCase().includes(CATALOG_QUERY) || node.name.toLowerCase().includes(CATALOG_QUERY))
      .map(file => catalogFileRow(file, depth + 1)),
  ].join('') : '';

  return `<div class="tree-row tree-dir${open ? ' open' : ''}" style="--depth:${depth}" onclick="catalogToggle('${escapeAttr(node.path)}')">
      <span class="tree-caret">${open ? '▾' : '▸'}</span>
      <span class="tree-ico">${open ? '📂' : '📁'}</span>
      <span class="tree-name">${escapeHtml(node.name)}</span>
      <span class="tree-badges">${badges.join('')}</span>
      <span class="tree-right">${bar}<button class="tree-copy" title="复制相对路径" onclick="event.stopPropagation();catalogCopyPath('${escapeAttr(node.path)}')">⧉</button></span>
    </div>${childrenHtml}`;
}

function renderCatalog() {
  const box = document.getElementById('catalog-tree');
  const head = document.getElementById('catalog-stat');
  if (!box) return;
  if (!CATALOG_TREE) { box.innerHTML = '<div class="empty-inline">还没有加载目录。</div>'; return; }

  CATALOG_STATS = catalogBuildStats();
  const summary = CATALOG_SUMMARY || {
    dirs: (function count(node) { return (node.children || []).length + (node.children || []).reduce((sum, c) => sum + count(c), 0); })(CATALOG_TREE),
    files: CATALOG_TREE.file_count || 0,
    questions: CATALOG_TREE.question_count || 0,
    size: CATALOG_TREE.size || 0,
    orphans: 0,
  };
  if (head) {
    const cells = [
      ['文件夹', summary.dirs],
      ['题目文件', summary.questions],
      ['全部文件', summary.files],
      ['占用', catalogFormatSize(summary.size)],
    ];
    head.innerHTML = cells.map(([label, value]) =>
      `<div class="stat-card"><div class="stat-label">${label}</div><div class="stat-value">${escapeHtml(String(value))}</div></div>`
    ).join('');
  }

  box.innerHTML = catalogDirRow(CATALOG_TREE, 0);

  const status = document.getElementById('catalog-status');
  if (status) {
    const parts = [];
    if (CATALOG_LOADED_FROM === 'fallback') parts.push('后端未响应，当前树由题库路径推算，只包含题目文件。');
    if (summary.orphans) parts.push(`${summary.orphans} 个题目文件还没进题库，点顶栏「重新扫描」可以收进来。`);
    if (summary.truncated) parts.push('目录层级过深，已截断显示。');
    if (CATALOG_QUERY) parts.push(`正在筛选「${CATALOG_QUERY}」。`);
    status.textContent = parts.join(' ');
  }
}
