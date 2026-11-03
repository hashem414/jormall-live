const assert = require('node:assert/strict');
global.window = {};
require('../app/static/js/voice-protocol.js');
const {decode, pcmResponse} = window.JorMallVoiceProtocol;
function response(bytes) { return new Response(new ReadableStream({start(c) {for (const b of bytes)c.enqueue(Uint8Array.of(b));c.close();}})); }
(async()=>{
 const good=[4,0,0,0,1,2,3,4,0,0,0,0];let result=[];
 for await(const b of decode(response(good)))result.push(...b);
 assert.deepEqual(result,[1,2,3,4]);
 for(const invalid of [good.slice(0,-1),[...good,9],[3,0,0,0,1,2,3]]){
  await assert.rejects(async()=>{for await(const b of decode(response(invalid))){};});
 }
 let cancelled=false;
 const raw=new Response(new ReadableStream({pull(){},cancel(){cancelled=true;}}));
 const reader=pcmResponse(raw).body.getReader();const pending=reader.read();
 await reader.cancel();await pending;assert.equal(cancelled,true);
 console.log('PASS: fragmented PCM, completion, truncation, trailing bytes, alignment, pending-read cancellation');
})().catch(e=>{console.error(e);process.exitCode=1;});
