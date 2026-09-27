/** 收件箱上传入口：文件拖放、选择和显式读取剪贴板。 */
import { html } from '../../core/html.js';
import { filedrop } from '../../ui/filedrop.js';
import { button } from '../../ui/button.js';

export function uploadView() {
  return html`<div class="crw-upload">
    ${filedrop({ id: 'ib-file', title: '拖入或粘贴多张截图，也可以点击选择文件',
      hint: '整张作业帮截图直接丢进来，不用先裁。相同图片自动合并。', accept: 'image/*', multiple: true })}
    <div class="crw-upload__actions">
      ${button({ label: '从剪贴板读取', icon: 'copy', action: 'create.clipboard' })}
      <span id="ib-up-status" class="crw-upload__status" role="status" aria-live="polite"></span>
    </div>
  </div>`;
}
