import { DatabaseSync } from 'node:sqlite';
import { createHash, randomBytes, randomUUID } from 'node:crypto';
export const hash = token => createHash('sha256').update(token).digest('hex');
export const secret = () => randomBytes(32).toString('base64url');
export class Store {
  constructor(path) {
    this.db = new DatabaseSync(path);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS members(id TEXT PRIMARY KEY, name TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id), last_seen TEXT NOT NULL, issues INTEGER NOT NULL DEFAULT 0, pending INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, member_id TEXT NOT NULL REFERENCES members(id), device_id TEXT NOT NULL, at TEXT NOT NULL, input_tokens INTEGER NOT NULL, cached_input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, reasoning_output_tokens INTEGER NOT NULL, total_tokens INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS events_at ON events(at);
      CREATE INDEX IF NOT EXISTS events_member_at ON events(member_id, at);
      CREATE TABLE IF NOT EXISTS limits(member_id TEXT NOT NULL REFERENCES members(id), limit_id TEXT NOT NULL, observed_at TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY(member_id,limit_id));
      CREATE TABLE IF NOT EXISTS browser_sessions(token_hash TEXT PRIMARY KEY, member_id TEXT, admin INTEGER NOT NULL DEFAULT 0, expires_at INTEGER NOT NULL);
    `);
  }
  close() { this.db.close(); }
  addMember(name) {
    const id = randomUUID(), token = 'ctm_' + secret();
    this.db.prepare('INSERT INTO members(id,name,token_hash,created_at) VALUES(?,?,?,?)').run(id,name,hash(token),new Date().toISOString());
    return { id, name, token };
  }
  memberForToken(token) { return this.db.prepare('SELECT id,name FROM members WHERE token_hash=? AND active=1').get(hash(token)); }
  listMembers() { return this.db.prepare('SELECT id,name,active,created_at FROM members ORDER BY created_at').all(); }
  deactivate(id) {
    this.db.prepare('UPDATE members SET active=0 WHERE id=?').run(id);
    this.db.prepare('DELETE FROM browser_sessions WHERE member_id=?').run(id);
  }
  newSession(memberId, admin) {
    const token = secret();
    this.db.prepare('INSERT INTO browser_sessions VALUES(?,?,?,?)').run(hash(token),memberId,admin ? 1 : 0,Date.now()+8*3600000);
    return token;
  }
  session(token) {
    const s = this.db.prepare('SELECT member_id,admin FROM browser_sessions WHERE token_hash=? AND expires_at>?').get(hash(token),Date.now());
    if (!s || (!s.admin && !this.db.prepare('SELECT id FROM members WHERE id=? AND active=1').get(s.member_id))) return null;
    return s;
  }
  logout(token) { this.db.prepare('DELETE FROM browser_sessions WHERE token_hash=?').run(hash(token)); }
  ingest(memberId, batch) {
    const now = new Date().toISOString();
    const knownDevice = this.db.prepare('SELECT member_id FROM devices WHERE id=?').get(batch.device_id);
    if (knownDevice && knownDevice.member_id !== memberId) throw Object.assign(new Error('device_identity_conflict'), {status:409});
    let accepted=0, duplicates=0, conflicts=0;
    this.db.exec('BEGIN IMMEDIATE');
    try {
      this.db.prepare(`INSERT INTO devices VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,issues=excluded.issues,pending=excluded.pending`).run(batch.device_id, memberId, now, batch.issues, batch.pending);
      const insert = this.db.prepare('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?,?,?,?,?)');
      const owner = this.db.prepare('SELECT member_id FROM events WHERE id=?');
      for (const e of batch.events) {
        const old = owner.get(e.id);
        if (old) { if (old.member_id === memberId) duplicates++; else conflicts++; continue; }
        accepted += Number(insert.run(e.id,memberId,batch.device_id,e.at,e.input_tokens,e.cached_input_tokens,e.output_tokens,e.reasoning_output_tokens,e.total_tokens).changes);
      }
      for (const l of batch.limits) this.db.prepare(`INSERT INTO limits VALUES(?,?,?,?) ON CONFLICT(member_id,limit_id) DO UPDATE SET observed_at=excluded.observed_at,value=excluded.value WHERE excluded.observed_at>limits.observed_at`).run(memberId,l.limit_id,l.observed_at,JSON.stringify(l));
      this.db.exec('COMMIT');
    } catch (e) { this.db.exec('ROLLBACK'); throw e; }
    return { accepted, duplicates, conflicts };
  }
  summary(hours, now = Date.now()) {
    const since = new Date(now-hours*3600000).toISOString(), until = new Date(now).toISOString();
    const members = this.db.prepare(`SELECT m.id,m.name,m.active,COALESCE(SUM(e.total_tokens),0) total_tokens,
      COALESCE(SUM(e.input_tokens),0) input_tokens,COALESCE(SUM(e.cached_input_tokens),0) cached_input_tokens,
      COALESCE(SUM(e.output_tokens),0) output_tokens,COALESCE(SUM(e.reasoning_output_tokens),0) reasoning_output_tokens,
      COUNT(e.id) observations FROM members m LEFT JOIN events e ON e.member_id=m.id AND e.at>=? AND e.at<=? GROUP BY m.id ORDER BY total_tokens DESC,m.name`).all(since,until);
    const total = members.reduce((s,m)=>s+m.total_tokens,0);
    for (const m of members) {
      const d = this.db.prepare('SELECT MAX(last_seen) last_seen,COALESCE(SUM(issues),0) issues,COALESCE(SUM(pending),0) pending,COUNT(*) devices FROM devices WHERE member_id=?').get(m.id);
      Object.assign(m,d,{share_percent:total ? m.total_tokens/total*100 : null,connected:Boolean(d.last_seen && now-Date.parse(d.last_seen)<180000)});
    }
    // Keep each reporting member separate: accounts may be different. Never average quotas.
    const limits = this.db.prepare('SELECT l.member_id,m.name,l.value FROM limits l JOIN members m ON m.id=l.member_id ORDER BY observed_at DESC').all().map(r=>({member_id:r.member_id,name:r.name,...JSON.parse(r.value)}));
    const daily = this.db.prepare("SELECT substr(at,1,10) day,SUM(total_tokens) total_tokens FROM events WHERE at>=? AND at<=? GROUP BY day ORDER BY day").all(since,until);
    return { generated_at:until,since,hours,total_tokens:total,members,limits,daily,
      metric:'observed_token_share_not_subscription_quota',coverage:'Local Codex rollout records since installation only. No cloud-only accounting. Device reports are not tamper-proof.' };
  }
  maintenance(retentionDays) {
    this.db.prepare('DELETE FROM browser_sessions WHERE expires_at<?').run(Date.now());
    // Old retries are filtered by event timestamp in the HTTP layer before ingestion.
    // Remove usage rows outside retention; membership and latest limit snapshots remain.
    this.db.prepare('DELETE FROM events WHERE at<?').run(new Date(Date.now()-retentionDays*86400000).toISOString());
  }
}
