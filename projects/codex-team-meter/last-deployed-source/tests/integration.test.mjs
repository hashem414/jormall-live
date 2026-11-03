import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,mkdir,writeFile,readFile,rm,appendFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { createApp } from '../server/server.mjs';
import { syncOnce,atomicJSON } from '../skills/team-usage-meter/scripts/agent.mjs';
const record=(ts,i,o)=>({timestamp:new Date(ts).toISOString(),type:'event_msg',payload:{type:'token_count',info:{total_token_usage:{input_tokens:i,cached_input_tokens:i/2,output_tokens:o,reasoning_output_tokens:o/2,total_tokens:i+o}}}});
test('offline queue survives; later sync retries safely and never uploads conversations',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'ctm-e2e-')),home=join(dir,'meter'),codexHome=join(dir,'codex');
  const app=createApp({dbPath:join(dir,'meter.sqlite'),adminToken:'x'.repeat(43),publicUrl:'http://localhost:8790'});
  await new Promise(r=>app.server.listen(0,'127.0.0.1',r));
  try{
    const m=app.store.addMember('أحمد'),now=Date.now(),port=app.server.address().port;
    await mkdir(join(codexHome,'sessions'),{recursive:true});const file=join(codexHome,'sessions','rollout-test.jsonl');
    await atomicJSON(join(home,'config.json'),{server:'http://127.0.0.1:'+port,token:m.token,deviceId:randomUUID(),startedAt:new Date(now-5000).toISOString(),codexHome});
    await writeFile(file,[record(now-6000,100,20),{type:'response_item',payload:{text:'PRIVATE_CUSTOMER_PASSWORD_DO_NOT_UPLOAD'}},record(now-4000,200,40)].map(x=>JSON.stringify(x)).join('\n')+'\n');
    await assert.rejects(syncOnce({home,fetcher:async()=>{throw new Error('Simulated outage');}}));
    let state=JSON.parse(await readFile(join(home,'state.json'),'utf8'));assert.equal(state.outbox.length,1);assert(!JSON.stringify(state).includes('PRIVATE_CUSTOMER'));assert(!JSON.stringify(state).includes(m.token));
    const transmitted=[];await syncOnce({home,fetcher:async(url,options)=>{transmitted.push(options.body);return fetch(url,options);}});
    assert(!transmitted.join('').includes('PRIVATE_CUSTOMER'));assert.equal(app.store.summary(24).total_tokens,120);
    await syncOnce({home});assert.equal(app.store.summary(24).total_tokens,120);
    await appendFile(file,JSON.stringify(record(now-3000,400,80))+'\n');await syncOnce({home});assert.equal(app.store.summary(24).total_tokens,360);
    state=JSON.parse(await readFile(join(home,'state.json'),'utf8'));assert.equal(state.outbox.length,0);
  }finally{await new Promise(r=>{app.server.close(r);app.server.closeAllConnections();});await rm(dir,{recursive:true,force:true});}
});
test('SQLite state survives server reopen',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'ctm-persist-'));const config={dbPath:join(dir,'db.sqlite'),adminToken:'z'.repeat(40),publicUrl:'http://localhost:8790'};
  try{const app=createApp(config);const m=app.store.addMember('Persistent');app.store.close();const next=createApp(config);assert.equal(next.store.listMembers()[0].name,'Persistent');next.store.close();}finally{await rm(dir,{recursive:true,force:true});}
});
