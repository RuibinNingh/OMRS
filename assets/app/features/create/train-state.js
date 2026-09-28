/** AI 训练工作区的纯函数：数据集统计的展示模型、框选策略表单与提交体。 */
export const LAYOUT_NAMES = Object.freeze({ zuoyebang: '作业帮截图', photo: '拍照 / 扫描', plain: '已裁好的题图', other: '其他' });
export const PROVIDERS = Object.freeze([
  { value: 'vlm', label: 'vlm — 设置里的多模态模型（联网）' },
  { value: 'template', label: 'template — 版式模板（零联网）' },
  { value: 'local_http', label: 'local_http — 本地检测服务（训好的 YOLO/ONNX）' },
]);
export const FORMATS = Object.freeze([
  { value: 'omrs_jsonl', label: 'OMRS JSONL（归一化框）' },
  { value: 'yolo', label: 'YOLO txt + JSONL' },
]);

export const percent = value => (value == null ? '—' : `${Math.round(value * 100)}%`);
const shown = value => (value == null ? '—' : value);
export const bytes = value => (value > 1048576 ? `${(value / 1048576).toFixed(1)} MB` : `${Math.round((value || 0) / 1024)} KB`);

export function statsModel(stats) {
  const s = stats || {};
  const boxes = s.boxes || {};
  const ai = s.ai || {};
  const convert = s.convert || {};
  const blind = s.blind || {};
  const storage = s.storage || {};
  const total = Math.max(1, s.images || 0);
  const decisions = Math.max(1, (convert.text || 0) + (convert.image || 0));
  return {
    cards: [
      { id: 'imgs', label: '已留存原图', value: shown(s.images), hint: `已录入 ${shown(s.done)} · 含已转文本不再需要图的题` },
      { id: 'boxes', label: '人工确认的框', value: shown(boxes.total), hint: `题目 ${shown(boxes.question)} · 答案 ${shown(boxes.answer)} · 忽略 ${shown(boxes.ignore)}` },
      { id: 'adopt', label: 'AI 框选采纳率', value: percent(ai.adoption_rate), hint: `AI 建议 ${shown(ai.suggested)} · 直接采纳 ${shown(ai.adopted)} · 微调 ${shown(ai.edited)}（IoU ${shown(ai.mean_iou_edited)}）· 拒绝 ${shown(ai.rejected)}` },
      { id: 'agree', label: '转文本判断一致率', value: percent(convert.agreement_rate), hint: `AI 判断 ${shown(convert.judged)} 次，与人工最终选择一致 ${shown(convert.agree)}` },
    ],
    layouts: Object.entries(s.layouts || {}).sort((a, b) => b[1] - a[1])
      .map(([key, count]) => ({ key, label: LAYOUT_NAMES[key] || key, count, value: Math.round(count / total * 100) })),
    convert: [
      { key: 'text', label: '转文本', count: convert.text || 0, value: Math.round((convert.text || 0) / decisions * 100), tone: 'info' },
      { key: 'image', label: '保留图片', count: convert.image || 0, value: Math.round((convert.image || 0) / decisions * 100), tone: 'success' },
    ],
    blind: blind.images
      ? `盲标 ${blind.images} 张（已评估 ${blind.evaluated}，待画 ${blind.pending}）· 隐藏 AI 框 ${blind.ai_boxes} 个，IoU≥0.5 命中 ${blind.matched}，平均 IoU ${shown(blind.mean_iou)}`
      : '还没有盲标样本：在下方把「每 N 张盲标」设为大于 0 后，AI 框选会按间隔隐藏建议',
    storage: `原图 ${bytes(storage.raw_bytes || 0)} · 裁图缓存 ${bytes(storage.crops_bytes || 0)} · 已丢弃待清理 ${storage.discarded || 0} 张`,
    chat: `聊天来源图 ${shown(s.chat?.images ?? 0)} 张 · 标注框 ${shown(s.chat?.boxes ?? 0)} 个（同图去重）`,
  };
}

/** /api/config → 表单值（字符串，直接进输入框）。 */
export function policyForm(config = {}) {
  return {
    provider: config.inbox_detect_provider || 'vlm',
    local: config.inbox_local_detect_url || '',
    blind: String(config.inbox_blind_every || 0),
    conf: String(config.inbox_auto_ready_conf || 0),
    upload: !!config.inbox_auto_on_upload,
    days: String(config.inbox_discard_keep_days == null ? 7 : config.inbox_discard_keep_days),
  };
}

/** 表单 → POST /api/config 的 inbox_* 键；数值夹到合法范围（与旧 ibSavePolicy 相同）。 */
export function policyPayload(form) {
  return {
    inbox_detect_provider: form.provider,
    inbox_local_detect_url: String(form.local || '').trim(),
    inbox_blind_every: Math.max(0, parseInt(form.blind, 10) || 0),
    inbox_auto_ready_conf: Math.max(0, Math.min(1, parseFloat(form.conf) || 0)),
    inbox_auto_on_upload: !!form.upload,
    inbox_discard_keep_days: Math.max(0, parseInt(form.days, 10) || 0),
  };
}

export const exportHref = format => `/api/inbox/dataset/export?format=${encodeURIComponent(format || 'omrs_jsonl')}`;

export function cleanupSummary(result, crops) {
  return `已清理：超过 ${result.discarded_days} 天的已丢弃原图 ${result.raw} 张（${bytes(result.raw_bytes || 0)}）${crops ? `，裁图缓存 ${result.crops} 个` : ''}`;
}
