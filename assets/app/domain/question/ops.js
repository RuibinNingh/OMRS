/**
 * 题目操作（从旧 questions.js / qtable.js 迁入）：迁移分类、停用 / 恢复、删除、批量停用 / 恢复、批量导出 A4。
 * 题库页、题目弹窗与各处 qview 的工具按钮共用；确认与输入走 ui/dialog，结果走 ui/toast。
 * 写操作成功后：清详情缓存 → reloadData() → 失效重绘挂着该题的 qview → 通知历史动态刷新。
 * 「编辑」打开 editor.js 的 Markdown 编辑器（ui/dialog）。
 */
import { html } from '../../core/html.js';
import { post } from '../../core/api.js';
import { toast } from '../../ui/toast.js';
import { dialog, confirm } from '../../ui/dialog.js';
import { reloadData } from '../data.js';
import { notifyHistoryChanged } from '../history.js';
import { qvInvalidate, dropDetail } from './mount.js';
import { closeModal } from './modal.js';
import { openEditor } from './editor.js';
import { allItems, itemOf } from '../items.js';
import { downloadResponse } from '../../core/download.js';

const zh = (a, b) => a.localeCompare(b, 'zh-CN');
const uniq = values => [...new Set(values.filter(Boolean))].sort(zh);

async function afterWrite(uids, { invalidate = true } = {}) {
  await reloadData();
  if (invalidate) await Promise.all(uids.map(uid => qvInvalidate(uid)));
  notifyHistoryChanged('question');
}

export function editQuestion(uid) { return uid ? openEditor(uid) : Promise.resolve(false); }

export async function suspendQuestion(uid) {
  const ok = await confirm(`停用题目「${uid}」？`, { hint: '停用后不会进入复习调度、统计或数据分析；题目正文和历史记录会保留，可随时恢复。', okText: '停用' });
  if (!ok) return false;
  const res = await post('/api/question/suspend', { uid });
  if (!res.ok) { toast(`停用失败：${res.error.message}`, { kind: 'error' }); return false; }
  await afterWrite([uid]);
  toast(`${uid} 已停用`, { kind: 'ok' });
  return true;
}

export async function resumeQuestion(uid) {
  const res = await post('/api/question/resume', { uid });
  if (!res.ok) { toast(`恢复失败：${res.error.message}`, { kind: 'error' }); return false; }
  await afterWrite([uid]);
  toast(`${uid} 已恢复`, { kind: 'ok' });
  return true;
}

export async function deleteQuestion(uid) {
  const ok = await confirm(`删除题目「${uid}」？`, {
    hint: '这会删除题目的 Markdown 正文，并在 Ledger 中追加归档记录。历史反馈仍会保留，但题目正文无法通过 Ledger 恢复；附件图片不会删除。',
    okText: '删除', danger: true,
  });
  if (!ok) return false;
  const res = await post('/api/question/delete', { uid });
  if (!res.ok) { toast(`删除失败：${res.error.message}`, { kind: 'error' }); return false; }
  dropDetail(uid);
  closeModal();
  await afterWrite([uid], { invalidate: false });
  toast(`${uid} 已删除`, { kind: 'ok' });
  return true;
}

export async function moveQuestion(uid) {
  const item = itemOf(uid);
  const all = allItems();
  const subjects = uniq(all.map(i => i.subject));
  const categories = uniq(all.map(i => i.category));
  const res = await dialog({
    title: `迁移「${uid}」到其他分类`, okText: '迁移', focus: '#qop-mv-category', size: 'md',
    hint: '迁移会改名（UID 按目标分类重新编号）并保留 question_id 与全部历史；展示板引用按 question_id 自动跟随。',
    body: html`<div class="qop-form">
      <label class="ui-field__label" for="qop-mv-subject">科目</label>
      <input class="ui-input" id="qop-mv-subject" list="qop-mv-subjects" value="${item.subject || ''}" autocomplete="off">
      <datalist id="qop-mv-subjects">${subjects.map(s => html`<option value="${s}"></option>`)}</datalist>
      <label class="ui-field__label" for="qop-mv-category">分类</label>
      <input class="ui-input" id="qop-mv-category" list="qop-mv-categories" value="${item.category || ''}" placeholder="目标分类" autocomplete="off">
      <datalist id="qop-mv-categories">${categories.map(c => html`<option value="${c}"></option>`)}</datalist>
    </div>`,
  });
  if (!res.ok) return false;
  const subject = String(res.values['qop-mv-subject'] || '').trim() || item.subject;
  const category = String(res.values['qop-mv-category'] || '').trim();
  if (!category) { toast('目标分类不能为空', { kind: 'warn' }); return false; }
  if (subject === item.subject && category === item.category) return false;
  const out = await post('/api/question/move', { uid, subject, category });
  if (!out.ok) { toast(`迁移失败：${out.error.message}`, { kind: 'error' }); return false; }
  dropDetail(uid);
  await afterWrite([], { invalidate: false });
  toast(`${uid} 已迁移为 ${out.data?.uid || '新 UID'}`, { kind: 'ok' });
  return true;
}

/** 批量停用 / 恢复：已停用的恢复，其余停用；逐题调用，失败计数。返回是否执行。 */
export async function batchSuspend(uids) {
  const list = uids.map(itemOf).filter(item => item.uid);
  if (!list.length) return false;
  const toSuspend = list.filter(item => !item.suspended).length;
  const ok = await confirm(`停用 ${toSuspend} 道 / 恢复 ${list.length - toSuspend} 道题？`, { hint: '停用后不进入调度与统计，可随时恢复；正文与历史都保留。', okText: '执行' });
  if (!ok) return false;
  let failed = 0;
  for (const item of list) {
    const res = await post(item.suspended ? '/api/question/resume' : '/api/question/suspend', { uid: item.uid });
    if (!res.ok) failed += 1;
  }
  await afterWrite(list.map(item => item.uid));
  toast(failed ? `完成，但有 ${failed} 道题失败` : `已处理 ${list.length} 道题`, { kind: failed ? 'warn' : 'ok' });
  return true;
}

/** 批量导出 A4（不含答案）：服务端生成自包含 HTML，经旧 export.js 的 downloadExportResponse 触发下载。 */
export async function exportA4(uids) {
  if (!uids.length) return false;
  try {
    const response = await fetch('/api/export', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ uids, format: 'a4', include_answers: false }) });
    if (!response.ok) {
      let message = '导出失败';
      try { message = (await response.json()).msg || message; } catch (error) { /* 非 JSON 错误页 */ }
      throw new Error(message);
    }
    await downloadResponse(response, 'OMRS-题库筛选-a4.html');
    toast(`已导出 ${uids.length} 道题的 A4 打印版`, { kind: 'ok' });
    return true;
  } catch (error) {
    toast(`导出失败：${error.message}`, { kind: 'error' });
    return false;
  }
}
