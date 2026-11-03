import http from 'node:http';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { timingSafeEqual } from 'node:crypto';
import { Store, hash } from './store.mjs';
import { counters } from '../skills/team-usage-meter/scripts/parser.mjs';
const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const fail = (status,code) => { throw Object.assign(new Error(code),{status}); };
const strict = (o, keys) => o && typeof o==='object' && !Array.isArray(o) && Object.keys(o).every(k=>keys.includes(k));
const int = n => Number.isSafeInteger(n) && n>=0 && n<=1e12;
const uuid = s => typeof s==='string' && /^[a-f0-9-]{36}$/.test(s);
const safeEq = (a,b) => timingSafeEqual(Buffer.from(hash(a)),Buffer.from(hash(b)));
export function validateBatch(b, now = Date.now()) {
  if (!strict(b,['device_id','events','limits','issues','pending']) || !uuid(b.device_id) || !Array.isArray(b.events) || b.events.length>300 || !Array.isArray(b.limits) || b.limits.length>30 || !int(b.issues) || !int(b.pending)) fail(400,'invalid_numeric_batch');
  const checkDate = s => typeof s==='string' && Number.isFinite(Date.parse(s)) && s === new Date(s).toISOString() && Date.parse(s)<=now+300000;
  for (const e of b.events) {
    if (!strict(e,['id','at','input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens','total_tokens']) || typeof e.id!=='string' || !/^[a-f0-9]{64}$/.test(e.id) || !checkDate(e.at) || !counters(e)) fail(400,'invalid_event_no_extra_fields_allowed');
  }
  for (const l of b.limits) {
    if (!strict(l,['limit_id','observed_at','primary','secondary']) || !/^[a-zA-Z0-9_.:-]{1,80}$/.test(l.limit_id) || !checkDate(l.observed_at)) fail(400,'invalid_limit');
    for (const w of [l.primary,l.secondary]) {
      if (w===null) continue;
      if (!strict(w,['used_percent','window_minutes','resets_at']) || !Number.isFinite(w.used_percent) || w.used_percent<0 || w.used_percent>100 || !(w.window_minutes===null || (int(w.window_minutes)&&w.window_minutes>0)) || !(w.resets_at===null || (int(w.resets_at)&&w.resets_at<1e11))) fail(400,'invalid_window');
    }
  }
  return b;
}
export function createApp({dbPath,adminToken,publicUrl,retentionDays=90}={}) {
  if (typeof adminToken!=='string' || adminToken.length<32) throw new Error('ADMIN_TOKEN must be a random secret of at least 32 characters. Run node deploy/setup.mjs.');
  const base = new URL(publicUrl ?? 'http://localhost:8790');
  if (!['http:','https:'].includes(base.protocol) || base.pathname!=='/' || base.username || base.password || base.search || base.hash) throw new Error('PUBLIC_URL must be an origin without a path.');
  if (base.protocol!=='https:' && !['localhost','127.0.0.1','[::1]'].includes(base.hostname)) throw new Error('Public deployment requires HTTPS.');
  const secure=base.protocol==='https:';
  if (dbPath!==':memory:') mkdirSync(dirname(dbPath),{recursive:true,mode:0o700});
  const store = new Store(dbPath);
  const staticFiles = new Map([
    ['/', ['index.html','text/html; charset=utf-8']], ['/app.js',['app.js','text/javascript; charset=utf-8']], ['/style.css',['style.css','text/css; charset=utf-8']],
  ].map(([url,[file,mime]])=>[url,{data:readFileSync(resolve(ROOT,'public',file)),mime}]));
  const rates=new Map();
  function rate(key,max) {
    const now=Date.now(); let v=rates.get(key);
    if (!v || v.until<now) { v={n:0,until:now+60000}; rates.set(key,v); }
    if (++v.n>max) fail(429,'too_many_requests');
    if (rates.size>2048) for (const [k,val] of rates) if (val.until<now) rates.delete(k);
    if (rates.size>4096) rates.clear();
  }
  const headers={
    'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
    'Permissions-Policy':'camera=(), microphone=(), geolocation=()',
    'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    'Cache-Control':'no-store',...(secure?{'Strict-Transport-Security':'max-age=31536000'}:{}),
  };
  const cookie = token => `ctm_session=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=${token?28800:0}${secure?'; Secure':''}`;
  async function body(req) {
    if (!(req.headers['content-type']??'').startsWith('application/json')) fail(415,'json_required');
    let size=0,parts=[];
    for await (const chunk of req) { size+=chunk.length; if(size>200000) fail(413,'body_too_large'); parts.push(chunk); }
    try { return JSON.parse(Buffer.concat(parts).toString('utf8')); } catch { fail(400,'invalid_json'); }
  }
  const getCookie = req => (req.headers.cookie??'').split(';').map(x=>x.trim()).find(x=>x.startsWith('ctm_session='))?.slice(12)??'';
  const authorize = req => { const s=store.session(getCookie(req)); if(!s) fail(401,'login_required'); return s; };
  const server=http.createServer(async (req,res)=>{
    const send=(status,data,extra={})=>{res.writeHead(status,{...headers,'Content-Type':'application/json; charset=utf-8',...extra});res.end(JSON.stringify(data));};
    try {
      const u=new URL(req.url,'http://internal');
      if (req.headers.origin && req.headers.origin!==base.origin) fail(403,'origin_not_allowed');
      if(req.method==='GET' && u.pathname==='/healthz') return send(200,{ok:true});
      if(req.method==='GET' && staticFiles.has(u.pathname)) {const f=staticFiles.get(u.pathname);res.writeHead(200,{...headers,'Content-Type':f.mime});return res.end(f.data);}
      if(req.method==='POST' && u.pathname==='/api/login') {
        rate('login:'+(req.socket.remoteAddress??'unknown'),30);
        const b=await body(req);
        if(!strict(b,['credential']) || typeof b.credential!=='string' || b.credential.length>200) fail(400,'invalid_credential');
        const admin=safeEq(b.credential,adminToken), member=admin?null:store.memberForToken(b.credential);
        if(!admin && !member) fail(401,'invalid_credential');
        const token=store.newSession(member?.id??null,admin);
        return send(200,{role:admin?'admin':'member'}, {'Set-Cookie':cookie(token)});
      }
      if(req.method==='POST' && u.pathname==='/api/logout') {store.logout(getCookie(req));return send(200,{ok:true},{'Set-Cookie':cookie('')});}
      if(req.method==='POST' && u.pathname==='/api/ingest') {
        const auth=req.headers.authorization??'';
        if(!auth.startsWith('Bearer ') || auth.length>250) fail(401,'device_token_required');
        const member=store.memberForToken(auth.slice(7)); if(!member) fail(401,'invalid_device_token');
        rate('ingest:'+member.id,90);
        const b=validateBatch(await body(req));
        const cutoff=Date.now()-retentionDays*86400000, before=b.events.length;
        b.events=b.events.filter(e=>Date.parse(e.at)>=cutoff);
        return send(200,{ok:true,...store.ingest(member.id,b),expired:before-b.events.length});
      }
      if(u.pathname.startsWith('/api/')) {
        const session=authorize(req);
        if(req.method==='GET' && u.pathname==='/api/me') return send(200,{role:session.admin?'admin':'member',public_url:base.origin,retention_days:retentionDays});
        if(req.method==='GET' && u.pathname==='/api/summary') {
          const hours=Number(u.searchParams.get('hours')??168);
          if(![5,24,168,720,2160].includes(hours)) fail(400,'invalid_period');
          return send(200,store.summary(hours));
        }
        if(req.method==='GET' && u.pathname==='/api/members' && session.admin) return send(200,{members:store.listMembers()});
        if(req.method==='POST' && u.pathname==='/api/members' && session.admin) {
          const b=await body(req);
          if(!strict(b,['name']) || typeof b.name!=='string' || !b.name.trim() || b.name.length>60 || /[\x00-\x1F\x7F]/.test(b.name)) fail(400,'invalid_name');
          if(store.listMembers().length>=100) fail(400,'member_limit_100');
          return send(201,{...store.addMember(b.name.trim()),server:base.origin});
        }
        if(req.method==='POST' && u.pathname==='/api/members/revoke' && session.admin) {
          const b=await body(req);if(!strict(b,['id'])||!uuid(b.id)) fail(400,'invalid_id');store.deactivate(b.id);return send(200,{ok:true});
        }
        fail(403,'not_allowed');
      }
      fail(404,'not_found');
    } catch (e) {
      // Never log request bodies, auth headers, session records or raw errors.
      const status=e.status??500;
      if(!res.headersSent) send(status,{error:status===500?'internal_error':e.message}); else res.end();
    }
  });
  server.requestTimeout=20000;server.headersTimeout=15000;server.keepAliveTimeout=5000;
  const maintenance=setInterval(()=>store.maintenance(retentionDays),3600000);maintenance.unref();
  server.on('close',()=>{clearInterval(maintenance);store.close();});
  return {server,store};
}
if(process.argv[1] && import.meta.url===pathToFileURL(resolve(process.argv[1])).href) {
  const port=Number(process.env.PORT??8790);
  const app=createApp({dbPath:resolve(process.env.DATA_DIR??resolve(ROOT,'data'),'meter.sqlite'),adminToken:process.env.ADMIN_TOKEN,publicUrl:process.env.PUBLIC_URL,retentionDays:90});
  app.server.listen(port,process.env.HOST??'0.0.0.0',()=>console.log(`Codex Team Meter listening on port ${port}. Numeric telemetry only.`));
  for (const sig of ['SIGINT','SIGTERM']) process.on(sig,()=>{app.server.close(()=>process.exit(0));setTimeout(()=>process.exit(1),10000).unref();});
}
