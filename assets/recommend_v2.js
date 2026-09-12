// === assets/recommend_v2.js — 优化后的推荐调度系统 ===
/* ══════════════════════════════════════════════════════════
   优化后的推荐面板 - 单列表显示，智能均衡推荐
   ══════════════════════════════════════════════════════════ */

// 全局状态
let REC_DATA_V2 = null;  // 推荐数据
let REC_SELECTED_V2 = {};  // 已选题目 {uid: true}
let REC_VIEW_V2 = 'flat';  // 视图模式: flat | gallery

function showRecommendPanelV2(){
  document.getElementById('recommend-panel-v2').style.display='block';
  document.getElementById('export-panel').style.display='none';
  document.getElementById('btn-regular-review').classList.add('primary');
  document.getElementById('btn-export').classList.remove('primary');
  loadRecommendationsV2();
}

function isRecSelectedV2(uid){return !!REC_SELECTED_V2[uid]}
function getRecSelectedCountV2(){return Object.keys(REC_SELECTED_V2).length}
function getRecSelectedUidsV2(){return Object.keys(REC_SELECTED_V2)}

/**
 * 智能均衡推荐算法
 * - 优先推荐到期题目
 * - 在科目间均衡分配
 * - 考虑熟练度、难度、EF等多个维度
 */
async function loadRecommendationsV2(){
  const subjectFilter = document.getElementById('rec-subject-v2').value || '';
  const practiceMode = document.getElementById('rec-practice-mode').value || 'balanced';
  const status = document.getElementById('rec-status-v2');

  status.textContent = '加载推荐中...';

  try {
    // 获取所有符合条件的题目
    const params = new URLSearchParams();
    if (subjectFilter) params.set('subject', subjectFilter);

    // 请求大量题目用于智能筛选（不限制数量）
    params.set('due_count', '1000');
    params.set('prof_count', '1000');

    // 获取标记筛选
    const filters = recV2GetFilterState();
    if (filters.labels && filters.labels.length > 0) {
      filters.labels.forEach(label => params.append('label', label));
    }

    const rawData = await api(`/api/recommend?${params.toString()}`);

    // 调试：检查API返回的数据
    console.log('API返回数据:', rawData);
    console.log('到期题目数:', (rawData.due || []).length);
    console.log('熟练度题目数:', (rawData.proficiency || []).length);

    // 合并到期和熟练度列表
    const allItems = [
      ...(rawData.due || []).map(item => ({...item, _source: 'due', _priority_boost: 1.5})),
      ...(rawData.proficiency || []).map(item => ({...item, _source: 'proficiency', _priority_boost: 1.0}))
    ];

    console.log('合并后题目数:', allItems.length);

    // 根据练习模式进行智能推荐
    let recommended = [];

    if (practiceMode === 'balanced') {
      // 均衡模式：科目间均衡分配
      recommended = intelligentBalancedRecommend(allItems, subjectFilter);
    } else if (practiceMode === 'weak') {
      // 薄弱模式：优先推荐薄弱科目
      recommended = weaknessBasedRecommend(allItems, subjectFilter);
    } else if (practiceMode === 'due') {
      // 到期模式：只推荐到期题目
      recommended = allItems.filter(item => item._source === 'due');
    } else {
      // 全部模式：展示所有题目
      recommended = allItems;
    }

    console.log('推荐后题目数:', recommended.length);

    REC_DATA_V2 = recommended;
    REC_SELECTED_V2 = {};
    renderUnifiedListV2();

    status.innerHTML = `<span style="color:var(--green)">✓ 推荐 ${recommended.length} 道题目</span>`;
  } catch (e) {
    status.innerHTML = `<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`;
  }
}

/**
 * 智能均衡推荐算法
 * 在科目间均衡分配题目，避免某个科目完全不推
 */
function intelligentBalancedRecommend(items, subjectFilter) {
  if (!items || items.length === 0) return [];

  // 按科目分组
  const bySubject = {};
  items.forEach(item => {
    const subject = item.subject || '未知';
    if (!bySubject[subject]) bySubject[subject] = [];
    bySubject[subject].push(item);
  });

  // 为每个科目计算综合优先级并排序
  Object.keys(bySubject).forEach(subject => {
    bySubject[subject].sort((a, b) => {
      const priorityA = calculateItemPriority(a);
      const priorityB = calculateItemPriority(b);
      return priorityB - priorityA;  // 降序
    });
  });

  // 轮询方式从各科目抽取题目，确保均衡
  const result = [];
  const subjects = Object.keys(bySubject);
  const maxPerSubject = Math.ceil(items.length / subjects.length);

  let round = 0;
  let hasMore = true;

  while (hasMore && result.length < items.length) {
    hasMore = false;

    for (const subject of subjects) {
      const subjectItems = bySubject[subject];
      if (round < subjectItems.length) {
        result.push(subjectItems[round]);
        hasMore = true;
      }
    }

    round++;
  }

  return result;
}

/**
 * 薄弱优先推荐算法
 * 优先推荐薄弱科目的题目
 */
function weaknessBasedRecommend(items, subjectFilter) {
  if (!items || items.length === 0) return [];

  // 按科目分组并计算平均熟练度
  const bySubject = {};
  items.forEach(item => {
    const subject = item.subject || '未知';
    if (!bySubject[subject]) {
      bySubject[subject] = {items: [], totalMastery: 0};
    }
    bySubject[subject].items.push(item);
    bySubject[subject].totalMastery += asNumber(item.mastery, 0);
  });

  // 计算每个科目的平均熟练度（薄弱程度）
  const subjectWeakness = [];
  Object.keys(bySubject).forEach(subject => {
    const data = bySubject[subject];
    const avgMastery = data.totalMastery / data.items.length;
    subjectWeakness.push({
      subject,
      avgMastery,
      weakness: 1 - avgMastery,  // 熟练度越低，薄弱程度越高
      items: data.items
    });
  });

  // 按薄弱程度排序科目
  subjectWeakness.sort((a, b) => b.weakness - a.weakness);

  // 从最薄弱的科目开始，每个科目取一定比例
  const result = [];
  subjectWeakness.forEach((subjectData, idx) => {
    // 薄弱科目取更多题目
    const proportion = 1.5 / (idx + 1);  // 第一个科目取最多，逐渐减少
    const count = Math.max(3, Math.floor(subjectData.items.length * proportion));

    // 对科目内题目按优先级排序
    const sorted = subjectData.items.sort((a, b) =>
      calculateItemPriority(b) - calculateItemPriority(a)
    );

    result.push(...sorted.slice(0, count));
  });

  return result;
}

/**
 * 计算单个题目的综合优先级
 * 综合考虑：到期状态、熟练度、难度、EF、失败次数等
 */
function calculateItemPriority(item) {
  let priority = 0;

  // 1. 到期加成（最重要）
  if (item._source === 'due') {
    priority += 100 * item._priority_boost;

    // 逾期天数加成
    if (item._overdue_days > 0) {
      priority += item._overdue_days * 10;
    }
  }

  // 2. 熟练度权重（熟练度越低优先级越高）
  const mastery = asNumber(item.mastery, 0);
  priority += (1 - mastery) * 50;

  // 3. 难度权重（难度越高稍微提高优先级）
  const difficulty = asNumber(item.difficulty, 5);
  priority += difficulty * 3;

  // 4. EF权重（EF越低越不稳定，优先级越高）
  const ef = asNumber(item.ef, 2.5);
  priority += (3.0 - ef) * 20;

  // 5. 失败次数权重（顽固题）
  if (item.fail_count) {
    priority += item.fail_count * 15;
  }

  // 6. 久未复习加成
  if (item.last_review) {
    const daysSince = daysSinceDate(item.last_review);
    if (daysSince > 30) {
      priority += Math.min(50, daysSince - 30);
    }
  }

  // 7. 标签加成
  if (item.labels && item.labels.length > 0) {
    priority += item.labels.length * 2;
  }

  return priority;
}

function daysSinceDate(dateStr) {
  if (!dateStr) return 999;
  try {
    const date = new Date(dateStr);
    const today = new Date();
    return Math.floor((today - date) / (1000 * 60 * 60 * 24));
  } catch {
    return 999;
  }
}

function setRecViewV2(view) {
  REC_VIEW_V2 = view;
  document.getElementById('rec-view-flat-v2').classList.toggle('active', view === 'flat');
  document.getElementById('rec-view-gallery-v2').classList.toggle('active', view === 'gallery');
  renderUnifiedListV2();
}

function renderUnifiedListV2() {
  if (!REC_DATA_V2) return;

  const filtered = applyRecFiltersV2(REC_DATA_V2);
  const container = document.getElementById('rec-unified-list-v2');

  if (filtered.length === 0) {
    container.innerHTML = '<div class="empty-inline">暂无符合条件的题目</div>';
    updateRecSummaryV2(0);
    return;
  }

  if (REC_VIEW_V2 === 'gallery') {
    container.innerHTML = renderGalleryViewV2(filtered);
    hydrateGalleryPreviewsV2();
  } else {
    container.innerHTML = renderFlatViewV2(filtered);
  }

  updateRecSummaryV2(filtered.length);
}

function renderFlatViewV2(items) {
  // 类似题库的平铺表格式显示
  return `<div class="qb-table-like">
    ${items.map((item, idx) => {
      const selected = isRecSelectedV2(item.uid);
      const masteryPct = (asNumber(item.mastery, 0) * 100).toFixed(0);
      const masteryColor = asNumber(item.mastery, 0) > 0.8 ? 'var(--green)' :
                          asNumber(item.mastery, 0) > 0.4 ? 'var(--yellow)' : 'var(--red)';
      const ef = asNumber(item.ef, 2.5).toFixed(2);
      const priority = calculateItemPriority(item).toFixed(0);

      // 到期标记
      let dueBadge = '';
      if (item._source === 'due') {
        const overdueDays = item._overdue_days || 0;
        if (overdueDays > 0) {
          dueBadge = `<span class="due-badge overdue">逾期${overdueDays}天</span>`;
        } else if (overdueDays === 0) {
          dueBadge = `<span class="due-badge today">今日到期</span>`;
        }
      }

      const tagLabel = (item.tag || '').replace(/#/g, '');

      return `<div class="rec-row-v2 ${selected ? 'selected' : ''}" data-uid="${escapeAttr(item.uid)}">
        <div class="rec-checkbox">
          <input type="checkbox" ${selected ? 'checked' : ''}
                 onchange="toggleRecSelectionV2('${escapeAttr(item.uid)}')"
                 onclick="event.stopPropagation()">
        </div>
        <div class="rec-main" onclick="viewQ('${escapeAttr(item.uid)}')">
          <div class="rec-row-header">
            <span class="uid-badge">${idx + 1}. ${escapeHtml(item.uid)}</span>
            ${dueBadge}
            <span class="priority-badge" title="综合优先级">P: ${priority}</span>
          </div>
          <div class="rec-row-meta">
            ${escapeHtml(item.subject || '')} · ${escapeHtml(item.category || '')} ·
            难度 ${escapeHtml(item.difficulty)} · EF ${ef} ·
            <span class="tag ${(item.tag || '').includes('已击杀') ? 'kill' : 'attack'}">${escapeHtml(tagLabel)}</span>
            ${recLabelsHtml(item)}
          </div>
        </div>
        <div class="rec-metrics">
          <div class="metric-item">
            <div class="metric-label">熟练度</div>
            <div class="metric-bar">
              <div class="metric-fill" style="width:${masteryPct}%;background:${masteryColor}"></div>
            </div>
            <div class="metric-value">${masteryPct}%</div>
          </div>
        </div>
        <div class="rec-actions">
          <button class="btn sm" onclick="event.stopPropagation();viewQ('${escapeAttr(item.uid)}')">详情</button>
          <button class="btn sm ${selected ? 'danger' : 'primary'}"
                  onclick="event.stopPropagation();toggleRecSelectionV2('${escapeAttr(item.uid)}')">
            ${selected ? '移除' : '选择'}
          </button>
        </div>
      </div>`;
    }).join('')}
  </div>`;
}

function renderGalleryViewV2(items) {
  return `<div class="gallery-grid">
    ${items.map((item, idx) => {
      const selected = isRecSelectedV2(item.uid);
      const masteryPct = (asNumber(item.mastery, 0) * 100).toFixed(0);
      const masteryColor = asNumber(item.mastery, 0) > 0.8 ? 'var(--green)' :
                          asNumber(item.mastery, 0) > 0.4 ? 'var(--yellow)' : 'var(--red)';
      const ef = asNumber(item.ef, 2.5).toFixed(2);
      const priority = calculateItemPriority(item).toFixed(0);

      let dueBadge = '';
      if (item._source === 'due' && item._overdue_days != null) {
        if (item._overdue_days > 0) {
          dueBadge = `<span class="due-badge overdue">逾期${item._overdue_days}天</span>`;
        } else if (item._overdue_days === 0) {
          dueBadge = `<span class="due-badge today">今日到期</span>`;
        }
      }

      const detail = QUESTION_CACHE[item.uid];
      const previewHtml = detail ? renderMdContent(detail.question || '（无题目内容）') :
                         '<div class="preview-placeholder">正在加载题目预览…</div>';
      const tagLabel = (item.tag || '').replace(/#/g, '');

      return `<div class="gallery-card ${selected ? 'selected' : ''}">
        <div class="gallery-head">
          <div>
            <div class="uid">${idx + 1}. ${escapeHtml(item.uid)} ${dueBadge}</div>
            <div class="gallery-meta">
              ${escapeHtml(item.subject || '')} · ${escapeHtml(item.category || '')}<br>
              难度 ${escapeHtml(item.difficulty)} · EF ${ef} · 优先级 ${priority}
            </div>
            <div class="tag-row">${recLabelsHtml(item)}</div>
          </div>
          <span class="tag ${(item.tag || '').includes('已击杀') ? 'kill' : 'attack'}">${escapeHtml(tagLabel)}</span>
        </div>
        <div class="question-progress-row">
          <div class="question-progress-main">
            <span>熟练度</span>
            <span class="m-bar">
              <span class="m-bar-fill" style="width:${masteryPct}%;background:${masteryColor}"></span>
            </span>
            <span>${masteryPct}%</span>
          </div>
        </div>
        <div class="gallery-preview" data-rec-preview-uid-v2="${escapeAttr(item.uid)}">${previewHtml}</div>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
          <button class="btn sm" onclick="viewQ('${escapeAttr(item.uid)}')">查看详情</button>
          <button class="btn sm ${selected ? 'danger' : 'primary'}"
                  onclick="toggleRecSelectionV2('${escapeAttr(item.uid)}')">
            ${selected ? '移除' : '选择'}
          </button>
        </div>
      </div>`;
    }).join('')}
  </div>`;
}

async function hydrateGalleryPreviewsV2() {
  const nodes = [...document.querySelectorAll('.gallery-preview[data-rec-preview-uid-v2]')];
  await Promise.all(nodes.map(async node => {
    const uid = node.dataset.recPreviewUidV2;
    if (!uid) return;
    const detail = await ensureQuestionDetail(uid);
    if (node.dataset.recPreviewUidV2 === uid) {
      node.innerHTML = renderMdContent(detail.question || '（无题目内容）');
    }
  }));
}

function applyRecFiltersV2(items) {
  const filters = recV2GetFilterState();
  return recV2FilterItems(items.map(normalizeRecItem), filters);
}

function normalizeRecItem(item) {
  if (!item) return item;
  if (item.due_date) return item;
  const od = item._overdue_days;
  if (od == null) return item;
  const d = new Date();
  d.setDate(d.getDate() - od);
  return {...item, due_date: d.toISOString().slice(0, 10)};
}

function recLabelsHtml(item, options = {}) {
  return typeof lblChips === 'function' ? lblChips(item?.labels || [], options) : '';
}

function toggleRecSelectionV2(uid) {
  if (REC_SELECTED_V2[uid]) {
    delete REC_SELECTED_V2[uid];
  } else {
    REC_SELECTED_V2[uid] = true;
  }

  // 更新单个行的状态
  const row = document.querySelector(`.rec-row-v2[data-uid="${uid}"]`);
  if (row) {
    row.classList.toggle('selected', REC_SELECTED_V2[uid]);
    const checkbox = row.querySelector('input[type="checkbox"]');
    if (checkbox) checkbox.checked = !!REC_SELECTED_V2[uid];
  }

  updateRecSelectionBarV2();
}

function selectAllVisibleV2() {
  const filtered = applyRecFiltersV2(REC_DATA_V2 || []);
  filtered.forEach(item => {
    if (item?.uid) REC_SELECTED_V2[item.uid] = true;
  });
  renderUnifiedListV2();
  updateRecSelectionBarV2();
}

function clearSelectionV2() {
  REC_SELECTED_V2 = {};
  renderUnifiedListV2();
  updateRecSelectionBarV2();
}

function smartSelectV2() {
  // 智能选择：优先选择到期题目，然后按优先级选择
  const filtered = applyRecFiltersV2(REC_DATA_V2 || []);

  // 先选所有到期题目
  const dueItems = filtered.filter(item => item._source === 'due');
  dueItems.forEach(item => {
    if (item?.uid) REC_SELECTED_V2[item.uid] = true;
  });

  // 如果到期题目少于20道，再从熟练度列表选择优先级最高的
  if (dueItems.length < 20) {
    const profItems = filtered
      .filter(item => item._source !== 'due')
      .sort((a, b) => calculateItemPriority(b) - calculateItemPriority(a))
      .slice(0, 20 - dueItems.length);

    profItems.forEach(item => {
      if (item?.uid) REC_SELECTED_V2[item.uid] = true;
    });
  }

  renderUnifiedListV2();
  updateRecSelectionBarV2();
}

function updateRecSummaryV2(totalCount) {
  document.getElementById('rec-summary-v2').textContent =
    `共 ${totalCount} 道题目`;
}

function updateRecSelectionBarV2() {
  const count = getRecSelectedCountV2();
  const bar = document.getElementById('rec-selection-bar-v2');

  if (count > 0) {
    bar.style.display = 'flex';
    document.getElementById('rec-selected-count-v2').textContent = `已选 ${count} 道`;

    // 估算时间
    const allItems = REC_DATA_V2 || [];
    const selectedItems = allItems.filter(item => REC_SELECTED_V2[item.uid]);
    const totalTime = selectedItems.reduce((sum, item) =>
      sum + Math.max(3, Math.round(asNumber(item.difficulty, 5) * 1.5)), 0
    );
    document.getElementById('rec-est-time-v2').textContent =
      `预计 ${totalTime} 分钟`;
  } else {
    bar.style.display = 'none';
  }
}

async function confirmScheduleV2() {
  const selectedUids = getRecSelectedUidsV2();
  if (selectedUids.length === 0) {
    uiToast('请至少选择 1 道题',{kind:'warn'});
    return;
  }

  const status = document.getElementById('rec-status-v2');
  status.textContent = '生成计划中...';

  try {
    const result = await api('/api/confirm-schedule', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        selected: selectedUids.map(uid => ({uid, source: 'smart'})),
        subject: document.getElementById('rec-subject-v2').value || null
      })
    });

    status.innerHTML = `<span style="color:var(--green)">✓ Session ${escapeHtml(result.session_id)} (${result.count} 题) 已创建</span>`;

    REC_SELECTED_V2 = {};
    renderUnifiedListV2();
    updateRecSelectionBarV2();

    await refreshSessions();
  } catch (e) {
    status.innerHTML = `<span style="color:var(--red)">✕ ${escapeHtml(e.message)}</span>`;
  }
}

/* ══════════════════════════════════════════════════════════
   End 优化后的推荐面板
   ══════════════════════════════════════════════════════════ */

// === 初始化函数 ===
function initRecommendV2() {
  // 填充科目下拉框
  if (DATA && DATA.stats && DATA.stats.by_subject) {
    const subjectSelect = document.getElementById('rec-subject-v2');
    if (subjectSelect) {
      const subjects = Object.keys(DATA.stats.by_subject).sort();
      const currentValue = subjectSelect.value;
      
      subjectSelect.innerHTML = '<option value="">全部科目</option>' +
        subjects.map(s => `<option value="${escapeAttr(s)}">${escapeHtml(s)}</option>`).join('');
      
      if (currentValue && subjects.includes(currentValue)) {
        subjectSelect.value = currentValue;
      }
    }
  }

  // 填充筛选选项
  populateRecFilterOptionsV2();
}

function populateRecFilterOptionsV2() {
  if (!DATA || !DATA.stats) return;

  // 填充分类
  const categorySelect = document.getElementById('rec-filter-category-v2');
  if (categorySelect && DATA.stats.by_category) {
    const categories = Object.keys(DATA.stats.by_category).sort();
    const currentValue = categorySelect.value;
    
    categorySelect.innerHTML = '<option value="">全部分类</option>' +
      categories.map(c => `<option value="${escapeAttr(c)}">${escapeHtml(c)}</option>`).join('');
    
    if (currentValue && categories.includes(currentValue)) {
      categorySelect.value = currentValue;
    }
  }

  // 填充知识点
  const ktagSelect = document.getElementById('rec-filter-ktag-v2');
  if (ktagSelect && DATA.stats.by_ktag) {
    const ktags = Object.keys(DATA.stats.by_ktag).sort();
    const currentValue = ktagSelect.value;
    
    ktagSelect.innerHTML = '<option value="">全部知识点</option>' +
      ktags.map(k => `<option value="${escapeAttr(k)}">${escapeHtml(k)}</option>`).join('');
    
    if (currentValue && ktags.includes(currentValue)) {
      ktagSelect.value = currentValue;
    }
  }

  // 填充标记筛选
  if (typeof renderLabelFilterChips === 'function') {
    const container = document.getElementById('rec-label-filter-list-v2');
    if (container) {
      renderLabelFilterChips('rec-v2', container);
    }
  }
}

// 获取筛选状态
// V2 的筛选实现必须使用私有名称；core.js 的 getFilterState/filterItems 是
// 题库、展示板、导出和即时练习共用的公共契约，不能被推荐面板覆盖。
function recV2GetFilterState() {
  const state = {
    text: '',
    subject: document.getElementById('rec-subject-v2')?.value || '',
    category: '',
    tag: '',
    knowledgeTag: '',
    labels: [],
    labelMode: 'any',
    difficultyMin: 0,
    difficultyMax: 10,
    masteryMin: null,
    masteryMax: null,
    dueFilter: '',
    suspended: '',
    sort: 'priority'
  };

  // V2 控件使用 rec-<field>-v2 命名，不接收公共筛选函数的 prefix 参数。
  const getId = suffix => `rec-${suffix}-v2`;

  const searchEl = document.getElementById(getId('search'));
  if (searchEl) state.text = searchEl.value.toLowerCase().trim();

  const categoryEl = document.getElementById(getId('filter-category'));
  if (categoryEl) state.category = categoryEl.value;

  const tagEl = document.getElementById(getId('filter-tag'));
  if (tagEl) state.tag = tagEl.value;

  const ktagEl = document.getElementById(getId('filter-ktag'));
  if (ktagEl) state.knowledgeTag = ktagEl.value;

  const labelModeEl = document.getElementById(getId('label-mode'));
  if (labelModeEl) state.labelMode = labelModeEl.value;

  const diffMinEl = document.getElementById(getId('filter-diff-min'));
  if (diffMinEl && diffMinEl.value) state.difficultyMin = parseInt(diffMinEl.value, 10);

  const diffMaxEl = document.getElementById(getId('filter-diff-max'));
  if (diffMaxEl && diffMaxEl.value) state.difficultyMax = parseInt(diffMaxEl.value, 10);

  const masteryMinEl = document.getElementById(getId('filter-mastery-min'));
  if (masteryMinEl && masteryMinEl.value) state.masteryMin = parseInt(masteryMinEl.value, 10);

  const masteryMaxEl = document.getElementById(getId('filter-mastery-max'));
  if (masteryMaxEl && masteryMaxEl.value) state.masteryMax = parseInt(masteryMaxEl.value, 10);

  const sortEl = document.getElementById(getId('filter-sort'));
  if (sortEl) state.sort = sortEl.value;

  const dueEl = document.getElementById(getId('filter-due'));
  if (dueEl) state.dueFilter = dueEl.value;

  // 获取选中的标记
  if (typeof getActiveLabels === 'function') {
    try {
      state.labels = getActiveLabels('rec-v2');
    } catch (e) {
      console.warn('Failed to get active labels:', e);
      state.labels = [];
    }
  }

  return state;
}

// 应用筛选
function recV2FilterItems(items, filters) {
  if (!items) return [];

  return items.filter(item => {
    if (filters.suspended !== 'all' && filters.suspended !== 'suspended' && item.suspended) return false;
    if (filters.suspended === 'suspended' && !item.suspended) return false;
    // 搜索
    if (filters.text) {
      const searchable = [
        item.uid,
        item.subject,
        item.category,
        item.tag,
        ...(item.knowledge_tags || []),
        ...(item.labels || [])
      ].join(' ').toLowerCase();
      
      if (!searchable.includes(filters.text)) return false;
    }

    if (filters.subject && item.subject !== filters.subject) return false;
    // 分类
    if (filters.category && item.category !== filters.category) return false;

    // 状态标签
    if (filters.tag && !item.tag?.includes(filters.tag)) return false;

    // 知识点
    if (filters.knowledgeTag) {
      const ktags = item.knowledge_tags || [];
      if (!ktags.includes(filters.knowledgeTag)) return false;
    }

    // 标记筛选
    if (filters.labels && filters.labels.length > 0) {
      const itemLabels = item.labels || [];
      if (filters.labelMode === 'all') {
        if (!filters.labels.every(l => itemLabels.includes(l))) return false;
      } else {
        if (!filters.labels.some(l => itemLabels.includes(l))) return false;
      }
    }

    // 难度范围
    if (filters.difficultyMin != null && item.difficulty < filters.difficultyMin) return false;
    if (filters.difficultyMax != null && item.difficulty > filters.difficultyMax) return false;

    // 熟练度范围
    if (filters.masteryMin != null) {
      const masteryPct = asNumber(item.mastery, 0) * 100;
      if (masteryPct < filters.masteryMin) return false;
    }
    if (filters.masteryMax != null) {
      const masteryPct = asNumber(item.mastery, 0) * 100;
      if (masteryPct > filters.masteryMax) return false;
    }

    // 到期状态
    if (filters.dueFilter) {
      const dueDate = item.due_date ? new Date(item.due_date) : null;
      const today = new Date();
      today.setHours(0, 0, 0, 0);

      if (filters.dueFilter === 'overdue') {
        if (!dueDate || dueDate >= today) return false;
      } else if (filters.dueFilter === 'today') {
        if (!dueDate || dueDate.getTime() !== today.getTime()) return false;
      } else if (filters.dueFilter === '3days') {
        const in3Days = new Date(today);
        in3Days.setDate(in3Days.getDate() + 3);
        if (!dueDate || dueDate < today || dueDate > in3Days) return false;
      } else if (filters.dueFilter === '7days') {
        const in7Days = new Date(today);
        in7Days.setDate(in7Days.getDate() + 7);
        if (!dueDate || dueDate < today || dueDate > in7Days) return false;
      } else if (filters.dueFilter === 'future') {
        if (!dueDate || dueDate <= today) return false;
      }
    }

    return true;
  }).sort((a, b) => {
    // 排序
    if (filters.sort === 'priority') {
      return calculateItemPriority(b) - calculateItemPriority(a);
    } else if (filters.sort === 'mastery-asc') {
      return asNumber(a.mastery, 0) - asNumber(b.mastery, 0);
    } else if (filters.sort === 'mastery-desc') {
      return asNumber(b.mastery, 0) - asNumber(a.mastery, 0);
    } else if (filters.sort === 'diff-asc') {
      return asNumber(a.difficulty, 5) - asNumber(b.difficulty, 5);
    } else if (filters.sort === 'diff-desc') {
      return asNumber(b.difficulty, 5) - asNumber(a.difficulty, 5);
    } else if (filters.sort === 'date-desc') {
      const dateA = a.last_review ? new Date(a.last_review).getTime() : 0;
      const dateB = b.last_review ? new Date(b.last_review).getTime() : 0;
      return dateB - dateA;
    } else if (filters.sort === 'due-asc') {
      const dateA = a.due_date ? new Date(a.due_date).getTime() : Infinity;
      const dateB = b.due_date ? new Date(b.due_date).getTime() : Infinity;
      return dateA - dateB;
    } else if (filters.sort === 'due-desc') {
      const dateA = a.due_date ? new Date(a.due_date).getTime() : 0;
      const dateB = b.due_date ? new Date(b.due_date).getTime() : 0;
      return dateB - dateA;
    }
    return 0;
  });
}
