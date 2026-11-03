import test from 'node:test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { createApp,validateBatch } from '../server/server.mjs';
const ADMIN='unit-test-admin-key-'+ 'a'.repeat(40);
const event=(id='a',i=100,o=20)=>({id:id.repeat(64),at:new Date(Date.now()-1000).toISOString(),input_tokens:i,cached_input_tokens:i/2,output_tokens:o,reasoning_output_tokens:o/2,total_tokens:i+o});
const batch=(events=[event()])=>({device_id:randomUUID(),events,limits:[],issues:0,pending:0});
async function fixture(fn){const app=createApp({dbPath:':memory:',adminToken:ADMIN,publicUrl:'http://localhost:8790'});await new Promise(r=>app.server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+app.server.address().port;
const call=async(path,method='GET',body,headers={})=>{const r=await fetch(base+path,{method,headers:{'Content-Type':'application/json',...headers},body:body===undefined?undefined:JSON.stringify(body)});return {status:r.status,body:await r.json(),cookie:r.headers.get('set-cookie')?.split(';')[0],headers:r.headers};};
try{await fn({app,call});}finally{await new Promise(r=>{app.server.close(r);app.server.closeAllConnections();});}}
test('public summary and member list require authentication',()=>fixture(async({call})=>{assert.equal((await call('/api/summary')).status,401);assert.equal((await call('/api/members')).status,401);}));
test('admin can create a member; token is not stored in plaintext in members table',()=>fixture(async({call,app})=>{
  const login=await call('/api/login','POST',{credential:ADMIN});assert.equal(login.status,200);assert(login.headers.get('set-cookie').includes('HttpOnly'));assert(login.headers.get('set-cookie').includes('SameSite=Strict'));
  const m=await call('/api/members','POST',{name:'أحمد'},{Cookie:login.cookie});assert.equal(m.status,201);assert(m.body.token.startsWith('ctm_'));
  const row=app.store.db.prepare('SELECT * FROM members').get();assert(!JSON.stringify(row).includes(m.body.token));
}));
test('member token cannot impersonate another member or create members',()=>fixture(async({call,app})=>{
  const m=app.store.addMember('A'),b=batch();b.member_id='someone_else';
  assert.equal((await call('/api/ingest','POST',b,{Authorization:'Bearer '+m.token})).status,400);
  const login=await call('/api/login','POST',{credential:m.token});
  assert.equal((await call('/api/members','POST',{name:'B'},{Cookie:login.cookie})).status,403);
}));
test('ingestion rejects prompt, response and arbitrary extra fields',()=>fixture(async({call,app})=>{
  const m=app.store.addMember('A');for(const field of ['prompt','conversation','messages','auth_json']){const b=batch();b.events[0][field]='SECRET';const result=await call('/api/ingest','POST',b,{Authorization:'Bearer '+m.token});assert.equal(result.status,400);}
  assert.equal(app.store.db.prepare('SELECT COUNT(*) n FROM events').get().n,0);
}));
test('same upload can be retried without double counting',()=>fixture(async({call,app})=>{
  const m=app.store.addMember('A'),b=batch(),h={Authorization:'Bearer '+m.token};
  assert.equal((await call('/api/ingest','POST',b,h)).body.accepted,1);assert.equal((await call('/api/ingest','POST',b,h)).body.duplicates,1);
  assert.equal(app.store.summary(24).total_tokens,120);
}));
test('percentages reflect measured token shares, not quota consumption',()=>fixture(async({app,call})=>{
  const a=app.store.addMember('A'),b=app.store.addMember('B');
  await call('/api/ingest','POST',batch([event('a',100,20)]),{Authorization:'Bearer '+a.token});
  await call('/api/ingest','POST',batch([event('b',300,60)]),{Authorization:'Bearer '+b.token});
  const s=app.store.summary(24);assert.equal(s.total_tokens,480);assert.equal(s.members.find(m=>m.name==='A').share_percent,25);assert.equal(s.members.find(m=>m.name==='B').share_percent,75);
  assert(!('quota_percent' in s.members[0]));assert.equal(s.metric,'observed_token_share_not_subscription_quota');
}));
test('empty usage reports null shares instead of fabricating zero percent',()=>fixture(async({app})=>{app.store.addMember('A');const s=app.store.summary(24);assert.equal(s.members[0].share_percent,null);}));
test('duplicate event seen on another member is flagged, not charged twice',()=>fixture(async({app})=>{
  const a=app.store.addMember('A'),b=app.store.addMember('B'),one=batch();app.store.ingest(a.id,one);one.device_id=randomUUID();const result=app.store.ingest(b.id,one);assert.equal(result.conflicts,1);assert.equal(app.store.summary(24).total_tokens,120);
}));
test('a device ID already owned by someone cannot be silently reassigned',()=>fixture(async({app,call})=>{
  const a=app.store.addMember('A'),b=app.store.addMember('B'),one=batch();await call('/api/ingest','POST',one,{Authorization:'Bearer '+a.token});
  assert.equal((await call('/api/ingest','POST',one,{Authorization:'Bearer '+b.token})).status,409);
}));
test('revoking member removes ingestion and existing session access',()=>fixture(async({app,call})=>{
  const m=app.store.addMember('A'),login=await call('/api/login','POST',{credential:m.token});app.store.deactivate(m.id);
  assert.equal((await call('/api/ingest','POST',batch(),{Authorization:'Bearer '+m.token})).status,401);
  assert.equal((await call('/api/summary','GET',undefined,{Cookie:login.cookie})).status,401);
}));
test('cross-origin requests rejected and no CORS wildcard',()=>fixture(async({call})=>{
  const r=await call('/api/login','POST',{credential:ADMIN},{Origin:'https://untrusted.example'});assert.equal(r.status,403);assert.equal(r.headers.get('access-control-allow-origin'),null);
}));
test('account-limit snapshots remain separate by reporter and limit pool',()=>fixture(async({app})=>{
  const a=app.store.addMember('A'),b=app.store.addMember('B');const p=batch([]);p.limits=[{limit_id:'codex',observed_at:new Date().toISOString(),primary:{used_percent:40,window_minutes:300,resets_at:1900000000},secondary:null}];
  app.store.ingest(a.id,p);p.device_id=randomUUID();p.limits[0].primary.used_percent=60;app.store.ingest(b.id,p);
  assert.equal(app.store.summary(24).limits.length,2);
}));
test('public remote HTTP rejected by server startup',()=>{assert.throws(()=>createApp({dbPath:':memory:',adminToken:ADMIN,publicUrl:'http://public.example'}),/HTTPS/);} );
test('future timestamps and malformed numeric batches rejected',()=>{
  const b=batch();b.events[0].at=new Date(Date.now()+3600000).toISOString();assert.throws(()=>validateBatch(b));
  const c=batch();c.events[0].total_tokens=-1;assert.throws(()=>validateBatch(c));
});
