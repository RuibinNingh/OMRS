/**
 * Markdown 编辑器（ui/dialog --xl，P5 第 3 轮起；原 questions.js 的 .modal#md-editor）。
 * 从题目弹窗、反馈台、即时练习、题库「⋯」的「编辑」打开；从题目弹窗打开时是叠上去的第二个模态对话框。
 * - 保存：POST /api/question/markdown → 清详情缓存 → 旧 reloadData() → 失效重绘挂着该题的 qview；失败时留在编辑器里，状态行写原因。
 *   内容没改时「保存」直接关闭，不写文件。Ctrl / ⌘ + Enter 保存（ui/overlay 的 onEnter）。
 * - 有未保存的修改时 Esc / 点遮罩不关（dismissible 为函数），状态行提示；「取消」与关闭按钮照常关闭（显式放弃）。
 * - 关闭后焦点回到「编辑」按钮；保存后 qview 重绘换掉了原按钮时，交给同一挂载点里新的「编辑」按钮。
 */
import { questionRef, questionItem } from './ref.js';
import { html } from '../../core/html.js';
import { get, post } from '../../core/api.js';
import { toast } from '../../ui/toast.js';
import { dialog, closeDialog } from '../../ui/dialog.js';
import { reloadData } from '../data.js';
import { qvInvalidate, dropDetail } from './mount.js';

const ID = 'md-editor';
const byId = () => (typeof document !== 'undefined' ? document.getElementById(ID) : null);

export const editorOpen = () => !!byId()?.open;
export function closeEditor() { closeDialog(byId()); }

export async function openEditor(uid) {
  const item = questionItem(uid);
  const key = item?.uid || '';
  const ref = questionRef(item);
  if (!key || editorOpen()) return false;
  const opener = document.activeElement;
  const mount = opener?.closest?.('[data-qv-mount]') || null;
  const res = await get(`/api/question/raw?question_id=${encodeURIComponent(ref.question_id)}`);
  if (!res.ok || !res.data || res.data.error) {
    toast(`无法打开 Markdown：${res.error?.message || res.data?.error || '读取失败'}`, { kind: 'error' });
    return false;
  }
  const original = String(res.data.markdown || '');
  const target = res.data.uid || key;
  let dirty = false;
  let status = null;
  const say = (text, tone = '') => { if (!status) return; status.textContent = text; status.dataset.tone = tone; };
  const idle = () => say(dirty ? '有未保存的修改：Esc 不会关闭，点「取消」放弃修改' : 'Ctrl / ⌘ + Enter 保存', dirty ? 'warn' : '');
  const result = await dialog({
    id: ID,
    size: 'xl',
    title: '编辑 Markdown',
    hint: [target, res.data.file_path].filter(Boolean).join(' · '),
    okText: '保存',
    focus: '#md-edit-text',
    body: html`<textarea class="ui-textarea qv-editor__text" id="md-edit-text" spellcheck="false" autocomplete="off" aria-label="题目 Markdown">${original}</textarea>
<p class="qv-editor__status" id="md-edit-status" role="status" aria-live="polite"></p>`,
    dismissible: () => !dirty,
    returnFocus: () => (opener?.isConnected ? opener : mount?.querySelector?.('[data-qv-act="edit"]')) || null,
    onOpen(el) {
      status = el.querySelector('#md-edit-status');
      const text = el.querySelector('#md-edit-text');
      text.setSelectionRange(0, 0);
      text.scrollTop = 0;
      text.addEventListener('input', () => {
        const next = text.value !== original;
        if (next !== dirty) { dirty = next; idle(); }
      });
      idle();
    },
    async onOk(values) {
      if (!dirty) return true;
      say('保存中…');
      const out = await post('/api/question/markdown', { ...ref, markdown: String(values['md-edit-text'] ?? '') });
      if (!out.ok) { say(`保存失败：${out.error.message}`, 'error'); return false; }
      dirty = false;
      dropDetail(target);
      await reloadData();
      await qvInvalidate(target);
      toast(`已保存 ${target} 的 Markdown`, { kind: 'ok' });
      return true;
    },
  });
  return result.ok;
}
