import { createHash } from 'node:crypto';

// This module is the privacy boundary. Never return/spread raw records or payloads.
export const FIELDS = ['input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens', 'total_tokens'];
const digest = value => createHash('sha256').update(value).digest('hex');
const number = n => Number.isSafeInteger(n) && n >= 0 && n <= 1e12;
export const zero = () => Object.fromEntries(FIELDS.map(k => [k, 0]));
export function counters(value) {
  if (!value || !FIELDS.every(k => number(value[k] ?? (k === 'reasoning_output_tokens' ? 0 : NaN)))) return null;
  const out = Object.fromEntries(FIELDS.map(k => [k, value[k] ?? 0]));
  if (out.cached_input_tokens > out.input_tokens || out.reasoning_output_tokens > out.output_tokens) return null;
  // Some Codex context-exhaustion events fill total_tokens artificially. Do not count them.
  if (out.total_tokens !== out.input_tokens + out.output_tokens) return null;
  return out;
}
export function sanitizeLimits(raw, timestamp) {
  if (!raw || !Number.isFinite(Date.parse(timestamp))) return null;
  const window = w => {
    if (!w || typeof w.used_percent !== 'number' || !Number.isFinite(w.used_percent) || w.used_percent < 0 || w.used_percent > 100) return null;
    const mins = w.window_minutes ?? w.window_duration_mins;
    const reset = w.resets_at;
    return { used_percent: w.used_percent,
      window_minutes: number(mins) && mins > 0 ? mins : null,
      resets_at: number(reset) && reset < 1e11 ? reset : null };
  };
  // Only opaque machine identifiers, never limit_name or account/email/credit data.
  const id = typeof raw.limit_id === 'string' && /^[a-zA-Z0-9_.:-]{1,80}$/.test(raw.limit_id) ? raw.limit_id : 'codex';
  const result = { limit_id: id, observed_at: new Date(timestamp).toISOString(), primary: window(raw.primary), secondary: window(raw.secondary) };
  return result.primary || result.secondary ? result : null;
}
export function freshCursor() {
  return { offset: 0, prev: null, floor: null, fork: false, seen: false, issues: 0 };
}
/** Parse locally, discard text, and emit ONLY numeric counters and an opaque dedupe key. */
export function consumeRecord(record, cursor, fileKey, startedAt) {
  const result = { event: null, limit: null };
  if (!record || typeof record !== 'object') return result;
  if (record.type === 'session_meta') {
    const p = record.payload;
    cursor.fork = Boolean(p?.forked_from_id);
    const t = Date.parse(p?.timestamp ?? record.timestamp);
    if (cursor.fork && Number.isFinite(t)) cursor.floor = t;
    return result;
  }
  if (record.type !== 'event_msg' || record.payload?.type !== 'token_count') return result;
  const time = Date.parse(record.timestamp);
  if (!Number.isFinite(time)) { cursor.issues++; return result; }
  const eligible = time >= startedAt && (cursor.floor === null || time >= cursor.floor);
  if (eligible) result.limit = sanitizeLimits(record.payload.rate_limits, record.timestamp);
  const raw = record.payload.info?.total_token_usage;
  if (raw == null) return result; // Rate-limit-only notification, not a token event.
  const current = counters(raw);
  if (!current) { cursor.issues++; cursor.prev = null; cursor.seen = true; return result; }
  const previous = cursor.prev;
  const hadSeen = cursor.seen;
  cursor.prev = current;
  cursor.seen = true;
  if (!eligible) return result; // Establish historical baseline without importing old use.
  // Missing baseline after an invalid record or inherited fork: fail closed, not overcount.
  if (!previous && (hadSeen || cursor.fork)) { cursor.issues++; return result; }
  const base = previous ?? zero();
  if (FIELDS.some(k => current[k] < base[k])) { cursor.issues++; return result; }
  const delta = Object.fromEntries(FIELDS.map(k => [k, current[k] - base[k]]));
  if (delta.total_tokens === 0) return result;
  if (!counters(delta)) { cursor.issues++; return result; }
  result.event = {
    id: digest(`ctm-v1|${fileKey}|${time}|${FIELDS.map(k => current[k]).join(',')}`),
    at: new Date(time).toISOString(), ...delta,
  };
  return result;
}
