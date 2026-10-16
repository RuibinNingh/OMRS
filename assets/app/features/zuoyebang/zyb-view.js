/** 作业帮工作区：来源与真实后端预览并列，人工核对后创建。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { filedrop } from '../../ui/filedrop.js';
import { labelChips } from '../../domain/labels/index.js';
import { ROLES, searchRegions, regionBounds } from './zyb-state.js';
import { panelUrl, serviceStatus } from '../../domain/zuoyebang-service.js';
const action = (label, name, options = {}) => button({ label, action: `zuoyebang.zyb${name}`, ...options });
export const timeLabel = value => value ? new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) : '暂无记录';

export function roots() {
  return html`<div class="zyb-workspace">
    <header class="zyb-workspace-head"><div><h2>作业帮</h2><p class="zyb-help">上传试卷，逐题核对并录入。</p></div><div id="zyb-account"></div></header>
    <div id="zyb-status" class="zyb-status" role="status" aria-live="polite"></div>
    <section class="zyb-source">
      <div class="zyb-pane zyb-input"><div class="zyb-head"><h3>试卷原图</h3><div id="zyb-source-modes" class="zyb-actions" role="group" aria-label="图片来源模式"></div></div>
        <div id="zyb-camera-source" class="zyb-camera" data-morph="skip"><video id="zyb-video" autoplay playsinline muted hidden aria-label="实时摄像头画面"></video><span id="zyb-camera-placeholder">摄像头未开启</span></div>
        <div id="zyb-upload"></div><div id="zyb-source-preview"></div>
        <div id="zyb-paper-tools"></div><div id="zyb-paper" class="zyb-paper" data-morph="skip"></div>
        <div id="zyb-queue"></div><div id="zyb-camera-controls"></div><div id="zyb-paste"></div>
      </div>
      <details class="zyb-pane ui-disclosure"><summary>搜索与录入记录</summary><div id="zyb-history"></div></details>
    </section>
    <section class="zyb-review zyb-pane">
      <div id="zyb-candidates"></div><div id="zyb-preview"></div>
      <section id="zyb-editor"></section><div id="zyb-result"></div>
    </section>
  </div>`;
}
export function accountView(s) {
  const observations = s.session?.observations || {};
  const short = s.sessionError ? '连接失败' : s.session?.connected ? '已连接' : s.service?.api_key_configured === false ? '未配置' : '待连接';
  const panel = panelUrl(s.service);
  return html`<button type="button" class="ui-btn zyb-account-trigger" data-action="zuoyebang.zybMenu" data-arg="toggle" aria-expanded="${String(!!s.accountPanel)}" aria-controls="zyb-account-panel" aria-label="作业帮服务 · ${short}"><span>服务 · ${short}</span><span aria-hidden="true">⌄</span></button>
    ${s.accountPanel ? html`<section id="zyb-account-panel" class="zyb-account-panel zyb-pane" aria-label="作业帮服务菜单">
      ${s.accountPanel === 'records' ? html`<div class="zyb-head">${action('返回服务菜单', 'Menu', { arg: 'main', variant: 'ghost' })}<h3>会话有效期记录</h3></div>${observationsView(observations)}` : html`
      <h3>独立作业帮服务</h3><p class="zyb-help">${s.service?.mode === 'external' ? '外部网关' : '本地独立网关'} · ${s.service?.base_url || '请在设置中配置'}</p>
      ${s.sessionError ? html`<p class="zyb-error" role="alert">${s.sessionError}；连接失败不代表账号过期。${s.session ? '下面保留当前配置最近一次观察。' : '尚未取得当前配置的账号观察。'}</p>` : ''}
      <p class="zyb-help">${serviceStatus(s.session)}</p><p class="zyb-help">账号导入、扫码、刷新与密钥管理只在独立服务面板操作。</p>
      <div class="zyb-account-actions">${action('打开服务设置', 'Settings')}${panel ? html`<a class="ui-btn" href="${panel}" target="_blank" rel="noopener noreferrer">打开独立管理面板</a>` : ''}${action('会话有效期记录', 'Menu', { arg: 'records' })}</div>`}
    </section>` : ''}`;
}
function observationsView(observations) {
  return html`<div class="zyb-observations">
      <p class="zyb-help">未取得官方有效期；失效时间只能确定在最后成功与首次确认失效之间。</p>
      ${['account', 'signing'].map(name => { const part = observations[name] || {}; return html`<dl><dt>${name === 'account' ? '账号' : '签名'}最后成功</dt><dd>${timeLabel(part.last_success_at)}</dd><dt>首次确认失效</dt><dd>${timeLabel(part.first_invalid_at)}</dd></dl>`; })}
      <ul>${(observations.events || []).slice(-8).reverse().map(row => html`<li>${timeLabel(row.at)} · ${{ profile_import: '导入设备会话', login: '扫码登录', refresh: '刷新账号', verify: '检查账号', search: '搜题', qr_start: '创建二维码', qr_cancel: '取消扫码' }[row.event] || row.event} · ${{ ok: '成功', network: '网络故障', signing_session: '签名失效', login_required: '账号失效', protocol: '响应异常', upstream: '上游错误' }[row.kind] || row.kind}</li>`)}</ul>
    </div>`;
}
export function cameraView(s) {
  const active = s.camera.on || s.camera.pending, locked = !!s.busy || !!s.job, canSearch = !locked && s.session?.local_session_ready;
  if (s.sourceMode === 'upload') return html`<div class="zyb-actions">${action('开始搜题', 'Search', { icon: 'search', variant: 'primary', loading: s.busy === 'search', disabled: !s.file || !canSearch })}</div>`;
  return html`<div class="zyb-actions">
    ${active ? action('拍照搜题', 'Capture', { icon: 'image', variant: 'primary', loading: s.busy === 'capture', disabled: !s.camera.on || locked })
      : s.file ? action('开始搜题', 'Search', { icon: 'search', variant: 'primary', loading: s.busy === 'search', disabled: !canSearch }) : ''}
    ${action(active ? '关闭摄像头' : s.file ? '重拍' : '打开摄像头', 'Camera', { icon: active ? 'x' : 'eye', variant: !active && !s.file ? 'primary' : 'default', disabled: locked })}
    </div><p class="zyb-help" role="status">${active || !s.file ? s.camera.message : '照片已保留，可与候选对照或重拍。'}</p>`;
}
export function sourceModesView(s) {
  return html`${action('摄像头', 'Source', { arg: 'camera', icon: 'eye', pressed: s.sourceMode === 'camera', disabled: s.busy === 'capture' })}
    ${action('上传图片', 'Source', { arg: 'upload', icon: 'upload', pressed: s.sourceMode === 'upload', disabled: s.busy === 'capture' })}`;
}
export function sourcePreviewView(s) {
  return !s.search?.image && s.fileUrl ? html`<img class="zyb-source-image" src="${s.fileUrl}" alt="当前搜题原图"><p class="zyb-help">${s.file?.name}</p>` : html``;
}
export function uploadView(s) {
  return filedrop({ id: 'zyb-image', title: s.file || s.search ? '更换搜题图片' : '选择或拖入图片', hint: 'JPG / PNG / WebP · 不超过 8 MB', accept: 'image/jpeg,image/png,image/webp', disabled: !!s.busy || !!s.job });
}
export function pasteView(s) {
  return html`<div class="zyb-actions">${action('粘贴图片', 'Paste', { icon: 'image', disabled: !!s.busy || !!s.job })}<span class="zyb-help">Ctrl / ⌘ + V</span></div>`;
}
export function paperToolsView(s) {
  if (!s.search?.image) return html``;
  return html`<div class="zyb-head"><label class="zyb-check"><input type="checkbox" data-change="zuoyebang.zybBoxes"${s.showBoxes ? html` checked` : ''}>显示题框</label>
    ${action(s.adjusting ? '完成调整' : '调整题框', 'Adjust', { size: 'sm', pressed: s.adjusting, disabled: !!s.busy || !!s.job || !regionBounds(s) })}</div>
    ${s.adjusting ? html`<p class="zyb-help">拖动当前题框或控制点调整范围，再选择「保留原题图片」。</p>` : ''}`;
}
export function queueView(s) {
  if (!s.search) return html``;
  const rows = searchRegions(s);
  return html`<div class="zyb-question-queue" role="group" aria-label="试卷题目">${rows.map((row, i) => action(`${s.savedLocations[row.index] ? '✓ ' : ''}${String(i + 1).padStart(2, '0')}`, 'Region', { arg: row.index, pressed: row.index === s.region, disabled: !!s.busy && s.busy !== 'render' }))}</div>
    <p class="zyb-help">${rows.length ? `${rows.length} 个题目位置 · 已录入 ${Object.keys(s.savedLocations).length} 道` : '未返回题目位置，可保留整张原图录入。'}</p>
    ${rows.some(row => !regionBounds(s, row.index)) ? html`<p class="zyb-help">部分位置没有有效坐标，可通过题号核对候选。</p>` : ''}`;
}
export function candidatesView(s) {
  if (!s.search) return html`<h3>逐题核对</h3><p class="zyb-help">拍照或上传试卷后，点击原图题框查看对应候选。</p>`;
  const rows = searchRegions(s), position = rows.findIndex(row => row.index === s.region);
  const candidates = s.search.candidates.filter(candidate => Number(candidate.location) === s.region);
  return html`<div class="zyb-head"><h3>${position < 0 ? '搜题结果' : `第 ${String(position + 1).padStart(2, '0')} 题`}</h3><span class="ui-badge">${s.savedLocations[s.region] ? '已录入' : '待核对'}</span></div>
    <p class="zyb-help">${candidates.length ? `${candidates.length} 个候选，请与原题核对；选中后自动生成预览。` : '未找到匹配题目，可以保留原题图片继续录入。'}</p>
    <div class="zyb-candidates">${each(candidates, candidate => candidate.index, (candidate) => html`<button class="zyb-candidate${candidate.index === s.selected ? ' on' : ''}" type="button" data-action="zuoyebang.zybSelect" data-arg="${candidate.index}" aria-pressed="${candidate.index === s.selected}"${s.busy && s.busy !== 'render' ? html` disabled` : ''}>
      <strong>候选 ${candidates.indexOf(candidate) + 1}</strong><span>${candidate.title}</span><small>${candidate.index === s.selected ? '已选中' : '核对题干与数字'}</small></button>`)}</div>
    <div class="zyb-actions">${Number.isInteger(s.selected) && !s.render && !s.busy && !s.job ? action('重试渲染', 'Render') : ''}
      ${s.search.image ? action('保留原题图片', 'Keep', { disabled: !!s.busy || !!s.job || (s.region != null && !regionBounds(s)), icon: 'image' }) : ''}
      ${rows.length > 1 ? action('下一题', 'Next', { variant: 'ghost', disabled: !!s.busy && s.busy !== 'render' }) : ''}</div>
    ${s.search.service ? html`<details class="zyb-origin"><summary>来源信息</summary><p class="zyb-help">${s.search.service.mode === 'external' ? '外部' : '本地独立'}网关 · ${s.search.service.base_url}</p></details>` : ''}`;
}
export function previewView(s) {
  const record = s.render, image = record?.images?.[s.role];
  const failed = s.error && Number.isInteger(s.selected) && !record && !s.busy;
  return html`<div class="zyb-head"><div><h3>题目与答案</h3></div><span class="ui-badge" role="status">${s.busy === 'render' ? '正在生成' : record?.status === 'ready' ? '已生成' : failed ? '预览未完成' : '等待选择'}</span></div>
    <div class="zyb-toolbar"><div class="zyb-actions" role="group" aria-label="渲染内容">${action('题目', 'Role', { arg: 'question', pressed: s.role === 'question', disabled: !record })}${action('答案与解析', 'Role', { arg: 'answer', pressed: s.role === 'answer', disabled: !record })}</div>
      <div class="zyb-actions">${action('HTML', 'Html', { pressed: s.showHtml, disabled: !record })}${action('展开', 'Expand', { icon: 'external', disabled: !image?.url })}</div></div>
    <div class="zyb-preview-meta"><span>${s.role === 'question' ? '题目' : '答案与解析'} · PNG</span><span>${image?.width ? `${image.width} × ${image.height} px` : image?.empty ? '上游未返回答案' : '尚未生成'}</span></div>
    <div class="zyb-viewport${s.zoom === 'actual' ? ' is-actual' : ''}">
      ${s.showHtml && image ? html`<pre class="zyb-code">${image.html || '无答案正文'}</pre>` : image?.url ? html`<img id="zyb-rendered-image" src="${image.url}" width="${image.width}" height="${image.height}" alt="后端生成的完整${s.role === 'question' ? '题目' : '答案'}渲染图">` : html`<div class="zyb-empty"><strong>${s.busy === 'render' ? '正在生成所选题目的预览…' : failed ? '预览未完成，可在候选区重试' : image?.empty ? '这道题没有答案内容' : '选择候选，自动预览'}</strong><p>题目与完整答案会显示在这里。</p></div>`}
    </div>
    <div class="zyb-render-footer"><span>${record?.source_kind === 'crop' ? '按原图像素保存' : record ? '保留完整题干、公式与附图' : '保留原题内容与阅读顺序'}</span><div class="zyb-actions" role="group" aria-label="预览比例">${action('适应宽度', 'Zoom', { arg: 'fit', pressed: s.zoom === 'fit' })}${action('100%', 'Zoom', { arg: 'actual', pressed: s.zoom === 'actual' })}</div></div>
    ${record ? html`<details class="ui-disclosure zyb-render-log"><summary>本次渲染记录</summary><dl><dt>生成时间</dt><dd>${timeLabel(record.completed_at)}</dd><dt>渲染器</dt><dd>Chromium ${record.browser || ''} · ${record.engine || '既有记录'}</dd><dt>原始附图</dt><dd>${record.source_images} 张，已本地化</dd><dt>图片指纹</dt><dd>${image?.sha256 || '无答案图片'}</dd></dl></details>` : ''}`;
}
export function editorView(s) {
  if (!s.render) return html`<h3>识别与录入</h3><p class="zyb-help">完成渲染后可识别文字、公式并核对题卡。</p>`;
  const f = s.form, submitted = !!s.result, locked = submitted || s.busy === 'commit';
  return html`<div class="zyb-head"><h3>识别与录入</h3>${action('AI 识别题目与答案', 'Extract', { icon: 'sparkle', disabled: !!s.busy || submitted, loading: s.busy === 'extract' })}</div><p class="zyb-help">忠实转录原文；需要图形或无法完整转录时保留整图。识别失败可重试，也可直接按完整图片保存。</p>
    <div class="zyb-editor-sections">${ROLES.map(role => { const section = s.sections[role]; return html`<div class="zyb-section" data-key="section-${role}"><div class="zyb-head"><strong>${role === 'question' ? '题目' : '答案与解析'}</strong><div class="zyb-actions">${section.mode !== 'none' ? [action('保留图片', 'Mode', { arg: `${role}:image`, pressed: section.mode === 'image', disabled: locked }), action('使用文本', 'Mode', { arg: `${role}:text`, pressed: section.mode === 'text', disabled: locked })] : '无答案'}</div></div><p class="zyb-help">${section.reason}</p>
      ${section.mode === 'text' ? html`<label class="zyb-field">${role === 'question' ? '题目正文' : '完整答案正文'}<textarea class="ui-textarea" rows="5" data-zyb-text="${role}"${locked ? html` disabled` : ''}>${section.text}</textarea></label>` : ''}</div>`; })}</div>
    <div class="zyb-fields"><label class="zyb-field">科目 *<input class="ui-input" data-zyb-field="subject" data-combobox="subject" value="${f.subject}" autocomplete="off"${locked ? html` disabled` : ''}></label><label class="zyb-field">分类 *<input class="ui-input" data-zyb-field="category" data-combobox="category" value="${f.category}" autocomplete="off"${locked ? html` disabled` : ''}></label>
      <label class="zyb-field">难度（1–10）<input class="ui-input" type="number" min="1" max="10" data-zyb-field="difficulty" value="${f.difficulty}"${locked ? html` disabled` : ''}></label><label class="zyb-field">相关知识点<input class="ui-input" data-zyb-field="related" data-combobox="tags" value="${f.related}" placeholder="逗号分隔"${locked ? html` disabled` : ''}></label></div>
    <label class="zyb-field">错因 · 可选<textarea class="ui-textarea" rows="2" data-zyb-field="cause"${locked ? html` disabled` : ''}>${f.cause}</textarea></label><div class="zyb-actions">${labelChips(s.labels)}${action('添加标记', 'Labels', { icon: 'plus', disabled: locked })}</div>
    <div class="zyb-actionbar"><p class="zyb-help">核对无误后写入题库，图片随题干、答案分别保存。</p>${action(submitted ? '已录入题库' : '录入 OMRS', 'Commit', { variant: 'primary', disabled: !!s.busy || submitted, loading: s.busy === 'commit' })}</div>`;
}
export function historyView(s) {
  if (!s.history.length) return html`<p class="zyb-help">暂无渲染记录</p>`;
  return html`<ul class="zyb-history">${s.history.map(row => html`<li>${action(row.kind === 'search' ? `试卷 · ${row.region_count || 0} 个位置 / ${row.candidate_count || 0} 个候选` : row.candidate?.title || '图文题目', 'History', { arg: row.id, disabled: !!s.busy || row.status !== 'ready' })}<small>${timeLabel(row.created_at)} · ${row.status === 'ready' ? '已生成' : row.status === 'failed' ? row.error : '未完成'}</small></li>`)}</ul>`;
}
export function resultView(s) {
  return s.result ? html`<div class="zyb-result" role="status"><strong>${s.result.uid} 已录入</strong><span>${s.result.file_path}</span><div class="zyb-actions">${action('加入展示板', 'Board', { icon: 'plus' })}${action('在题目库查看', 'Open')}</div></div>` : html``;
}
