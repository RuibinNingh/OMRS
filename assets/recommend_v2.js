// 复习选题：后端提供候选与来源；筛选、分科轮选和选择状态只作用于当前工作区。
let REC_DATA_V2 = null;
let REC_SELECTED_V2 = new Map();
let REC_ONLY_SELECTED = false;
let REC_REQUEST = 0;
let REC_LOADING = false;
let REC_ERROR = '';
let REC_SUBMITTING = false;
let REC_VIEW_V2 = 'list';
let REC_GALLERY_OBSERVER = null;
try { if (localStorage.getItem('omrs-schedule-view') === 'gallery') REC_VIEW_V2 = 'gallery'; } catch (_) {}

function setRecViewV2(view) {
  REC_VIEW_V2 = view === 'gallery' ? 'gallery' : 'list';
  try { localStorage.setItem('omrs-schedule-view', REC_VIEW_V2); } catch (_) {}
  renderUnifiedListV2();
}
function recMountGallery(box) {
  const mount = node => {
    if (node.isConnected) qvRender(node, node.dataset.recPreviewUid, {...QV_CARD_OPTS, clamp:8});
  };
  const nodes = box.querySelectorAll('[data-rec-preview-uid]');
  if (typeof IntersectionObserver === 'undefined') { nodes.forEach(mount); return; }
  REC_GALLERY_OBSERVER = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      REC_GALLERY_OBSERVER?.unobserve(entry.target);
      mount(entry.target);
    });
  }, {rootMargin:'240px'});
  nodes.forEach(node => REC_GALLERY_OBSERVER.observe(node));
}

const REC_FILTER_FIELDS = [
  ['rec-subject-v2', '科目'], ['rec-search-v2', '搜索'],
  ['rec-filter-category-v2', '分类'], ['rec-filter-ktag-v2', '知识点'],
  ['rec-filter-tag-v2', '状态'], ['rec-filter-due-v2', '到期'],
  ['rec-filter-diff-min-v2', '难度 ≥'], ['rec-filter-diff-max-v2', '难度 ≤'],
  ['rec-filter-mastery-min-v2', '熟练度 ≥'], ['rec-filter-mastery-max-v2', '熟练度 ≤']
];
function recEl(id) { return document.getElementById(id); }
function showRecommendPanelV2() { schShow('arrange'); }
function initRecommendV2() {
  const items = getItems().filter(item => !item.suspended);
  const unique = values => [...new Set(values.filter(Boolean))].sort((a,b) => a.localeCompare(b,'zh-CN'));
  setSelectOptions('rec-subject-v2', unique(items.map(i => i.subject)), '全部科目');
  setSelectOptions('rec-filter-category-v2', unique(items.map(i => i.category)), '全部分类');
  setSelectOptions('rec-filter-ktag-v2', unique(items.flatMap(i => i.knowledge_tags || [])), '全部知识点');
  if (typeof renderLabelFilterOptions === 'function') renderLabelFilterOptions('rec-v2');
}
async function loadRecommendationsV2() {
  const request = ++REC_REQUEST;
  REC_LOADING = true;
  REC_ERROR = '';
  renderUnifiedListV2();
  try {
    // Bulk mode returns every eligible item, excluding active plans on the server.
    const raw = await api('/api/recommend?due_count=1000&prof_count=1000');
    if (request !== REC_REQUEST) return;
    REC_DATA_V2 = [...(raw.due || []).map(i => ({...i, _source:'due'})),
      ...(raw.proficiency || []).map(i => ({...i, _source:'proficiency'}))];
    const available = new Map(REC_DATA_V2.map(i => [i.uid,i]));
    let removed = 0;
    for (const uid of REC_SELECTED_V2.keys()) {
      if (available.has(uid)) REC_SELECTED_V2.set(uid, available.get(uid));
      else { REC_SELECTED_V2.delete(uid); removed++; }
    }
    if (removed) uiToast(`${removed} 道已选题已不可安排，已移出选择。其余选择已保留。`, {kind:'warn'});
  } catch (error) {
    if (request !== REC_REQUEST) return;
    REC_ERROR = error.message;
  } finally {
    if (request === REC_REQUEST) {
      REC_LOADING = false;
      renderUnifiedListV2();
    }
  }
}
function recV2GetFilterState() {
  const value = id => recEl(id)?.value || '';
  const number = (id, fallback) => value(id) === '' ? fallback : Number(value(id));
  return {
    text:value('rec-search-v2').trim().toLowerCase(), subject:value('rec-subject-v2'),
    category:value('rec-filter-category-v2'), tag:value('rec-filter-tag-v2'),
    knowledgeTag:value('rec-filter-ktag-v2'),
    labels:typeof selectedLabelNamesFor === 'function' ? selectedLabelNamesFor('rec-v2') : [],
    labelMode:value('rec-v2-label-mode') || 'any',
    difficultyMin:number('rec-filter-diff-min-v2',1), difficultyMax:number('rec-filter-diff-max-v2',10),
    masteryMin:number('rec-filter-mastery-min-v2',null), masteryMax:number('rec-filter-mastery-max-v2',null),
    dueFilter:value('rec-filter-due-v2'), suspended:'', sort:value('rec-filter-sort-v2') || 'priority'
  };
}
function recFilterError(f) {
  if (f.difficultyMin < 1 || f.difficultyMax > 10 || f.difficultyMin > f.difficultyMax) return '难度范围应为 1–10，且下限不能大于上限。';
  if ((f.masteryMin != null && (f.masteryMin < 0 || f.masteryMin > 100)) ||
      (f.masteryMax != null && (f.masteryMax < 0 || f.masteryMax > 100)) ||
      (f.masteryMin != null && f.masteryMax != null && f.masteryMin > f.masteryMax)) return '熟练度范围应为 0–100%，且下限不能大于上限。';
  return '';
}
function recV2FilterItems(items, filters) {
  if (recFilterError(filters)) return [];
  const result = filterItems(items || [], {...filters,
    masteryMin:filters.masteryMin == null ? null : filters.masteryMin / 100,
    masteryMax:filters.masteryMax == null ? null : filters.masteryMax / 100});
  // The shared filter sorts by mastery by default; restore server rank for recommendation mode.
  if (filters.sort === 'priority') {
    const rank = new Map((items || []).map((item,index) => [item.uid,index]));
    result.sort((a,b) => rank.get(a.uid) - rank.get(b.uid));
  }
  return result;
}
function recRoundRobin(items) {
  const groups = new Map();
  for (const item of items) {
    const subject = item.subject || '未分类';
    if (!groups.has(subject)) groups.set(subject, []);
    groups.get(subject).push(item);
  }
  const result = [];
  for (let index=0; result.length<items.length; index++) {
    for (const group of groups.values()) if (group[index]) result.push(group[index]);
  }
  return result;
}
function recOrderItems(items, mode) {
  const due = items.filter(i => i._source === 'due');
  const prof = items.filter(i => i._source !== 'due');
  if (mode === 'weak') return [...prof,...due];
  if (mode === 'balanced') return [...recRoundRobin(due),...recRoundRobin(prof)];
  return [...due,...prof];
}
function applyRecFiltersV2(items) {
  const filters = recV2GetFilterState();
  const filtered = recV2FilterItems(items, filters);
  return filters.sort === 'priority' ? recOrderItems(filtered, recEl('rec-practice-mode').value) : filtered;
}
function recClearFilter(id) {
  recEl(id).value = '';
  renderUnifiedListV2();
}
function recRemoveLabel(name) {
  setSelectedLabelNamesFor('rec-v2',selectedLabelNamesFor('rec-v2').filter(n => n !== name));
  renderUnifiedListV2();
}
function recResetFilters() {
  REC_FILTER_FIELDS.forEach(([id]) => { recEl(id).value = ''; });
  recEl('rec-v2-label-mode').value = 'any';
  recEl('rec-filter-sort-v2').value = 'priority';
  setSelectedLabelNamesFor('rec-v2',[]);
  REC_ONLY_SELECTED = false;
  renderUnifiedListV2();
}
function recRenderChips() {
  const chips = REC_FILTER_FIELDS.filter(([id]) => recEl(id).value !== '').map(([id,label]) => {
    const el = recEl(id);
    const value = el.tagName === 'SELECT' ? el.selectedOptions[0]?.textContent : el.value;
    return `<button class="btn sm" onclick="recClearFilter(${jsArg(id)})" aria-label="移除${escapeAttr(label)}筛选">${escapeHtml(label)} ${escapeHtml(value)} ×</button>`;
  });
  for (const name of selectedLabelNamesFor('rec-v2')) chips.push(`<button class="btn sm" onclick="recRemoveLabel(${jsArg(name)})">标记 ${escapeHtml(name)} ×</button>`);
  if (chips.length) chips.push('<button class="btn sm" onclick="recResetFilters()">清除筛选</button>');
  recEl('rec-filter-chips').innerHTML = chips.join('');
}
function recReason(item) {
  const days = getDueDays(item);
  if (item._source === 'proficiency') return `提前巩固${days == null ? '' : ` · ${days} 天后到期`}`;
  if (days == null) return '待安排复习';
  return days < 0 ? `已逾期 ${-days} 天` : days === 0 ? '今日到期' : `${days} 天后到期`;
}
function renderUnifiedListV2() {
  if (!recEl('rec-unified-list-v2')) return;
  recRenderChips();
  const filtered = applyRecFiltersV2(REC_DATA_V2 || []);
  const shown = REC_ONLY_SELECTED ? filtered.filter(i => REC_SELECTED_V2.has(i.uid)) : filtered;
  const problem = recFilterError(recV2GetFilterState());
  recEl('rec-status-v2').innerHTML = REC_ERROR ? `推荐加载失败：${escapeHtml(REC_ERROR)} <button class="btn sm" onclick="loadRecommendationsV2()">重试</button>` : REC_LOADING ? '正在更新推荐…' : problem;
  recEl('rec-summary-v2').textContent = REC_DATA_V2 ? `当前显示 ${shown.length} 题 · 可安排 ${REC_DATA_V2.length} 题` : '正在准备推荐…';
  recEl('rec-only-selected').setAttribute('aria-pressed',String(REC_ONLY_SELECTED));
  recEl('rec-suggest').disabled = REC_LOADING || !!REC_ERROR || !!problem || !filtered.length;
  const box = recEl('rec-unified-list-v2');
  REC_GALLERY_OBSERVER?.disconnect();
  box.querySelectorAll('[data-rec-preview-uid]').forEach(node => qvRender(node, ''));
  const gallery = REC_VIEW_V2 === 'gallery';
  box.classList.toggle('sch-gallery', gallery && shown.length > 0);
  ['list','gallery'].forEach(view => {
    const button = recEl(`rec-view-${view}`);
    button.classList.toggle('active', view === REC_VIEW_V2);
    button.setAttribute('aria-pressed', String(view === REC_VIEW_V2));
  });
  if (!shown.length) {
    const active = (SESSIONS || []).filter(s => s.status === 'active').length;
    let message = REC_LOADING ? '正在读取可安排的题目…' : REC_ERROR ? '未能更新推荐，请重试。' : problem || (REC_ONLY_SELECTED ? '当前筛选内没有已选题。可关闭「只看已选」或清除筛选。' : REC_DATA_V2?.length ? '没有符合这些条件的题目，试试放宽筛选。' : '目前没有可安排的新题。');
    if (!REC_LOADING && !REC_ERROR && !REC_DATA_V2?.length && active) message += ` 还有 ${active} 个计划待完成，可以接着复习。`;
    box.innerHTML = `<div class="card sch-empty"><strong>${escapeHtml(message)}</strong>${!REC_LOADING && !REC_ERROR ? active && !REC_DATA_V2?.length ? '<button class="btn" onclick="schShow(\'plans\')">查看已有计划</button>' : '<button class="btn" onclick="recResetFilters()">清除筛选</button>' : ''}</div>`;
  } else {
    qvSetContext('schedule-pick',shown.map(i => i.uid));
    box.innerHTML = shown.map((item,index) => `<div class="sch-question ${REC_SELECTED_V2.has(item.uid)?'is-selected':''}">
      <input type="checkbox" aria-label="选择 ${escapeAttr(item.uid)}" ${REC_SELECTED_V2.has(item.uid)?'checked':''} onchange="toggleRecSelectionV2(${jsArg(item.uid)})">
      <span class="sch-number">${index+1}</span><div class="sch-question-main"><button class="sch-title" onclick="viewQ(${jsArg(item.uid)},'schedule-pick')">${escapeHtml(item.uid)}</button><div class="sch-meta">${escapeHtml(item.subject)} · ${escapeHtml(item.category)} · 难度 ${escapeHtml(item.difficulty)}${lblChips(item.labels || [])}</div></div>
      ${gallery ? `<div class="sch-gallery-preview" data-rec-preview-uid="${escapeAttr(item.uid)}"><div class="preview-placeholder">正在加载题面…</div></div>` : ''}
      <div class="sch-question-info"><span class="sch-reason ${item._source==='due'?'is-due':''}">${escapeHtml(recReason(item))}</span><span class="sch-meta">熟练度 ${Math.round(asNumber(item.mastery,0)*100)}%</span></div>
      <button class="btn sm" onclick="viewQ(${jsArg(item.uid)},'schedule-pick')">预览</button></div>`).join('');
    if (gallery) recMountGallery(box);
  }
  updateRecSelectionBarV2(filtered);
}
function toggleRecSelectionV2(uid) {
  if (REC_SELECTED_V2.has(uid)) REC_SELECTED_V2.delete(uid);
  else { const item = (REC_DATA_V2 || []).find(i => i.uid === uid); if (item) REC_SELECTED_V2.set(uid,item); }
  renderUnifiedListV2();
}
function recToggleSelected() { REC_ONLY_SELECTED = !REC_ONLY_SELECTED; renderUnifiedListV2(); }
function clearSelectionV2() { REC_SELECTED_V2.clear(); REC_ONLY_SELECTED = false; renderUnifiedListV2(); }
function selectAllVisibleV2() {
  if (REC_LOADING || REC_ERROR) return;
  applyRecFiltersV2(REC_DATA_V2 || []).forEach(i => REC_SELECTED_V2.set(i.uid,i));
  renderUnifiedListV2();
}
function smartSelectV2() {
  const input = recEl('rec-target-count');
  if (!input.reportValidity() || !Number.isInteger(Number(input.value)) || Number(input.value) < 1) return;
  const chosen = applyRecFiltersV2(REC_DATA_V2 || []).slice(0,Number(input.value));
  REC_SELECTED_V2 = new Map(chosen.map(i => [i.uid,i]));
  REC_ONLY_SELECTED = false;
  renderUnifiedListV2();
}
function updateRecSelectionBarV2(filtered = applyRecFiltersV2(REC_DATA_V2 || [])) {
  const count = REC_SELECTED_V2.size;
  const visible = new Set(filtered.map(i => i.uid));
  const hidden = [...REC_SELECTED_V2.keys()].filter(uid => !visible.has(uid)).length;
  recEl('rec-selected-count-v2').textContent = `已选 ${count} 题`;
  const time = [...REC_SELECTED_V2.values()].reduce((sum,i) => sum + Math.max(3,Math.round(asNumber(i.difficulty,5)*1.5)),0);
  recEl('rec-est-time-v2').textContent = count ? `约 ${time} 分钟 · 仅供参考` : '勾选题目，或按建议选择';
  recEl('rec-hidden-count').innerHTML = hidden ? `${hidden} 道已选题被筛选隐藏，仍会加入计划。 <button class="btn sm" onclick="recResetFilters();REC_ONLY_SELECTED=true;renderUnifiedListV2()">查看全部已选</button>` : '';
  recEl('rec-confirm').disabled = !count || REC_LOADING || !!REC_ERROR || REC_SUBMITTING;
  recEl('rec-confirm').textContent = REC_SUBMITTING ? '正在生成…' : '生成计划';
}
async function confirmScheduleV2() {
  if (REC_SUBMITTING || REC_LOADING || REC_ERROR || !REC_SELECTED_V2.size) return;
  REC_SUBMITTING = true;
  updateRecSelectionBarV2();
  try {
    const selected = [...REC_SELECTED_V2.values()].map(i => ({uid:i.uid,source:i._source}));
    const subjects = new Set([...REC_SELECTED_V2.values()].map(i => i.subject));
    const result = await api('/api/confirm-schedule',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({selected,persist:true,subject:subjects.size === 1 ? [...subjects][0] : null})});
    REC_SELECTED_V2.clear();
    REC_ONLY_SELECTED = false;
    recEl('sch-plan-filter').value = 'active';
    recEl('sch-plan-search').value = '';
    schShow('plans');
    await refreshSessions();
    await schOpenPlan(result.session_id);
    await loadRecommendationsV2();
    uiToast(`已生成 ${result.count} 题的复习计划`);
  } catch (error) {
    recEl('rec-status-v2').textContent = `生成失败：${error.message}。选择已保留；若题目已被其他计划占用，请刷新推荐。`;
  } finally {
    REC_SUBMITTING = false;
    updateRecSelectionBarV2();
  }
}
