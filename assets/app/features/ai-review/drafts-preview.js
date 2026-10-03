/** 审核页来源图共用站内图片预览，图序按当前草稿人工关联顺序。 */
import { openImageViewer } from '../../ui/image-viewer.js';
import { imageSha, imageUrl } from './drafts-state.js';

export function previewDraftSource(state, sha) {
  const known = new Map([...(state.draft?.source_images || []), ...(state.draft?.conversation_images || [])]
    .map(image => [imageSha(image), image]));
  const images = (state.value?.source_images || []).map((id, i) => {
    const image = known.get(id);
    return { src: imageUrl(id), label: image?.ref || `来源截图 ${i + 1}` };
  });
  const index = (state.value?.source_images || []).indexOf(sha);
  if (index >= 0) openImageViewer(images, index);
}
