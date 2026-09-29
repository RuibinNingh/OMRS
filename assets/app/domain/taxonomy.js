/** 零题分类与已入库题目共用的科目分类候选。 */
import { get } from '../core/api.js';

let taxonomy = { subjects: [], categories_by_subject: {} };

export async function loadTaxonomy() {
  const response = await get('/api/taxonomy');
  if (response.ok && response.data?.taxonomy) taxonomy = response.data.taxonomy;
  return taxonomy;
}

export function mergeTaxonomy(suggestions) {
  const grouped = Object.fromEntries(Object.entries(suggestions.categoriesBySubject || {})
    .map(([subject, names]) => [subject, [...names]]));
  for (const [subject, names] of Object.entries(taxonomy.categories_by_subject || {})) {
    grouped[subject] = [...new Set([...(grouped[subject] || []), ...names])].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  }
  return { ...suggestions,
    subjects: [...new Set([...(suggestions.subjects || []), ...(taxonomy.subjects || [])])].sort((a, b) => a.localeCompare(b, 'zh-CN')),
    categoriesBySubject: grouped };
}
