(() => {
  'use strict';
  const base = document.body.dataset.appBasePath || '';
  const state = { page: 1, pageSize: 25 };
  const byId = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ms = value => Number(value) > 0 ? `${Number(value).toLocaleString()} ms` : '—';
  const number = value => Number(value).toLocaleString();
  const minutes = value => Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 });
  const filters = () => new URLSearchParams({
    days: byId('days-filter').value, provider: byId('provider-filter').value,
    operation: byId('operation-filter').value, language: byId('language-filter').value,
    status: byId('status-filter').value
  });
  function status(message, error = false) {
    byId('dashboard-status').textContent = message;
    byId('dashboard-status').dataset.tone = error ? 'error' : 'success';
  }
  async function get(url) {
    const response = await fetch(url, { credentials: 'same-origin' });
    if (!response.ok) throw Error((await response.json().catch(() => ({}))).detail || `Request failed (${response.status})`);
    return response.json();
  }
  function showVoice(kind, allowance) {
    byId(`metric-voice-${kind}`).textContent = `${minutes(allowance.used_minutes)} / ${minutes(allowance.limit_minutes)} min`;
    byId(`metric-voice-${kind}-remaining`).textContent = `${minutes(allowance.remaining_minutes)} min remaining`;
    byId(`voice-${kind}-card`).classList.remove('green', 'yellow', 'red');
    byId(`voice-${kind}-card`).classList.add(allowance.status);
  }
  function showSummary(data) {
    const bundle = data.monthly_limit;
    byId('metric-requests').textContent = number(data.requests);
    byId('metric-openai-input').textContent = number(data.openai.input_tokens);
    byId('metric-openai-output').textContent = number(data.openai.output_tokens);
    byId('metric-monthly-bundle').textContent = `${number(bundle.used_tokens)} / ${number(bundle.limit_tokens)}`;
    byId('metric-monthly-remaining').textContent = `${number(Math.max(0, bundle.limit_tokens - bundle.used_tokens))} tokens remaining`;
    showVoice('input', data.monthly_voice.input);
    showVoice('output', data.monthly_voice.output);
    byId('metric-latency').textContent = ms(data.request_ms.avg);
    byId('metric-failures').textContent = `${data.failed} / ${data.cancelled} cancelled`;
  }
  async function summary() {
    showSummary(await get(`${base}/api/client/usage/summary?${filters()}`));
  }
  async function requests() {
    const query = filters();
    query.set('page', state.page);
    query.set('page_size', state.pageSize);
    const data = await get(`${base}/api/client/usage/requests?${query}`);
    byId('request-table-body').innerHTML = data.items.map(item => {
      const usage = item.provider === 'openai'
        ? `${number(item.input_text_tokens)} in / ${number(item.output_text_tokens)} out`
        : item.operation === 'tts' ? `${(item.output_audio_duration_ms / 1000).toFixed(1)} s` : `${(item.input_audio_duration_ms / 1000).toFixed(1)} s`;
      return `<tr data-id="${esc(item.id)}"><td>${esc(new Date(item.started_at).toLocaleString())}</td><td>${esc(item.language || '—')}</td><td>${esc(usage)}</td></tr>`;
    }).join('') || '<tr><td colspan="3">No API requests match these filters.</td></tr>';
    const pages = Math.max(1, Math.ceil(data.total / state.pageSize));
    byId('page-label').textContent = `Page ${state.page} of ${pages} · ${data.total} requests`;
    byId('previous-page').disabled = state.page <= 1;
    byId('next-page').disabled = state.page >= pages;
    document.querySelectorAll('tr[data-id]').forEach(row => row.addEventListener('click', () => detail(row.dataset.id)));
  }
  async function detail(id) {
    const data = await get(`${base}/api/client/usage/requests/${id}`);
    const fields = {
      Started: data.started_at, Language: data.language,
      'Input tokens': data.input_text_tokens,
      'Output tokens': data.output_text_tokens, 'Request latency': ms(data.request_duration_ms),
      'First audio': ms(data.first_audio_ms), 'Output audio': `${(data.output_audio_duration_ms / 1000).toFixed(2)} s`,
      Error: data.error_type || '—'
    };
    byId('detail-title').textContent = `${data.operation.toUpperCase()} · ${data.status}`;
    byId('detail-grid').innerHTML = Object.entries(fields).map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`).join('');
  }
  async function refresh() {
    try { status('Loading…'); await Promise.all([summary(), requests()]); status('Updated'); }
    catch (error) { status(error.message, true); }
  }
  ['days-filter', 'provider-filter', 'operation-filter', 'language-filter', 'status-filter'].forEach(id =>
    byId(id).addEventListener('change', () => { state.page = 1; refresh(); })
  );
  byId('previous-page').addEventListener('click', () => { if (state.page > 1) { state.page--; requests(); } });
  byId('next-page').addEventListener('click', () => { state.page++; requests(); });
  refresh();
})();
