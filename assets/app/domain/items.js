/**
 * 题目列表（过渡期适配器）：全站共用的筛选语义（题库、调度、导出、即时练习）仍在旧 core.js 的 filterItems()，
 * 这里只组装筛选条件并转调；到期天数同理转调 getDueDays()。数据所有权反转（P6）时换实现。
 * facets() 是纯函数：从题目列表取科目 / 分类 / 知识点选项，排序与旧 populateFilterOptions() 一致。
 */
const g = globalThis;

export const itemsOf = data => (Array.isArray(data?.items) ? data.items : []);

/** 练习用的筛选条件：只放开科目、分类、知识点、标记；停用题照旧排除，不排序（保留推荐顺序）。 */
export function practiceFilters({ subject = '', category = '', ktag = '', labels = [], labelMode = 'any' } = {}) {
  return {
    text: '', subject, category, tag: '', knowledgeTag: ktag, labels: [...labels], labelMode,
    difficultyMin: 0, difficultyMax: 10, masteryMin: null, masteryMax: null, dueFilter: '', suspended: '', sort: 'none',
  };
}

export function filterPractice(items, filters) {
  const list = Array.isArray(items) ? items : [];
  return typeof g.filterItems === 'function' ? g.filterItems(list, practiceFilters(filters)) : [...list];
}

/** 题库页用：全部题目（旧 getItems() 的副本）、按 uid 取题、按筛选条件过滤排序（旧 filterItems，语义与调度 / 导出共用）。 */
export const allItems = () => (typeof g.getItems === 'function' ? g.getItems() : []);
export const itemOf = uid => (typeof g.getItemByUid === 'function' ? g.getItemByUid(String(uid || '')) : null) || {};
export function filterAll(items, filters) {
  const list = Array.isArray(items) ? items : [];
  return typeof g.filterItems === 'function' ? g.filterItems(list, filters) : [...list];
}

export const dueDays = item => (typeof g.getDueDays === 'function' ? g.getDueDays(item) : null);

const zh = (a, b) => a.localeCompare(b, 'zh-CN');
const uniq = values => [...new Set(values.filter(Boolean))].sort(zh);

export function facets(items) {
  const list = Array.isArray(items) ? items : [];
  return {
    subjects: uniq(list.map(item => item.subject)),
    categories: uniq(list.map(item => item.category)),
    ktags: uniq(list.flatMap(item => item.knowledge_tags || [])),
  };
}
