/** 目录树的纯投影：磁盘结构与题目学习状态分别计算。 */

const number = (value, fallback = 0) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
};
const partsOf = item => String(item?.path || '').replace(/\\/g, '/').split('/').filter(Boolean);
const zh = (a, b) => a.name.localeCompare(b.name, 'zh-CN');

export function fallbackTree(items) {
  const root = { name: '错题', path: '错题', type: 'dir', children: [], files: [], question_count: 0, file_count: 0, size: 0 };
  const dirs = new Map([['错题', root]]);
  for (const item of items || []) {
    const parts = partsOf(item);
    if (parts.length < 2) continue;
    let cursor = root;
    let path = parts[0];
    for (const part of parts.slice(1, -1)) {
      path += `/${part}`;
      if (!dirs.has(path)) {
        const child = { name: part, path, type: 'dir', children: [], files: [], question_count: 0, file_count: 0, size: 0 };
        dirs.set(path, child);
        cursor.children.push(child);
      }
      cursor = dirs.get(path);
    }
    const name = parts.at(-1);
    cursor.files.push({ name, path: `${path}/${name}`, type: 'file', kind: 'question', size: 0, uid: item.uid, indexed: true });
  }
  function rollUp(node) {
    node.children.forEach(rollUp);
    node.children.sort(zh);
    node.files.sort(zh);
    node.question_count = node.files.filter(file => file.kind === 'question').length
      + node.children.reduce((sum, child) => sum + child.question_count, 0);
    node.file_count = node.files.length + node.children.reduce((sum, child) => sum + child.file_count, 0);
  }
  rollUp(root);
  return root;
}

export function folderStats(items, daysUntilDue) {
  const stats = new Map();
  for (const item of items || []) {
    const parts = partsOf(item);
    if (parts.length < 2) continue;
    const due = daysUntilDue(item);
    const killed = number(item.mastery) >= 1 || String(item.tag || '').includes('已击杀');
    let path = '';
    for (const part of parts.slice(0, -1)) {
      path = path ? `${path}/${part}` : part;
      const row = stats.get(path) || { count: 0, masterySum: 0, killed: 0, due: 0, leech: 0 };
      row.count += 1;
      row.masterySum += number(item.decayed_mastery, number(item.mastery));
      if (killed) row.killed += 1;
      if (!killed && due != null && due <= 0) row.due += 1;
      if (item.is_leech) row.leech += 1;
      stats.set(path, row);
    }
  }
  return stats;
}

export function treeSummary(root, supplied) {
  if (supplied) return supplied;
  function folders(node) { return (node.children || []).reduce((count, child) => count + 1 + folders(child), 0); }
  return { dirs: root ? folders(root) : 0, questions: root?.question_count || 0,
    files: root?.file_count || 0, size: root?.size || 0, orphans: 0 };
}

export function matches(node, query) {
  if (!query) return true;
  const q = String(query).toLocaleLowerCase();
  return String(node.name || '').toLocaleLowerCase().includes(q)
    || (node.files || []).some(file => file.name.toLocaleLowerCase().includes(q))
    || (node.children || []).some(child => matches(child, q));
}

export function formatSize(bytes) {
  const n = number(bytes);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function treePaths(root) {
  const paths = [];
  function visit(node) { paths.push(node.path); (node.children || []).forEach(visit); }
  if (root) visit(root);
  return paths;
}
