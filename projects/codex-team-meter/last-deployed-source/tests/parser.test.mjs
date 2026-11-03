import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,writeFile,appendFile,readFile,rm,mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { consumeRecord,freshCursor,counters,sanitizeLimits } from '../skills/team-usage-meter/scripts/parser.mjs';
import { scanFile,collect } from '../skills/team-usage-meter/scripts/agent.mjs';
const start=Date.parse('2026-09-20T10:00:00.000Z');
const usage=(i=100,o=20)=>({input_tokens:i,cached_input_tokens:Math.floor(i/2),output_tokens:o,reasoning_output_tokens:Math.floor(o/2),total_tokens:i+o});
const event=(time,counts=usage(),extra={})=>({timestamp:new Date(time).toISOString(),type:'event_msg',payload:{type:'token_count',info:{total_token_usage:counts,last_token_usage:counts},...extra}});
const consume=(r,c)=>consumeRecord(r,c,'rollout-opaque-id.jsonl',start);
test('numeric extraction excludes conversation, reasoning text and credentials',()=>{
  const c=freshCursor();
  for(const type of ['response_item','user_message','agent_reasoning','tool_result'])assert.equal(consume({type,payload:{text:'TOP_SECRET_MESSAGE',auth:'SECRET'}},c).event,null);
  const r=event(start+1,usage(),{prompt:'SECRET',email:'PERSON@example.com'});const result=consume(r,c);
  assert.deepEqual(Object.keys(result.event).sort(),['id','at','input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens','total_tokens'].sort());
  assert(!JSON.stringify(result).includes('SECRET'));assert(!JSON.stringify(c).includes('SECRET'));
});
test('existing session history becomes baseline, not newly attributed use',()=>{
  const c=freshCursor();assert.equal(consume(event(start-1000,usage(500,100)),c).event,null);
  assert.equal(consume(event(start+1000,usage(650,130)),c).event.total_tokens,180);
});
test('cumulative totals are differenced; repeated token and limit notifications do not duplicate',()=>{
  const c=freshCursor();assert.equal(consume(event(start+1,usage()),c).event.total_tokens,120);
  assert.equal(consume(event(start+2,usage()),c).event,null);
  assert.equal(consume(event(start+3,usage(200,40)),c).event.total_tokens,120);
  assert.equal(consume({timestamp:new Date(start+4).toISOString(),type:'event_msg',payload:{type:'token_count',info:null}},c).event,null);
});
test('cache and reasoning are subsets, not extra billable counts',()=>{
  const c=freshCursor(),e=consume(event(start+1,usage()),c).event;
  assert.equal(e.total_tokens,e.input_tokens+e.output_tokens);assert.equal(e.total_tokens,120);
});
test('negative, unsafe and inconsistent numeric records rejected',()=>{
  assert.equal(counters({...usage(),input_tokens:-1}),null);
  assert.equal(counters({...usage(),total_tokens:90000000000000}),null);
  assert.equal(counters({...usage(),cached_input_tokens:101}),null);
  assert.equal(counters({...usage(),reasoning_output_tokens:21}),null);
  assert.equal(counters({...usage(),total_tokens:9999}),null);
});
test('artificial context fill is not counted; following sample re-baselines',()=>{
  const c=freshCursor();consume(event(start+1,usage()),c);
  assert.equal(consume(event(start+2,{input_tokens:0,cached_input_tokens:0,output_tokens:0,reasoning_output_tokens:0,total_tokens:200000}),c).event,null);
  assert.equal(consume(event(start+3,usage(200,40)),c).event,null);
  assert.equal(c.issues,2);
});
test('counter reset fails closed rather than double counting',()=>{
  const c=freshCursor();consume(event(start+1,usage(500,100)),c);
  assert.equal(consume(event(start+2,usage(100,20)),c).event,null);
  assert.equal(consume(event(start+3,usage(200,40)),c).event.total_tokens,120);
  assert.equal(c.issues,1);
});
test('fork inherited history not counted under the fork',()=>{
  const c=freshCursor();consume({type:'session_meta',timestamp:new Date(start+1000).toISOString(),payload:{forked_from_id:'private-id',timestamp:new Date(start+1000).toISOString()}},c);
  assert.equal(consume(event(start+100,usage(1000,200)),c).event,null);
  assert.equal(consume(event(start+2000,usage(1100,220)),c).event.total_tokens,120);
  assert(!JSON.stringify(c).includes('private-id'));
});
test('rate-limit snapshots keep zero and remove account/credit fields',()=>{
  const l=sanitizeLimits({limit_id:'codex',limit_name:'PRIVATE',email:'SECRET',credits:{balance:'99'},primary:{used_percent:0,window_minutes:300,resets_at:1900000000,secret:'S'},secondary:null},new Date(start).toISOString());
  assert.equal(l.primary.used_percent,0);assert.equal(l.primary.window_minutes,300);
  assert(!JSON.stringify(l).includes('SECRET'));assert(!JSON.stringify(l).includes('balance'));assert(!JSON.stringify(l).includes('PRIVATE'));
  assert.equal(sanitizeLimits({primary:{used_percent:101}},new Date(start).toISOString()),null);
});
test('trailing incomplete JSON line survives restart without double count',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'ctm-parser-'));try{
    const file=join(dir,'rollout-test.jsonl'),c=freshCursor(),events=[];
    const line=JSON.stringify(event(start+1));await writeFile(file,line.slice(0,40));await scanFile(file,c,start,e=>events.push(e),()=>{});assert.equal(c.offset,0);
    await appendFile(file,line.slice(40)+'\n');await scanFile(file,c,start,e=>events.push(e),()=>{});assert.equal(events.length,1);
    await scanFile(file,c,start,e=>events.push(e),()=>{});assert.equal(events.length,1);
    assert.equal(c.offset,Buffer.byteLength(line+'\n'));
  }finally{await rm(dir,{recursive:true,force:true});}
});
test('large private content is discarded locally and next usage event still counted',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'ctm-large-'));try{
    const file=join(dir,'rollout-large.jsonl'),c=freshCursor(),events=[];
    await writeFile(file,JSON.stringify({type:'response_item',payload:{text:'PRIVATE'.repeat(170000)}})+'\n'+JSON.stringify(event(start+1))+'\n');
    await scanFile(file,c,start,e=>events.push(e),()=>{});assert.equal(events.length,1);assert(!JSON.stringify(c).includes('PRIVATE'));
  }finally{await rm(dir,{recursive:true,force:true});}
});
test('only rollout files are scanned; auth.json and ordinary files are not opened',async()=>{
  const dir=await mkdtemp(join(tmpdir(),'ctm-files-'));try{
    await mkdir(join(dir,'sessions'),{recursive:true});await writeFile(join(dir,'auth.json'),'NOT_VALID_JSON_SECRET');
    await writeFile(join(dir,'sessions','other.jsonl'),JSON.stringify(event(start+1))+'\n');
    await writeFile(join(dir,'sessions','rollout-test.jsonl'),JSON.stringify(event(start+1))+'\n');
    const s={files:{},limits:{},outbox:[]};await collect({codexHome:dir,startedAt:new Date(start).toISOString()},s);
    assert.equal(s.filesFound,1);assert.equal(s.outbox.length,1);assert(!JSON.stringify(s).includes('SECRET'));assert(!JSON.stringify(s).includes('rollout-test'));
  }finally{await rm(dir,{recursive:true,force:true});}
});
