/** 录入入口共用的分类建议与人工编辑保护。 */
export function mergeClassification(form, result, { manual = {}, baseline = form } = {}) {
  const next = { ...form };
  const canApply = name => !manual[name] && next[name] === baseline[name];
  if (canApply('subject') && !String(next.subject || '').trim() && result.subject) next.subject = String(result.subject);
  if (canApply('category') && !String(next.category || '').trim() && result.category) next.category = String(result.category);
  if (canApply('difficulty') && result.difficulty != null && Number(result.difficulty) >= 1 && Number(result.difficulty) <= 10) {
    next.difficulty = String(result.difficulty);
  }
  if (canApply('related')) {
    const tags = String(next.related || '').split(/[,，]/).map(tag => tag.trim()).filter(Boolean);
    for (const tag of result.knowledge_tags || []) if (tag && !tags.includes(tag)) tags.push(tag);
    next.related = tags.join(', ');
  }
  return next;
}

export function suggestions(items = []) {
  const unique = values => [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  const categoriesBySubject = {};
  for (const item of items) {
    if (item.subject && item.category) (categoriesBySubject[item.subject] ||= []).push(item.category);
  }
  for (const subject of Object.keys(categoriesBySubject)) categoriesBySubject[subject] = unique(categoriesBySubject[subject]);
  return {
    subjects: unique(items.map(item => item.subject)),
    categories: unique(items.map(item => item.category)),
    tags: unique(items.flatMap(item => [item.category, ...(item.knowledge_tags || [])])),
    categoriesBySubject,
  };
}
