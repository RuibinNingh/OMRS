/** 领域影响预览：只使用服务端已经核对的快照。 */
import { html, raw } from '../../core/html.js';
import { button } from '../../ui/button.js';
import { renderMd } from '../../domain/question/index.js';

const list = values => (values || []).join('、') || '（无）';
const text = value => value ? html`<div class="q-md">${raw(renderMd(value))}</div>` : html`<p class="arv-muted">（空）</p>`;
function snapshotImage(block, images) {
  const source = images.find(image => (image.sha256 || image.image_sha) === block.image_sha) || {};
  const width = source.width || 1, height = source.height || 1, box = block.box || { x: 0, y: 0, w: 1, h: 1 };
  return html`<svg class="arv-draft-image" role="img" aria-label="${block.section}裁图预览" viewBox="${box.x * width} ${box.y * height} ${box.w * width} ${box.h * height}">
    <image href="/api/drafts/image?sha=${encodeURIComponent(block.image_sha)}" width="${width}" height="${height}"></image></svg>`;
}
export function draftSnapshot(preview) {
  return html`<section class="arv-draft-snapshot"><h3>草稿 ${preview.draft_id} · 第 ${preview.revision} 版</h3>
    <dl class="arv-facts"><div><dt>科目 / 分类</dt><dd>${preview.subject} / ${preview.category}</dd></div><div><dt>难度</dt><dd>${preview.difficulty}</dd></div>
      <div><dt>知识点</dt><dd>${list(preview.knowledge_points)}</dd></div><div><dt>标记</dt><dd>${list(preview.labels)}</dd></div></dl>
    <h4>错因</h4>${text(preview.cause)}<h4>补充备注</h4>${text(preview.note)}
    <div class="arv-draft-blocks">${(preview.blocks || []).map(block => html`<section class="arv-draft-block"><h4>${block.section} · ${block.kind === 'image' ? '图片' : '文字'}</h4>
      ${block.kind === 'image' ? snapshotImage(block, preview.source_images || []) : text(block.text)}${block.note ? html`<p class="arv-muted">${block.note}</p>` : ''}</section>`)}</div>
    <p class="arv-muted">只审批此版本；编辑草稿后须重新发起入库审核。</p>
    ${button({ label: '打开草稿编辑器', action: 'ai-review.openDraft', arg: preview.draft_id })}</section>`;
}
export function relatedPreview(item) {
  const p = item.preview || {}, rows = p.items || [];
  return html`${p.uid ? html`<p>题目：${p.uid}${p.path ? ` · ${p.path}` : ''}</p>` : ''}
    ${p.subject || p.category ? html`<p>科目 / 分类：${p.subject || ''} / ${p.category || ''}</p>` : ''}
    ${p.from || p.to ? html`<div class="arv-diff"><div><h4>当前位置</h4><p>${p.from}</p></div><div class="arv-after"><h4>移至</h4><p>${p.to}</p></div></div>` : ''}
    ${p.reason || item.payload?.reason || item.actor?.reason ? html`<p>原因：${p.reason || item.payload?.reason || item.actor.reason}</p>` : ''}${p.message ? html`<p>${p.message}</p>` : ''}
    ${p.user_statement ? html`<blockquote>${p.user_statement}</blockquote>` : ''}
    ${p.session_id ? html`<p>复习计划：${p.session_id}${p.session_left != null ? `；提交后剩余 ${p.session_left} 道待反馈` : ''}</p>` : ''}
    ${rows.length ? html`<section class="arv-related"><h3>涉及 ${rows.length} 道题目</h3>${rows.map(row => html`<section class="arv-change"><h4>${row.uid || row.question_id || row.label || '关联题目'}</h4>
      ${row.subject || row.category ? html`<p>${row.subject || ''} / ${row.category || ''}${row.source ? ` · ${row.source === 'proficiency' ? '熟练度' : '到期推荐'}` : ''}</p>` : ''}
      ${row.before || row.after ? html`<div class="arv-diff"><div><h4>当前标记</h4><p>${list(row.before)}</p></div><div class="arv-after"><h4>修改后标记</h4><p>${list(row.after)}</p></div></div>` : ''}
      ${row.is_correct != null ? html`<p>${row.is_correct ? '答对' : '答错'} · 自评分 ${row.sub_score}</p>` : ''}
      ${row.mastery_before != null ? html`<p>预计熟练度：${Math.round(row.mastery_before * 100)}% → ${Math.round(row.mastery_after * 100)}%${row.state ? ` · ${row.state}` : ''}</p>` : ''}</section>`)}</section>` : ''}`;
}
