/** 作业帮工作区：来源与真实后端预览并列，人工核对后创建。 */
import { html, each } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { filedrop } from '../../ui/filedrop.js';
import { labelChips } from '../../domain/labels/index.js';
import { ROLES } from './zyb-state.js';
const action = (label, name, options = {}) => button({ label, action: `create.zyb${name}`, ...options });
export const timeLabel = value => value ? new Date(value * 1000).toLocaleString('zh-CN', { hour12: false }) : '暂无记录';

export function roots() {
  return html`<div class="zyb-workspace">
    <header class="zyb-workspace-head"><h2>作业帮搜题</h2><div id="zyb-account"></div></header>
    <div class="zyb-source">
      <div class="zyb-capture">
      <section class="zyb-pane"><h3>摄像头 <small>后置优先</small></h3>
        <div class="zyb-camera" data-morph="skip"><video id="zyb-video" autoplay playsinline muted hidden aria-label="实时摄像头画面"></video><span id="zyb-camera-placeholder">摄像头未开启</span></div>
        <div id="zyb-camera-controls"></div><p class="zyb-help">打开后可实时预览，搜题请先选择图片。</p>
      </section>
      <section class="zyb-pane"><h3>搜题图片</h3><div id="zyb-upload"></div></section>
      </div>
      <section class="zyb-pane"><div id="zyb-candidates"></div></section>
      <details class="zyb-pane ui-disclosure"><summary>最近渲染记录</summary><div id="zyb-history"></div></details>
    </div>
    <section class="zyb-pane zyb-renderer"><div id="zyb-preview"></div></section>
    <div id="zyb-status" class="zyb-status" role="status" aria-live="polite"></div>
    <section class="zyb-pane" id="zyb-editor"></section>
    <div id="zyb-result"></div>
  </div>`;
}
export function accountView(s) {
  const data = s.session;
  const ready = data?.local_session_ready;
  const observations = data?.observations || {};
  const account = observations.account || {}, signing = observations.signing || {};
  const busy = s.busy === 'account';
  const label = !data ? '读取会话中…' : !ready ? '尚未配置设备会话' : signing.state === 'invalid' ? '签名会话已失效' : account.state === 'invalid' ? '请重新扫码登录' : account.state === 'valid' ? '账号最近核对有效' : '账号待在线核对';
  const short = !data ? '读取中' : !ready ? '未配置' : signing.state === 'invalid' ? '签名失效' : account.state === 'invalid' ? '待登录' : account.state === 'valid' ? '已登录' : '待核对';
  return html`<button type="button" class="ui-btn zyb-account-trigger" data-action="create.zybMenu" data-arg="toggle" aria-expanded="${!!s.accountPanel}" aria-controls="zyb-account-panel" aria-label="作业帮账号 · ${short}"><span>账号 · ${short}</span><span aria-hidden="true">⌄</span></button>
    ${s.accountPanel ? html`<section id="zyb-account-panel" class="zyb-account-panel zyb-pane" aria-label="作业帮账号菜单">
      ${s.accountPanel === 'records' ? html`<div class="zyb-head">${action('返回账号菜单', 'Menu', { arg: 'main', variant: 'ghost' })}<h3>会话有效期记录</h3></div>${observationsView(observations)}` : html`
      <h3>作业帮账号</h3><p class="zyb-help">${label}</p>
      ${s.sessionError ? html`<p class="zyb-error" role="alert">${s.sessionError}</p>` : ''}
      ${!ready ? html`<p class="zyb-help">首次使用需导入已验收的设备会话文件，然后扫码登录。</p>` : ''}
      <div class="zyb-account-actions">${action('扫码登录', 'Login', { disabled: !ready || !!s.busy })}${action('检查账号', 'Account', { arg: 'verify', disabled: !ready || !!s.busy })}${action('刷新账号', 'Account', { arg: 'refresh', disabled: !ready || !!s.busy })}
        <label class="zyb-profile ui-btn">导入设备会话<input type="file" id="zyb-profile" aria-label="导入设备会话" accept=".json,application/json"${busy ? html` disabled` : ''}></label>
        ${action('会话有效期记录', 'Menu', { arg: 'records' })}</div>`}
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
  return html`<div class="zyb-actions">${action(s.camera.on || s.camera.pending ? '关闭摄像头' : '打开摄像头', 'Camera', { icon: 'eye', disabled: !s.session?.has_account_credential })}</div><p class="zyb-help" role="status">${s.camera.message}</p>`;
}
export function uploadView(s) {
  return html`${filedrop({ id: 'zyb-image', title: s.file ? '更换搜题图片' : '选择或拖入搜题图片', hint: 'JPG / PNG / WebP · 不超过 8 MB', accept: 'image/jpeg,image/png,image/webp', disabled: !!s.busy })}
    ${s.fileUrl ? html`<img class="zyb-source-image" src="${s.fileUrl}" alt="当前搜题原图"><p class="zyb-help">${s.file?.name}</p>` : ''}
    <div class="zyb-actions">${action('开始搜题', 'Search', { icon: 'search', variant: 'primary', loading: s.busy === 'search', disabled: !s.file || !!s.busy || !s.session?.local_session_ready })}</div>`;
}
export function candidatesView(s) {
  if (!s.search) return html`<p class="zyb-help">搜题结果将在这里按位置、候选分别显示。</p>`;
  return html`<h4>搜题候选 <small>${s.search.candidates.length} 个</small></h4><div class="zyb-candidates">
    ${each(s.search.candidates, candidate => candidate.index, candidate => html`<button class="zyb-candidate${candidate.index === s.selected ? ' on' : ''}" type="button" data-action="create.zybSelect" data-arg="${candidate.index}" aria-pressed="${candidate.index === s.selected}"${s.busy ? html` disabled` : ''}>
      <strong>位置 ${Number(candidate.location) + 1} · 候选 ${candidate.index + 1}</strong><span>${candidate.title}</span><small>请与搜题原图核对</small></button>`)}
    </div><div class="zyb-actions">${action(s.render ? '重新渲染所选题目' : '渲染所选题目', 'Render', { disabled: !!s.busy, loading: s.busy === 'render' })}</div>`;
}
export function previewView(s) {
  const record = s.render, image = record?.images?.[s.role];
  return html`<div class="zyb-head"><div><h2>后端渲染预览</h2><p class="zyb-help">固定宽度 1080 px · 高度随全文展开 · 答案一张完整长图</p></div><span class="ui-badge">${record?.status === 'ready' ? '已实际生成' : '等待渲染'}</span></div>
    <div class="zyb-toolbar"><div class="zyb-actions" role="group" aria-label="渲染内容">${action('题目', 'Role', { arg: 'question', pressed: s.role === 'question' })}${action('答案与解析', 'Role', { arg: 'answer', pressed: s.role === 'answer' })}</div>
      <div class="zyb-actions">${action('HTML', 'Html', { pressed: s.showHtml, disabled: !record })}${action('展开', 'Expand', { icon: 'external', disabled: !image?.url })}</div></div>
    <div class="zyb-preview-meta"><span>${s.role === 'question' ? '题目' : '答案与解析'} · PNG</span><span>${image?.width ? `${image.width} × ${image.height} px` : image?.empty ? '上游未返回答案' : '尚未生成'}</span></div>
    <div class="zyb-viewport${s.zoom === 'actual' ? ' is-actual' : ''}">
      ${s.showHtml && image ? html`<pre class="zyb-code">${image.html || '无答案正文'}</pre>` : image?.url ? html`<img id="zyb-rendered-image" src="${image.url}" width="${image.width}" height="${image.height}" alt="后端生成的完整${s.role === 'question' ? '题目' : '答案'}渲染图">` : html`<div class="zyb-empty"><strong>${image?.empty ? '这道题没有答案内容' : '选好题目后，在这里查看真实渲染图'}</strong><p>附图、图片公式和字体完整加载后才生成预览。</p></div>`}
    </div>
    <div class="zyb-render-footer"><span>${record ? '字体、公式和附图已完整加载' : '保留原题内容与阅读顺序'}</span><div class="zyb-actions" role="group" aria-label="预览比例">${action('适应宽度', 'Zoom', { arg: 'fit', pressed: s.zoom === 'fit' })}${action('100%', 'Zoom', { arg: 'actual', pressed: s.zoom === 'actual' })}</div></div>
    ${record ? html`<details class="ui-disclosure zyb-render-log"><summary>本次渲染记录</summary><dl><dt>生成时间</dt><dd>${timeLabel(record.completed_at)}</dd><dt>渲染器</dt><dd>Chromium ${record.browser} · ${record.engine || '既有记录'}</dd><dt>原始附图</dt><dd>${record.source_images} 张，已本地化</dd><dt>图片指纹</dt><dd>${image?.sha256 || '无答案图片'}</dd></dl></details>` : ''}`;
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
  return html`<ul class="zyb-history">${s.history.map(row => html`<li>${action(row.candidate?.title || '图文题目', 'History', { arg: row.id, disabled: !!s.busy || row.status !== 'ready' })}<small>${timeLabel(row.created_at)} · ${row.status === 'ready' ? '已生成' : row.status === 'failed' ? row.error : '未完成'}</small></li>`)}</ul>`;
}
export function resultView(s) {
  return s.result ? html`<div class="zyb-result" role="status"><strong>${s.result.uid} 已录入</strong><span>${s.result.file_path}</span><div class="zyb-actions">${action('加入展示板', 'Board', { icon: 'plus' })}${action('在题目库查看', 'Open')}</div></div>` : html``;
}
