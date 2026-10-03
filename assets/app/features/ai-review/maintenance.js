/** 草稿图片维护独立于当前选题，空待审队列仍可清理过期资源。 */
import { post } from '../../core/api.js';
import { confirm } from '../../ui/dialog.js';

export const confirmDraftCleanup = () => confirm('清理过期丢弃草稿的临时图片？', {
  hint: '仍被聊天、其他草稿或训练数据引用的图片会保留。', okText: '开始清理',
});
export async function requestDraftCleanup() {
  const result = await post('/api/drafts/cleanup', {});
  const cleaned = result.data?.cleaned || {}, retained = result.data?.retained || {};
  const summary = `已清理 ${cleaned.drafts || 0} 份过期草稿、${cleaned.images || 0} 张无引用图片、${cleaned.crops || 0} 份裁图；保留 ${retained.images || 0} 张仍被引用的图片`;
  return { result, summary };
}
