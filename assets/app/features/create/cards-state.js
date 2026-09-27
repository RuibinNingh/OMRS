/** 题卡工作区的纯函数：就绪题卡清单、字段归一、写入路径、预览类型与创建汇总。 */
import { groupCards } from './process-state.js';

export const newCardForm = () => ({ subject: '', category: '', difficulty: 5, tags: [], labels: [], cause: '', page: '', classified: false });
export const cardKey = (id, card) => `${id}#${card}`;

export function parseKey(key) {
  const text = String(key || '');
  const at = text.lastIndexOf('#');
  return { id: text.slice(0, at), card: Number(text.slice(at + 1)) };
}

const splitList = value => String(value || '').split(/[,，]/).map(part => part.trim()).filter(Boolean);

/**
 * 待创建的题卡：status=ready 的每张图按题卡分组，已创建（created_uid）的跳过。
 * 与旧 ibReadyCards 相同，缺表单的题卡就地补一份默认表单（之后的字段保存要写回 item.cards）。
 */
export function readyCards(items = []) {
  const out = [];
  for (const item of items) {
    if (item.status !== 'ready') continue;
    if (!item.cards || typeof item.cards !== 'object') item.cards = {};
    for (const [card, regions] of groupCards(item)) {
      const slot = String(card);
      if (!item.cards[slot]) item.cards[slot] = newCardForm();
      const form = item.cards[slot];
      if (!Array.isArray(form.labels)) form.labels = splitList(form.labels);
      if (!form.created_uid) out.push({ key: cardKey(item.id, card), item, card, regions, form });
    }
  }
  return out;
}

/** 表单字段的存储形态：难度为数字，知识点与标记为去重数组，其余原样。 */
export function cardValue(field, value) {
  if (field === 'difficulty') return Math.min(10, Math.max(1, Number(value) || 5));
  if (field === 'tags' || field === 'labels') return [...new Set(splitList(value))];
  return String(value ?? '');
}

export const tagText = tags => (Array.isArray(tags) ? tags.join(', ') : String(tags || ''));

export function targetPath(form = {}) {
  const subject = form.subject || '科目';
  const category = form.category || '分类';
  return `→ 错题/${subject}/${category}/${category}N.md`;
}

export const regionKinds = regions => regions.map(region => (region.convert === 'text' ? '文本' : '图片')).join(' + ');
export const allText = regions => regions.every(region => region.role === 'ignore' || region.convert === 'text');
export const missingRequired = form => !String(form.subject || '').trim() || !String(form.category || '').trim();

/** 已有题目里的科目、分类与知识点，供表单 datalist 提示（快速录入与题卡共用）。 */
export function suggestions(items = []) {
  const unique = values => [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN'));
  return {
    subjects: unique(items.map(item => item.subject)),
    categories: unique(items.map(item => item.category)),
    tags: unique(items.flatMap(item => [item.category, ...(item.knowledge_tags || [])])),
  };
}

export function commitSummary(created, failed) {
  return `已创建 ${created} 道题目${failed ? `，${failed} 张失败` : ''}；原图与框位已存入数据集`;
}
