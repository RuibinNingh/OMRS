/** 按标记追加展示板引用，使用确认时的稳定身份快照。 */
import { questionRefs } from '../../domain/question/ref.js';
import { syncBody } from './view.js';

export function createBoardLabelSync({ detail, flush, deps, postBoard, reloadData, toast }) {
  async function syncLabel(preferred = '') {
    if (!detail()) return;
    // 加题同步会在服务端追加引用；先落盘本地待保存的 items，避免随后重读用旧快照覆盖新题。
    if (!(await flush())) return;
    const defs = deps.labels();
    if (!defs.length) { toast('还没有标记，先在题目上打一个「考前必看」之类的标记', { kind: 'warn' }); return; }
    let label = preferred && defs.some(item => item.name === preferred) ? preferred : '';
    if (!label) {
      const current = detail().source_labels?.[0] || '';
      const res = await deps.dialog({
        title: '按标记同步', okText: '同步到展示板', focus: '[data-dialog-ok]',
        hint: '把带有该标记、且还不在板里的题目追加到末尾；之后新打的标记不会自动进板，需要时再同步一次。',
        body: syncBody(defs, current),
      });
      if (!res.ok) return;
      label = defs.find((item, index) => res.values[`bd-sync-${index}`] === true)?.name;
    }
    if (!label) return;
    if (!(await flush())) return;   // 对话框关闭后再查一次：同步追加前没有新的脏字段或在途保存
    const refs = questionRefs(deps.items().filter(item => !item.suspended && (item.labels || []).includes(label)));
    try {
      const result = refs.length ? await postBoard('/api/board/items/add', { id: detail().id, question_refs: refs }) : { board: { added: 0 } };
      if (!preferred) await postBoard('/api/board/update', { id: detail().id, source_labels: [label] });
      await reloadData();
      toast(result.board.added ? `已同步 ${result.board.added} 道「${label}」题目` : `没有带「${label}」的新题目`);
    } catch (error) { toast(`同步标记失败：${error.message}`, { kind: 'error' }); }
  }

  return syncLabel;
}
