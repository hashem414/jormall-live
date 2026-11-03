import { createReadStream } from 'node:fs';
import * as fs from 'node:fs/promises';
import { homedir } from 'node:os';
import { join, resolve, basename, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';
import { consumeRecord, freshCursor } from './parser.mjs';
const HASH=v=>createHash('sha256').update(v).digest('hex');
export const HOME=resolve(process.env.CTM_HOME??join(homedir(),'.codex-team-meter'));
export async function atomicJSON(path,value) {
  const tmp=path+'.tmp';await fs.mkdir(dirname(path),{recursive:true,mode:0o700});
  await fs.writeFile(tmp,JSON.stringify(value),{mode:0o600});await fs.rename(tmp,path);
}
async function readJSON(path,fallback) {
  try{return JSON.parse(await fs.readFile(path,'utf8'));}catch(e){if(e.code==='ENOENT')return fallback;throw new Error('Local state is unreadable; stop and restore it rather than silently re-counting.');}
}
export async function walk(dir) {
  let entries;try{entries=await fs.readdir(dir,{withFileTypes:true});}catch(e){if(e.code==='ENOENT')return [];throw e;}
  const out=[];
  for(const e of entries) {
    if(e.isSymbolicLink())continue;
    if(e.isDirectory())out.push(...await walk(join(dir,e.name)));
    else if(e.isFile() && /^rollout-.*\.jsonl$/.test(e.name))out.push(join(dir,e.name));
  }
  return out;
}
/** Read only complete lines. Oversized content is discarded without keeping it in state. */
export async function scanFile(path,cursor,startedAt,onEvent,onLimit,maxBytes=32*1024*1024) {
  const st=await fs.stat(path);
  if(st.size<cursor.offset){cursor.offset=0;cursor.prev=null;cursor.seen=false;cursor.issues++;}
  if(st.size===cursor.offset)return;
  const begin=cursor.offset,end=Math.min(st.size,begin+maxBytes);
  let pos=begin,lineStart=begin,parts=[],length=0,skip=Boolean(cursor.skipContinuation);
  const fileKey=basename(path);
  for await(const chunk of createReadStream(path,{start:begin,end:end-1,highWaterMark:65536})) {
    let start=0;
    for(let i=0;i<chunk.length;i++)if(chunk[i]===10) {
      const piece=chunk.subarray(start,i);length+=piece.length;
      if(!skip && length<=1024*1024){parts.push(piece);let record;
        try{record=JSON.parse(Buffer.concat(parts).toString('utf8'));}catch{cursor.issues++;}
        if(record){const out=consumeRecord(record,cursor,fileKey,startedAt);if(out.event)onEvent(out.event);if(out.limit)onLimit(out.limit);}
      }else cursor.issues++;
      lineStart=pos+i+1;cursor.offset=lineStart;start=i+1;parts=[];length=0;skip=false;cursor.skipContinuation=false;
    }
    if(start<chunk.length){const piece=chunk.subarray(start);length+=piece.length;if(length<=1024*1024&&!skip)parts.push(piece);else{skip=true;parts=[];}}
    pos+=chunk.length;
  }
  // A pathological line > the read budget is skipped to a future newline, never parsed.
  if(cursor.offset===begin && end<st.size && length>1024*1024) {
    cursor.offset=end;cursor.skipContinuation=true;cursor.issues++;
  }
  // Incomplete last lines are reread next tick. Nothing from their content is persisted.
}
export async function collect(config,state) {
  const files=(await Promise.all([walk(join(config.codexHome,'sessions')),walk(join(config.codexHome,'archived_sessions'))])).flat();
  const seen=new Set();
  let processed=0;
  for(const file of files) {
    const key=HASH(basename(file));if(seen.has(key))continue;seen.add(key);
    const cursor=state.files[key]??freshCursor();state.files[key]=cursor;
    // The stored checkpoint does not contain filenames, messages or session IDs.
    await scanFile(file,cursor,Date.parse(config.startedAt),e=>state.outbox.push(e),l=>{
      if(!state.limits[l.limit_id] || l.observed_at>state.limits[l.limit_id].observed_at)state.limits[l.limit_id]=l;
    });
    processed++;
    if(state.outbox.length>=20000)break; // Back-pressure, persist checkpoint, then upload.
  }
  state.filesFound=files.length;state.filesProcessed=processed;
  return state;
}
export async function syncOnce({home=HOME,fetcher=fetch}={}) {
  await fs.mkdir(home,{recursive:true,mode:0o700});
  const lockPath=join(home,'agent.lock');let lock;
  try {lock=await fs.open(lockPath,'wx',0o600);await lock.writeFile(String(process.pid));}
  catch(e){if(e.code!=='EEXIST')throw e;
    const pid=Number(await fs.readFile(lockPath,'utf8').catch(()=>''));
    if(Number.isSafeInteger(pid)&&pid>0){try{process.kill(pid,0);return {busy:true};}catch(err){if(err.code!=='ESRCH')return {busy:true};}}
    await fs.unlink(lockPath).catch(()=>{});return {busy:true,recoveredStaleLock:true};
  }
  try {
    const config=await readJSON(join(home,'config.json'),null);
    if(!config)throw new Error('Run install.mjs first.');
    const u=new URL(config.server);
    if(u.protocol!=='https:' && !(u.protocol==='http:'&&['localhost','127.0.0.1','[::1]'].includes(u.hostname)))throw new Error('HTTPS required except on loopback.');
    if(u.username||u.password||u.search||u.hash||u.pathname!=='/')throw new Error('Server URL must be a plain origin.');
    const state=await readJSON(join(home,'state.json'),{version:1,files:{},limits:{},outbox:[],lastSuccess:null});
    await collect(config,state);
    // Persist checkpoints AND pending numeric events together before networking.
    await atomicJSON(join(home,'state.json'),state);
    const issues=Object.values(state.files).reduce((s,c)=>s+c.issues,0)+(state.conflicts??0)+(state.expired??0);
    let batches=0, conflicts=0,expired=0;
    do {
      const events=state.outbox.slice(0,300);
      const payload={device_id:config.deviceId,events,limits:Object.values(state.limits).slice(0,30),issues,pending:Math.max(0,state.outbox.length-events.length)};
      const response=await fetcher(u.origin+'/api/ingest',{method:'POST',headers:{'Content-Type':'application/json','Authorization':'Bearer '+config.token},body:JSON.stringify(payload),signal:AbortSignal.timeout(15000),redirect:'error'});
      if(!response.ok)throw new Error(`Sync failed (HTTP ${response.status}); numeric events remain queued locally.`);
      const ack=await response.json();if(ack.ok!==true)throw new Error('Unexpected server acknowledgment; queue preserved.');
      state.outbox.splice(0,events.length);state.lastSuccess=new Date().toISOString();conflicts+=ack.conflicts??0;expired+=ack.expired??0;
      state.conflicts=(state.conflicts??0)+(ack.conflicts??0);state.expired=(state.expired??0)+(ack.expired??0);
      await atomicJSON(join(home,'state.json'),state);batches++;
    }while(state.outbox.length && batches<8);
    const status={last_success:state.lastSuccess,pending:state.outbox.length,issues,files_found:state.filesFound,conflicts:state.conflicts??0,expired:state.expired??0,server:u.origin};
    await atomicJSON(join(home,'status.json'),status);
    return status;
  } finally {await lock.close();await fs.unlink(lockPath).catch(()=>{});}
}
async function main() {
  const mode=process.argv[2]??'once';
  if(mode==='status'){
    const status=await readJSON(join(HOME,'status.json'),null);
    console.log(JSON.stringify(status??{message:'No successful sync yet. Run the installer and agent once.'},null,2));return;
  }
  if(!['once','watch'].includes(mode))throw new Error('Usage: node agent.mjs once|watch|status');
  do {
    try{const s=await syncOnce();console.log(JSON.stringify(s));}
    catch(e){console.error(e.message);if(mode==='once')process.exitCode=1;}
    if(mode==='watch')await new Promise(r=>setTimeout(r,15000));
  }while(mode==='watch');
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href)main().catch(e=>{console.error(e.message);process.exitCode=1;});
