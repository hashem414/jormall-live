const fmt = new Intl.NumberFormat('en-US');
let lastRows = [];
let ageBounds = { min: 17, max: 80 };
let maxMode = false;
let recommendationInFlight = false;
let currentResultState = null;
let resultSyncController = null;
let resultSyncPromise = Promise.resolve();

function $(id) { return document.getElementById(id); }

function numberFromInput(id, fallback = 0) {
  const el = $(id);
  if (!el) return fallback;
  const digits = String(el.value || '').replace(/,/g, '').replace(/[^0-9]/g, '');
  if (!digits) return fallback;
  return Number(digits);
}

function formatCountInput(id) {
  const el = $(id);
  if (!el) return;
  const raw = String(el.value || '').replace(/,/g, '').replace(/[^0-9]/g, '');
  el.value = raw ? fmt.format(Number(raw)) : '';
}

function setOptions(id, values) {
  const el = $(id);
  el.innerHTML = '';
  values.forEach(v => {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    if (v === 'Any') opt.selected = true;
    el.appendChild(opt);
  });
  renderTagOptions(id, values);
}

function tagPanelId(id) { return `${id}Options`; }
function tagLabelId(id) { return `${id}Tags`; }

function renderTagOptions(id, values) {
  const panel = $(tagPanelId(id));
  if (!panel) return;
  panel.innerHTML = values.map((v, idx) => `
    <label class="tag-option">
      <input type="checkbox" value="${escapeHtml(v)}" ${idx === 0 || v === 'Any' ? 'checked' : ''}>
      <span>${escapeHtml(v)}</span>
    </label>
  `).join('');
  panel.addEventListener('click', (event) => event.stopPropagation());
  panel.querySelectorAll('input[type="checkbox"]').forEach((chk) => {
    chk.addEventListener('change', () => handleTagChange(id, chk));
  });
  const button = document.querySelector(`.tag-select[data-select-id="${id}"] .tag-select-button`);
  if (button) {
    button.addEventListener('click', (event) => {
      event.stopPropagation();
      closeOtherTagSelects(id);
      document.querySelector(`.tag-select[data-select-id="${id}"]`)?.classList.toggle('open');
    });
  }
  updateTagSummary(id);
}

function closeOtherTagSelects(activeId = '') {
  document.querySelectorAll('.tag-select.open').forEach((wrap) => {
    if (wrap.dataset.selectId !== activeId) wrap.classList.remove('open');
  });
}

function handleTagChange(id, changed) {
  const panel = $(tagPanelId(id));
  const checks = Array.from(panel.querySelectorAll('input[type="checkbox"]'));
  const any = checks.find(chk => chk.value === 'Any');
  if (changed.value === 'Any' && changed.checked) {
    checks.forEach(chk => { if (chk.value !== 'Any') chk.checked = false; });
  } else if (changed.value !== 'Any' && changed.checked && any) {
    any.checked = false;
  }
  if (!checks.some(chk => chk.checked) && any) any.checked = true;
  syncHiddenSelect(id);
  updateTagSummary(id);
}

function syncHiddenSelect(id) {
  const el = $(id);
  if (!el) return;
  const selected = getMultiValues(id);
  Array.from(el.options).forEach(opt => { opt.selected = selected.includes(opt.value); });
}

function getMultiValues(id) {
  const panel = $(tagPanelId(id));
  if (!panel) return ['Any'];
  const values = Array.from(panel.querySelectorAll('input[type="checkbox"]:checked')).map(chk => chk.value);
  const clean = values.filter(v => v && v !== 'Any');
  return clean.length ? clean : ['Any'];
}

function setMultiValues(id, value) {
  const panel = $(tagPanelId(id));
  if (!panel) return;
  const values = Array.isArray(value) ? value : [value];
  const wanted = values.map(v => String(v || '').trim()).filter(v => v && v !== 'Any' && v !== 'NA');
  const checks = Array.from(panel.querySelectorAll('input[type="checkbox"]'));
  const available = new Set(checks.map(chk => chk.value));
  const matched = wanted.filter(v => available.has(v));
  checks.forEach(chk => {
    chk.checked = matched.length ? matched.includes(chk.value) : chk.value === 'Any';
  });
  syncHiddenSelect(id);
  updateTagSummary(id);
}

function updateTagSummary(id) {
  const label = $(tagLabelId(id));
  if (!label) return;
  const selected = getMultiValues(id);
  if (!selected.length || selected[0] === 'Any') {
    label.innerHTML = '<span class="tag-chip muted-chip">Any</span>';
    return;
  }
  const shown = selected.slice(0, 3);
  const extra = selected.length - shown.length;
  label.innerHTML = shown.map(v => `<span class="tag-chip">${escapeHtml(v)}</span>`).join('') + (extra > 0 ? `<span class="tag-chip more-chip">+${extra}</span>` : '');
}

async function api(url, options = {}) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.error?.message || data?.error || `Request failed: ${res.status}`);
  return data;
}

async function loadStatus() {
  const data = await api('/api/v2/status');
  const s = data.summary;
  $('totalRows').textContent = fmt.format(s.total_rows || 0);
  $('readyLists').textContent = fmt.format(s.ready_lists || 0);
  $('readyQuantity').textContent = fmt.format(s.total_quantity_ready || 0);
  $('rawCategories').textContent = fmt.format(s.raw_categories || 0);
  $('categoryGroups').textContent = fmt.format(s.category_groups || 0);
  $('dupeRows').textContent = fmt.format(s.duplicate_except_date_rows || 0);
  if ($('sourceDropped')) $('sourceDropped').textContent = fmt.format(s.source_excluded_lists || 0);
  if ($('engineLabel')) $('engineLabel').textContent = data.runtime_label || 'AI unavailable';
}

function titleCase(value) {
  const text = String(value || '');
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : '';
}

async function loadOptions() {
  const opt = await api('/api/v2/options');
  setOptions('category', opt.categories || ['Any']);
  setOptions('gender', opt.genders || ['Any']);
  setOptions('classFilter', opt.classes || ['Any']);
  setOptions('city', opt.cities || ['Any']);
  setOptions('area', opt.areas || ['Any']);
  ageBounds = opt.age_bounds || { min: 17, max: 80 };
  setupAgeRange(ageBounds.min, ageBounds.max);
}

function setupAgeRange(minAge, maxAge) {
  const minEl = $('ageMin');
  const maxEl = $('ageMax');
  [minEl, maxEl].forEach(el => {
    el.min = minAge;
    el.max = maxAge;
  });
  minEl.value = minAge;
  maxEl.value = maxAge;
  $('ageMinBound').textContent = minAge;
  $('ageMaxBound').textContent = maxAge;
  updateAgeRangeLabel();
}

function updateAgeRangeLabel() {
  const minEl = $('ageMin');
  const maxEl = $('ageMax');
  let lo = Number(minEl.value);
  let hi = Number(maxEl.value);
  if (lo > hi) {
    [lo, hi] = [hi, lo];
  }
  const minBound = Number(minEl.min);
  const maxBound = Number(maxEl.max);
  const left = ((lo - minBound) / Math.max(1, maxBound - minBound)) * 100;
  const right = ((hi - minBound) / Math.max(1, maxBound - minBound)) * 100;
  $('ageRangeFill').style.left = `${left}%`;
  $('ageRangeFill').style.width = `${Math.max(0, right - left)}%`;
  $('ageRangeLabel').textContent = (lo === minBound && hi === maxBound) ? 'Any age' : `${lo} - ${hi}`;
}

function resetAgeRange() {
  $('ageMin').value = ageBounds.min;
  $('ageMax').value = ageBounds.max;
  updateAgeRangeLabel();
}

function toggleMaxMode() {
  maxMode = !maxMode;
  $('maxLists').disabled = maxMode;
  $('maxLists').classList.toggle('disabled-input', maxMode);
  $('maxModeBtn').classList.toggle('active', maxMode);
  $('maxModeBtn').setAttribute('aria-pressed', String(maxMode));
  $('maxModeBtn').textContent = maxMode ? 'Max on' : 'Max';
}

function getPayload() {
  const lo = Math.min(Number($('ageMin').value), Number($('ageMax').value));
  const hi = Math.max(Number($('ageMin').value), Number($('ageMax').value));
  const ageFilterActive = lo !== Number(ageBounds.min) || hi !== Number(ageBounds.max);
  return {
    campaign_prompt: $('campaignPrompt').value,
    category: getMultiValues('category'),
    gender: getMultiValues('gender'),
    class: getMultiValues('classFilter'),
    age_range: ageFilterActive ? `${lo} - ${hi}` : 'Any',
    age_min: lo,
    age_max: hi,
    age_filter_active: ageFilterActive,
    full_age_min: ageBounds.min,
    full_age_max: ageBounds.max,
    city: getMultiValues('city'),
    area: getMultiValues('area'),
    min_quantity: numberFromInput('minQuantity', 0),
    target_quantity: $('targetQuantity') ? $('targetQuantity').value : '',
    max_lists: numberFromInput('maxLists', 30),
    max_mode: maxMode,
    candidate_scope: $('candidateScope') ? $('candidateScope').value : 'direct_adjacent_contextual',
    // Backup mechanics are automatic now; Order Processing only controls filters and target.
    include_unique_lists: true,
    allow_class_downgrade: true,
    allow_age_extension: true,
    use_allclasses_only_as_backup: true,
    enhance_count: Boolean($('targetQuantity') && String($('targetQuantity').value || '').trim() !== '' && String($('targetQuantity').value || '').trim() !== '0'),
    reset_ai_fields: $('resetAIFields') ? $('resetAIFields').checked : false
  };
}


function applyInterpretedFilters(filters) {
  if (!filters) return;
  setMultiValues('category', filters.desired_category);
  setMultiValues('gender', filters.desired_gender);
  setMultiValues('classFilter', filters.desired_socioeconomic_class);
  setMultiValues('city', filters.desired_city);
  setMultiValues('area', filters.desired_area);
  const age = filters.desired_age_range || 'Any';
  const m = String(age).match(/(\d{1,3})\s*-\s*(\d{1,3})/);
  if (m) {
    const lo = Math.max(ageBounds.min, Math.min(Number(m[1]), Number(m[2])));
    const hi = Math.min(ageBounds.max, Math.max(Number(m[1]), Number(m[2])));
    $('ageMin').value = lo;
    $('ageMax').value = hi;
    updateAgeRangeLabel();
  }
}


function safeUrl(value) {
  const text = String(value || '').trim();
  if (!text) return '';
  try {
    const url = new URL(text);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch (_) {
    return '';
  }
}

function renderLocationReferences(profile) {
  const refs = Array.isArray(profile.location_references) ? profile.location_references : [];
  if (!refs.length) {
    const fallback = (profile.branches || []).concat(profile.cities || []).concat(profile.areas || [])
      .filter(Boolean).slice(0, 8);
    if (!fallback.length && !profile.branches_and_coverage) return '<li>No branch/location reference found.</li>';
    return (fallback.length ? fallback : [profile.branches_and_coverage]).map(loc =>
      `<li><strong>${escapeHtml(loc)}</strong><span>Catalog reference</span></li>`
    ).join('');
  }
  return refs.slice(0, 8).map((ref) => {
    const location = ref.location || ref.branch || ref.name || 'Location';
    const cityArea = [ref.city, ref.area || ref.zone].filter(Boolean).join(' · ');
    const note = ref.note ? `<em>${escapeHtml(ref.note)}</em>` : '';
    const url = safeUrl(ref.source_url || ref.url);
    const title = ref.source_title || 'Reference';
    const link = url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(title)}</a>` : `<span>${escapeHtml(title || 'Catalog reference')}</span>`;
    return `<li><strong>${escapeHtml(location)}</strong>${cityArea ? `<small>${escapeHtml(cityArea)}</small>` : ''}${link}${note}</li>`;
  }).join('');
}

function renderBriefPoints(profile) {
  const points = Array.isArray(profile.brief_points) ? profile.brief_points.filter(Boolean).slice(0, 4) : [];
  if (!points.length) return '';
  return `<ul class="company-brief-points">${points.map(point => `<li>${escapeHtml(point)}</li>`).join('')}</ul>`;
}

function renderSourceNotes(profile) {
  const notes = Array.isArray(profile.source_notes) ? profile.source_notes.slice(0, 5) : [];
  if (!notes.length) return '';
  return `<div class="source-notes compact"><span>References</span>${notes.map(src => {
    const parts = String(src || '').split(/:\s+(https?:\/\/\S+)/);
    if (parts.length >= 3) {
      return `<small>${escapeHtml(parts[0])}: <a href="${escapeHtml(parts[1])}" target="_blank" rel="noopener noreferrer">${escapeHtml(parts[1])}</a></small>`;
    }
    return `<small>${escapeHtml(src)}</small>`;
  }).join('')}</div>`;
}

function renderCompanyConfirmation(profileInput) {
  const box = $('companyConfirmation');
  if (!box) return;
  const profiles = Array.isArray(profileInput) ? profileInput : (profileInput ? [profileInput] : []);
  const availableProfiles = profiles.filter(p => p && p.available);
  if (!availableProfiles.length) {
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  box.style.display = 'block';
  box.innerHTML = availableProfiles.map((profile) => {
    const fmtQty = fmt.format(Number(profile.total_quantity || 0));
    const categories = profile.business_category || (profile.category_groups || []).filter(Boolean).slice(0, 3).join(', ') || 'NA';
    const badge = profile.search_used ? 'Referenced company profile' : 'Catalog company profile';
    const enrichErr = profile.profile_enrichment_error ? `<div class="company-alert">Public references unavailable; catalog profile used.</div>` : '';
    const guidance = profile.location_selection_guidance || 'Use branch/area references first, then broaden only if the target count is low.';
    return `
      <div class="company-card-inner">
        <div class="company-confirm-header">
          <div>
            <span class="company-badge">${escapeHtml(badge)}</span>
            <h3>${escapeHtml(profile.company || 'Company profile')}</h3>
          </div>
          <div class="company-metrics">
            <span><strong>${fmt.format(Number(profile.lists_found || 0))}</strong> lists</span>
            <span><strong>${fmtQty}</strong> records</span>
            <span><strong>${fmt.format(Number(profile.exclusive_lists || 0))}</strong> exclusive</span>
          </div>
        </div>

        <div class="company-brief-layout">
          <div class="company-clean-summary">
            <p class="company-about-text">${escapeHtml(profile.about || '')}</p>
            ${renderBriefPoints(profile)}
            <div class="mini-insight"><span>Category</span><strong>${escapeHtml(categories)}</strong></div>
            <div class="mini-insight"><span>How to use it</span><strong>${escapeHtml(guidance)}</strong></div>
          </div>
          <div class="branch-reference-card">
            <div class="branch-reference-title">Branches / locations to consider</div>
            <ul class="branch-reference-list">${renderLocationReferences(profile)}</ul>
          </div>
        </div>

        ${renderSourceNotes(profile)}
        <div class="company-confirm-question">${escapeHtml(profile.confirmation_question || 'Confirm the branch/area references before using the suggested lists.')}</div>
        ${enrichErr}
      </div>
    `;
  }).join('');
}

function renderAppliedFilters(filters) {
  const wrap = $('appliedFilters');
  if (!wrap) return;
  const formatFilterValue = (value) => {
    if (Array.isArray(value)) return value.filter(v => v && v !== 'Any' && v !== 'NA').join(', ');
    return value;
  };
  const sourceFor = (dimension) => {
    const source = filters?.provenance?.[dimension];
    return source === 'ui' ? 'UI' : source === 'prompt' ? 'Prompt' : '';
  };
  const age = filters?.age_min == null && filters?.age_max == null
    ? ''
    : `${filters?.age_min ?? ''}${filters?.age_max == null ? '+' : ` - ${filters.age_max}`}`;
  const labels = [
    ['Category', formatFilterValue(filters?.categories), sourceFor('category')],
    ['Gender', formatFilterValue(filters?.genders), sourceFor('gender')],
    ['Class', formatFilterValue(filters?.classes), sourceFor('class')],
    ['Age', age, sourceFor('age')],
    ['City', formatFilterValue(filters?.cities), sourceFor('city')],
    ['Area', formatFilterValue(filters?.areas), sourceFor('area')],
    ['Minimum count', Number(filters?.minimum_list_count || 0) ? fmt.format(filters.minimum_list_count) : '', sourceFor('minimum_list_count')]
  ].filter(([_, value]) => value && value !== 'Any' && value !== 'NA');
  if (!labels.length) {
    wrap.innerHTML = '<span class="filter-chip"><span>Applied filters</span> None / broad search</span>';
    return;
  }
  wrap.innerHTML = labels.map(([label, value, source]) =>
    `<span class="filter-chip"><span>${escapeHtml(label)}</span> ${escapeHtml(value)}${source ? ` - Source: ${escapeHtml(source)}` : ''}</span>`
  ).join('');
}

function rowId(row) {
  return String(row?.['List ID'] || '');
}

function getSelectedRows() {
  if (!currentResultState) return [];
  return currentResultState.activeRows.filter(row =>
    currentResultState.selectedIds.has(rowId(row)) && !currentResultState.excludedIds.has(rowId(row))
  );
}

function renderSelectionChart(rows) {
  const chart = $('selectionChart');
  const selected = (rows || []).slice().sort((a, b) => Number(b['Quantity'] || 0) - Number(a['Quantity'] || 0)).slice(0, 12);
  if (!selected.length) {
    chart.innerHTML = '<div class="empty-chart">No lists selected.</div>';
    return;
  }
  const max = Math.max(...selected.map(r => Number(r['Quantity'] || 0)), 1);
  chart.innerHTML = selected.map(row => {
    const qty = Number(row['Quantity'] || 0);
    const pct = Math.max(4, Math.round((qty / max) * 100));
    const label = escapeHtml(row['List Name'] || 'List');
    const profile = escapeHtml(row['Audience'] || row['Category'] || '');
    return `
      <div class="bar-row">
        <div class="bar-label" title="${label}">${label}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
        <div class="bar-value">${fmt.format(qty)}</div>
        <div class="bar-profile">${profile}</div>
      </div>
    `;
  }).join('');
}

function shortText(value, maxLen = 180) {
  const text = String(value || '');
  return text.length > maxLen ? `${text.slice(0, maxLen - 1)}…` : text;
}

function deriveCurrentResultState() {
  if (!currentResultState) return null;
  const activeRows = currentResultState.activeRows.filter(row => !currentResultState.excludedIds.has(rowId(row)));
  const selectedRows = activeRows.filter(row => currentResultState.selectedIds.has(rowId(row)));
  const activeQuantity = activeRows.reduce((sum, row) => sum + Number(row['Quantity'] || 0), 0);
  const selectedQuantityValue = selectedRows.reduce((sum, row) => sum + Number(row['Quantity'] || 0), 0);
  const excludedItems = Array.from(currentResultState.excludedItems.values());
  const excludedQuantity = excludedItems.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  const target = Number(currentResultState.summary.target_quantity || currentResultState.summary.target_count || 0);
  const targetReached = target > 0 ? activeQuantity >= target : null;
  const categories = new Map();
  activeRows.forEach(row => {
    const group = row['Business Category Group'] || row['Category'] || 'Uncategorized';
    const current = categories.get(group) || { group, recommended_lists: 0, recommended_quantity: 0 };
    current.recommended_lists += 1;
    current.recommended_quantity += Number(row['Quantity'] || 0);
    categories.set(group, current);
  });
  return {
    activeRows,
    selectedRows,
    excludedItems,
    resultCategoryGroups: Array.from(categories.values()),
    summary: {
      ...currentResultState.summary,
      selected_lists: activeRows.length,
      total_quantity: activeQuantity,
      gross_selected_quantity: activeQuantity,
      active_recommendation_list_count: activeRows.length,
      active_recommended_quantity: activeQuantity,
      selected_list_count: selectedRows.length,
      selected_quantity: selectedQuantityValue,
      excluded_list_count: excludedItems.length,
      excluded_quantity: excludedQuantity,
      target_count: target,
      target_reached: targetReached,
      target_met: targetReached,
      target_difference: target ? activeQuantity - target : 0,
      target_overshoot: target && activeQuantity >= target ? activeQuantity - target : 0,
      target_shortage: target && activeQuantity < target ? target - activeQuantity : 0,
    }
  };
}

function renderExcludedLists(items) {
  const wrap = $('excludedLists');
  if (!wrap) return;
  wrap.hidden = !items.length;
  wrap.innerHTML = items.map((item, index) => `
    <span class="excluded-item">
      <span>${escapeHtml(item.list_name || item.list_id)} - ${fmt.format(Number(item.quantity || 0))}</span>
      <button type="button" class="restore-btn" data-excluded-index="${index}">Restore</button>
    </span>
  `).join('');
  wrap.querySelectorAll('.restore-btn').forEach(button => {
    button.addEventListener('click', () => restoreRecommendation(items[Number(button.dataset.excludedIndex)]?.list_id));
  });
}

function renderCurrentResultState(renderTable = true) {
  const derived = deriveCurrentResultState();
  if (!derived) return;
  currentResultState.summary = derived.summary;
  currentResultState.resultCategoryGroups = derived.resultCategoryGroups;
  $('recommendedCount').textContent = fmt.format(derived.summary.active_recommendation_list_count || 0);
  $('recommendedTotal').textContent = fmt.format(derived.summary.active_recommended_quantity || 0);
  $('selectedListCount').textContent = fmt.format(derived.summary.selected_list_count || 0);
  $('selectedTotal').textContent = fmt.format(derived.summary.selected_quantity || 0);
  $('excludedCount').textContent = fmt.format(derived.summary.excluded_list_count || 0);
  $('excludedTotal').textContent = fmt.format(derived.summary.excluded_quantity || 0);
  $('targetQtyView').textContent = fmt.format(derived.summary.target_count || 0);
  $('targetDiffView').textContent = fmt.format(derived.summary.target_difference || 0);
  if (derived.summary.target_count) {
    const source = titleCase(derived.summary.target_source || 'none');
    const statusText = derived.summary.target_met
      ? `Target reached Â· overshoot ${fmt.format(derived.summary.target_overshoot || 0)}`
      : `Target not reachable Â· shortage ${fmt.format(derived.summary.target_shortage || 0)}`;
    $('targetStatus').textContent = `Target source: ${source} Â· ${statusText}`;
  } else {
    $('targetStatus').textContent = 'No target count set';
  }
  renderSelectionChart(derived.selectedRows);
  renderExcludedLists(derived.excludedItems);
  if (renderTable) renderRows(derived.activeRows);
  const base = currentResultState.baseResult;
  base.summary = derived.summary;
  base.result_category_groups = derived.resultCategoryGroups;
  renderIntentSummary(base.interpreted_intent || {}, base);
  $('selectAllBtn').disabled = !derived.activeRows.length;
  $('clearSelectionBtn').disabled = !derived.selectedRows.length;
  $('downloadSelectedBtn').disabled = !derived.selectedRows.length;
}

function renderRows(rows) {
  lastRows = rows || [];
  const tbody = document.querySelector('#resultsTable tbody');
  tbody.innerHTML = '';
  const fragment = document.createDocumentFragment();
  lastRows.forEach((row, idx) => {
    const tr = document.createElement('tr');
    const quantity = Number(row['Quantity'] || 0);
    const id = rowId(row);
    const checked = currentResultState?.selectedIds.has(id) ? 'checked' : '';
    const isExclusive = row['Exclusive Data'] === true || String(row['Exclusive Data']).toLowerCase() === 'true';
    if (isExclusive) tr.classList.add('exclusive-row');
    const exclusiveBadge = isExclusive ? '<span class="exclusive-badge">Exclusive</span>' : '';
    tr.innerHTML = `
      <td><input class="row-check" type="checkbox" ${checked} data-quantity="${quantity}" data-index="${idx}"></td>
      <td>${exclusiveBadge}${escapeHtml(row['List Name'] || '')}</td>
      <td>${escapeHtml(row['Company'] || '')}</td>
      <td class="about-cell" title="${escapeHtml(row['About'] || '')}">${escapeHtml(shortText(row['About'] || ''))}</td>
      <td>${escapeHtml(row['Audience'] || row['Category'] || '')}</td>
      <td>${escapeHtml(row['Class'] || '')}</td>
      <td>${escapeHtml(row['Age Range'] || '')}</td>
      <td>${escapeHtml(row['Location'] || row['City / Coverage'] || '')}</td>
      <td class="qty">${fmt.format(quantity)}</td>
      <td>${escapeHtml(row['Created Date'] || '')}</td>
      <td><span class="unique-badge">${escapeHtml(row['Uniqueness'] || '')}</span></td>
      <td class="why">${escapeHtml(row['Why Recommended'] || '')}</td>
      <td><button type="button" class="exclude-btn" data-index="${idx}">Exclude</button></td>
    `;
    fragment.appendChild(tr);
  });
  tbody.appendChild(fragment);
  document.querySelectorAll('.row-check').forEach(chk => chk.addEventListener('change', () => {
    const row = lastRows[Number(chk.dataset.index || -1)];
    toggleRecommendationUse(rowId(row), chk.checked);
  }));
  document.querySelectorAll('.exclude-btn').forEach(button => button.addEventListener('click', () => {
    const row = lastRows[Number(button.dataset.index || -1)];
    excludeRecommendation(row);
  }));
}

function initializeCurrentResultState(result) {
  const state = result.result_state || {};
  const activeRows = result.recommended || [];
  const selectedIds = Array.isArray(state.selected_ids)
    ? state.selected_ids
    : activeRows.map(rowId);
  const excludedItems = new Map((state.excluded_items || []).map(item => [String(item.list_id), item]));
  currentResultState = {
    jobId: result.job_id || '',
    revision: Number(state.revision || 0),
    activeRows,
    selectedIds: new Set(selectedIds.map(String)),
    excludedIds: new Set((state.excluded_ids || []).map(String)),
    excludedItems,
    summary: result.summary || {},
    resultCategoryGroups: result.result_category_groups || [],
    baseResult: result,
    syncError: null,
  };
}

function applyServerInteraction(data) {
  if (!currentResultState) return;
  const state = data.result_state || {};
  currentResultState.activeRows = data.recommendations || [];
  currentResultState.summary = data.summary || currentResultState.summary;
  currentResultState.resultCategoryGroups = data.result_category_groups || [];
  currentResultState.selectedIds = new Set((state.selected_ids || []).map(String));
  currentResultState.excludedIds = new Set((state.excluded_ids || []).map(String));
  currentResultState.excludedItems = new Map(
    (state.excluded_items || []).map(item => [String(item.list_id), item])
  );
  currentResultState.revision = Number(state.revision ?? data.revision ?? currentResultState.revision);
  currentResultState.syncError = null;
  const base = currentResultState.baseResult;
  base.recommended = currentResultState.activeRows;
  base.summary = currentResultState.summary;
  base.result_category_groups = currentResultState.resultCategoryGroups;
  base.result_state = state;
  base.diagnostics = base.diagnostics || {};
  base.diagnostics.interaction = data.interaction_diagnostics || {};
}

function queueResultStateSync(autoSelectReplacements = true) {
  if (!currentResultState?.jobId) return Promise.resolve();
  if (resultSyncController) resultSyncController.abort();
  resultSyncController = new AbortController();
  const revision = currentResultState.revision;
  const payload = {
    excluded_ids: Array.from(currentResultState.excludedIds),
    selected_ids: Array.from(currentResultState.selectedIds),
    revision,
    auto_select_replacements: autoSelectReplacements,
  };
  const sync = api(`/api/v2/recommend/jobs/${encodeURIComponent(currentResultState.jobId)}/selection`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
    signal: resultSyncController.signal,
  }).then(data => {
    if (!currentResultState || revision !== currentResultState.revision) return;
    if (Number(data.revision) !== revision) return;
    applyServerInteraction(data);
    renderCurrentResultState(true);
  }).catch(error => {
    if (error.name === 'AbortError') return;
    if (currentResultState && revision === currentResultState.revision) {
      currentResultState.syncError = error;
      $('aiNote').textContent = `Result update failed: ${error.message || error}`;
    }
  });
  resultSyncPromise = sync;
  return sync;
}

function toggleRecommendationUse(id, use) {
  if (!currentResultState || !id) return;
  if (use) currentResultState.selectedIds.add(id);
  else currentResultState.selectedIds.delete(id);
  currentResultState.revision += 1;
  renderCurrentResultState(false);
  queueResultStateSync(false);
}

function excludeRecommendation(row) {
  if (!currentResultState || !row) return;
  const id = rowId(row);
  if (!id || currentResultState.excludedIds.has(id)) return;
  currentResultState.excludedIds.add(id);
  currentResultState.excludedItems.set(id, {
    list_id: id,
    list_name: row['List Name'] || id,
    quantity: Number(row['Quantity'] || 0),
  });
  currentResultState.activeRows = currentResultState.activeRows.filter(item => rowId(item) !== id);
  currentResultState.revision += 1;
  renderCurrentResultState(true);
  queueResultStateSync(true);
}

function restoreRecommendation(id) {
  if (!currentResultState || !id || !currentResultState.excludedIds.has(String(id))) return;
  currentResultState.excludedIds.delete(String(id));
  currentResultState.excludedItems.delete(String(id));
  currentResultState.revision += 1;
  renderCurrentResultState(true);
  queueResultStateSync(true);
}

function selectAll(state) {
  if (!currentResultState) return;
  currentResultState.selectedIds = state
    ? new Set(currentResultState.activeRows.map(rowId).filter(Boolean))
    : new Set();
  currentResultState.revision += 1;
  renderCurrentResultState(true);
  queueResultStateSync(false);
}

async function downloadCurrentSelection() {
  if (!currentResultState || !getSelectedRows().length) return;
  await resultSyncPromise;
  if (currentResultState.syncError) {
    alert(currentResultState.syncError.message || currentResultState.syncError);
    return;
  }
  const link = document.createElement('a');
  link.href = `/api/v2/recommend/jobs/${encodeURIComponent(currentResultState.jobId)}/export?revision=${currentResultState.revision}`;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

function escapeHtml(str) {
  return String(str)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function showWorking(message = 'Starting recommendation.', percent = 2) {
  const card = $('workingCard');
  if (card) card.style.display = 'grid';
  setWorkingStatus(message, percent);
}

function setWorkingStatus(message, percent) {
  const msg = $('workingMessage');
  const bar = $('workingProgress');
  if (msg && message) msg.textContent = message;
  if (bar) bar.style.width = `${Math.max(2, Math.min(100, Number(percent || 0)))}%`;
}

function hideWorking() {
  const card = $('workingCard');
  if (card) card.style.display = 'none';
}

async function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function waitForRecommendationJob(jobId) {
  const fallbackMessages = [
    'Ranking unique lists…',
    'Reaching target count…',
    'Preparing company branch references…',
    'Building the final grid and visualisation…'
  ];
  let ticks = 0;
  while (true) {
    const job = await api(`/api/v2/recommend/status/${encodeURIComponent(jobId)}`);
    const message = job.message || fallbackMessages[ticks % fallbackMessages.length];
    const percent = Number(job.progress || Math.min(95, 10 + ticks * 5));
    setWorkingStatus(message, percent);
    if (job.status === 'completed') return job.result;
    if (job.status === 'failed') throw new Error(job.error?.message || 'Recommendation failed.');
    ticks += 1;
    await sleep(650);
  }
}

function renderRecommendationResult(result) {
  $('resultsCard').style.display = 'block';
  initializeCurrentResultState(result);
  $('recommendedCount').textContent = fmt.format(result.summary.selected_lists || 0);
  $('recommendedTotal').textContent = fmt.format(result.summary.total_quantity || 0);
  $('targetQtyView').textContent = fmt.format(result.summary.target_quantity || 0);
  $('targetDiffView').textContent = fmt.format(result.summary.target_difference || 0);
  if (result.summary.target_quantity) {
    const source = titleCase(result.summary.target_source || 'none');
    const statusText = result.summary.target_met
      ? `Target reached · overshoot ${fmt.format(result.summary.target_overshoot || 0)}`
      : `Target not reachable · shortage ${fmt.format(result.summary.target_shortage || 0)}`;
    $('targetStatus').textContent = `Target source: ${source} · ${statusText}`;
  } else {
    $('targetStatus').textContent = 'No target count set';
  }
  $('aiNote').textContent = result.ai_error
    ? `${result.ai_note}`
    : result.ai_note;
  renderCampaignUnderstanding(result);
  renderRuntimeDiagnostics(result);
  renderIntentSummary(result.interpreted_intent || {}, result);
  renderCompanyConfirmation(result.company_confirmations || result.company_confirmation);
  if (!result.reset_ai_fields && !result.interpreted_intent) {
    applyInterpretedFilters(result.interpreted_filters);
  }
  renderAppliedFilters(result.effective_filters || result.interpreted_filters);
  $('enhancementNote').textContent = (result.enhancements_applied || []).join(' · ');
  const suppressed = result.summary.duplicate_profiles_suppressed || 0;
  $('uniqueNote').textContent = suppressed
    ? `${fmt.format(suppressed)} similar dated/profile duplicates were suppressed so the suggestion stays unique.`
    : 'No similar profile duplicates were needed in the final suggestion.';
  renderCurrentResultState(true);
  window.scrollTo({ top: $('resultsCard').offsetTop - 80, behavior: 'smooth' });
}

function renderIntentSummary(intent, result = {}) {
  const wrap = $('intentSummary');
  if (!wrap) return;
  const filters = intent.explicit_filters || {};
  const constraints = result.manual_constraints || {};
  const representedCategories = (result.result_category_groups || []).map(group => group.group);
  const ageFilter = filters.age_min == null
    ? ''
    : `Age ${filters.age_min}${filters.age_max == null ? '+' : ` - ${filters.age_max}`}`;
  const affinity = intent.class_affinity || {};
  const affinityText = Array.isArray(affinity)
    ? affinity.join(', ')
    : Object.entries(affinity).map(([name, strength]) => `${name}:${strength}`).join(', ');
  const entries = [
    ['Advertiser', (intent.advertisers || []).join(', ')],
    ['Products', (intent.normalized_product_concepts || intent.product_families || []).join(', ')],
    ['Filters', [...(filters.cities || []), ...(filters.areas || []), ...(filters.gender || []), ...(filters.classes || []), ageFilter].filter(Boolean).join(', ')],
    ['Class affinity', affinityText],
    ['Category filter', (constraints.categories || []).join(', ')],
    ['Minimum count', constraints.min_quantity ? fmt.format(constraints.min_quantity) : ''],
    ['Result categories', representedCategories.join(', ')],
  ].filter(([, value]) => value);
  wrap.innerHTML = entries.map(([label, value]) =>
    `<span class="filter-chip"><span>${escapeHtml(label)}</span> ${escapeHtml(value)}</span>`
  ).join('');
}

function renderCampaignUnderstanding(result) {
  const understanding = result.campaign_understanding || {};
  const summary = result.summary || {};
  const products = (understanding.products_services || [])
    .map(item => item.normalized_description)
    .filter(Boolean);
  const explicit = understanding.explicit_target_audiences || [];
  const inferred = understanding.inferred_target_audiences || [];
  const targets = explicit.length ? explicit : inferred;
  const summaryEl = $('campaignUnderstandingSummary');
  const targetEl = $('suggestedTarget');
  if (summaryEl) summaryEl.textContent = summary.campaign_understood || understanding.interpretation_summary || 'AI understanding unavailable.';
  if (targetEl) targetEl.textContent = targets.length
    ? targets.join(', ')
    : products.length ? `Likely buyers or users of ${products.join(', ')}` : 'No target inferred.';
}

function renderRuntimeDiagnostics(result) {
  const diagnostics = result.diagnostics || {};
  const target = diagnostics.target || {};
  const positioning = diagnostics.class_positioning || {};
  const wrap = $('runtimeDiagnostics');
  if (!wrap) return;
  const modeLabel = diagnostics.ai_call_succeeded ? 'AI Hybrid \u00b7 OpenAI' : 'AI unavailable';
  if ($('engineLabel')) $('engineLabel').textContent = modeLabel;
  const entries = [
    ['AI understanding', diagnostics.intent_provider === 'openai' ? 'OpenAI' : 'Unavailable'],
    ['AI call', diagnostics.ai_call_succeeded ? 'Yes' : 'No'],
    ['Model', diagnostics.intent_model || 'Unavailable'],
    ['Intent latency', `${fmt.format(diagnostics.intent_latency_ms || 0)} ms`],
    ['Embedding provider', diagnostics.embedding_provider === 'openai' ? 'OpenAI' : diagnostics.embedding_provider || 'Unavailable'],
    ['Query embedding', diagnostics.query_embedding_generated ? 'Yes' : 'No'],
    ['Catalogue embeddings', diagnostics.catalogue_embedding_cache_hit ? 'OpenAI / cached' : 'Not used'],
    ['Retrieval mode', titleCase(diagnostics.retrieval_mode || 'not started').replaceAll('_', ' ')],
    ['Profiles scored', fmt.format(diagnostics.profiles_scored || 0)],
    ['Recommendations', fmt.format(diagnostics.returned_profiles || 0)],
    ['Requested reach', fmt.format(target.effective_target_count || 0)],
    ['Target source', titleCase(target.source || 'none')],
    ['Qualified before target', fmt.format(target.qualified_before_target || 0)],
    ['Selected after target', fmt.format(target.selected_after_target || 0)],
    ['Gross selected quantity', fmt.format(target.gross_selected_quantity || 0)],
    ['Reach excluded from semantics', diagnostics.semantic_query_contains_reach_number ? 'No' : 'Yes'],
    ['Geography excluded from semantics', diagnostics.semantic_query_contains_explicit_geography ? 'No' : 'Yes'],
    ['Primary class', positioning.primary_class || 'None'],
    ['Class source', titleCase(positioning.source || 'none').replaceAll('_', ' ')],
  ];
  wrap.innerHTML = entries.map(([label, value]) =>
    `<div><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>`
  ).join('');
}

async function recommend() {
  if (recommendationInFlight) return;
  recommendationInFlight = true;
  $('recommendBtn').disabled = true;
  $('recommendBtn').textContent = 'Working…';
  showWorking('Starting recommendation.', 2);
  try {
    const started = await api('/api/v2/recommend/start', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(getPayload())
    });
    setWorkingStatus('Recommendation job started.', 6);
    const result = await waitForRecommendationJob(started.job_id);
    result.job_id = result.job_id || started.job_id;
    setWorkingStatus('Recommendation ready.', 100);
    renderRecommendationResult(result);
  } catch (err) {
    alert(err.message || err);
  } finally {
    await sleep(250);
    hideWorking();
    $('recommendBtn').disabled = false;
    $('recommendBtn').textContent = 'Recommend Lists';
    recommendationInFlight = false;
  }
}

document.addEventListener('click', () => closeOtherTagSelects(''));

document.addEventListener('DOMContentLoaded', async () => {
  await loadStatus();
  await loadOptions();
  ['minQuantity', 'maxLists'].forEach(id => {
    const el = $(id);
    if (el) {
      el.addEventListener('input', () => formatCountInput(id));
      el.addEventListener('blur', () => formatCountInput(id));
    }
  });
  $('recommendBtn').addEventListener('click', recommend);
  $('selectAllBtn').addEventListener('click', () => selectAll(true));
  $('clearSelectionBtn').addEventListener('click', () => selectAll(false));
  $('downloadSelectedBtn').addEventListener('click', downloadCurrentSelection);
  $('ageMin').addEventListener('input', updateAgeRangeLabel);
  $('ageMax').addEventListener('input', updateAgeRangeLabel);
  $('resetAgeBtn').addEventListener('click', resetAgeRange);
  $('maxModeBtn').addEventListener('click', toggleMaxMode);
});
