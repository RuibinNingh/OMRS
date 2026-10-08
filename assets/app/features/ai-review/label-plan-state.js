/** 整批修订只保留原目标；表单与逐题分页独立于服务端审批版本。 */
export const isLabelPlan = item => item?.tool === 'propose_label_plan';
export function labelPlanValues(item) {
  return { label_changes: (item.payload?.label_changes || []).map(op => {
    const after = item.preview?.label_changes?.find(p => p.change_id === op.change_id)?.after;
    return { change_id: op.change_id, enabled: op.enabled,
      ...(after ? { name: after.name, color: after.color, order: after.order } : {}) };
  }), question_changes: (item.payload?.question_changes || []).map(q => ({ question_id: q.question_id, enabled: q.enabled, add: [...q.add], remove: [...q.remove] })), excluded_question_ids: [] };
}
export function editLabelPlan(edited, kind, id, field, value) {
  const out = structuredClone(edited);
  if (kind === 'exclude') {
    out.excluded_question_ids = value ? [...new Set([...out.excluded_question_ids, id])] : out.excluded_question_ids.filter(q => q !== id);
    return out;
  }
  const row = (kind === 'definition' ? out.label_changes : out.question_changes).find(r => (r.change_id || r.question_id) === id);
  if (!row) return out;
  if (field === 'enabled') row.enabled = Boolean(value);
  else if (kind === 'definition' && ['name', 'color', 'order'].includes(field)) row[field] = field === 'order' ? Number(value) : String(value);
  else if (['add', 'remove'].includes(field)) {
    const [ref, checked] = value;
    row[field] = checked ? [...new Set([...row[field], ref])] : row[field].filter(v => v !== ref);
    const other = field === 'add' ? 'remove' : 'add';
    if (checked) row[other] = row[other].filter(v => v !== ref);
  }
  return out;
}
export function planRefs(item) {
  const defs = new Map();
  for (const op of item.payload?.label_changes || []) {
    defs.set(op.action === 'create' ? op.key : op.label_id, { ref: op.action === 'create' ? op.key : op.label_id,
      name: op.name || item.preview?.label_changes?.find(p => p.change_id === op.change_id)?.before?.name || op.label_id });
    if (op.into) defs.set(op.into, { ref: op.into, name: item.preview?.label_changes?.find(p => p.label_id === op.into)?.after?.name || op.into });
  }
  for (const q of item.original_payload?.question_changes || item.payload?.question_changes || []) {
    for (const ref of [...q.add, ...q.remove]) if (!defs.has(ref)) defs.set(ref, { ref, name: ref });
  }
  return [...defs.values()].map(value => ({ ...value, name: item.preview?.allowed_labels?.find(label => label.ref === value.ref)?.name || value.name }));
}
export function pageOf(items, page = 0, size = 25) {
  const count = Math.max(1, Math.ceil(items.length / size));
  const current = Math.max(0, Math.min(count - 1, page));
  return { items: items.slice(current * size, (current + 1) * size), page: current, pages: count, total: items.length };
}
