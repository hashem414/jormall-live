import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp,mkdir,writeFile,readFile,rm,stat } from 'node:fs/promises';
import { tmpdir,platform } from 'node:os';
import { join,resolve } from 'node:path';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { createApp } from '../server/server.mjs';
const exec=promisify(execFile);
test('installer in an isolated Linux home copies the skill, protects profile and refuses reassignment', {skip:platform()!=='linux'},async()=>{
  const dir=await mkdtemp(join(tmpdir(),'ctm-install-'));
  const app=createApp({dbPath:join(dir,'db.sqlite'),adminToken:'i'.repeat(43),publicUrl:'http://localhost:8790'});
  await new Promise(r=>app.server.listen(0,'127.0.0.1',r));
  try{
    const home=join(dir,'home'),meter=join(home,'.codex-team-meter'),codexHome=join(home,'.codex');
    await mkdir(codexHome,{recursive:true});
    const member=app.store.addMember('Installer test'),profile=join(dir,'member-profile.json');
    const server='http://127.0.0.1:'+app.server.address().port;
    await writeFile(profile,JSON.stringify({server,token:member.token}),{mode:0o600});
    const env={...process.env,HOME:home,USERPROFILE:home,CTM_HOME:meter,CODEX_HOME:codexHome};
    const result=await exec(process.execPath,[resolve('skills/team-usage-meter/install.mjs'),'--profile',profile,'--accept'],{env,timeout:20000});
    assert(!result.stdout.includes(member.token));
    assert.match(result.stdout,/Installed skill:/);
    for(const file of ['SKILL.md','README_AR.md','install.mjs','uninstall.mjs','scripts/agent.mjs','scripts/parser.mjs','agents/openai.yaml'])
      assert((await stat(join(home,'.agents','skills','team-usage-meter',file))).isFile());
    const config=JSON.parse(await readFile(join(meter,'config.json'),'utf8'));
    assert.equal(config.token,member.token);assert.equal(config.server,server);
    assert.equal((await stat(join(meter,'config.json'))).mode & 0o777,0o600);
    assert.equal(app.store.summary(24).total_tokens,0);
    assert(!(await readFile(join(meter,'state.json'),'utf8')).includes(member.token));
    const other=app.store.addMember('Other member');
    await writeFile(profile,JSON.stringify({server,token:other.token}));
    await assert.rejects(exec(process.execPath,[resolve('skills/team-usage-meter/install.mjs'),'--profile',profile,'--accept'],{env,timeout:20000}),/already linked to another member/);
    assert.equal(JSON.parse(await readFile(join(meter,'config.json'),'utf8')).token,member.token);
  }finally{
    await new Promise(r=>{app.server.close(r);app.server.closeAllConnections();});
    await rm(dir,{recursive:true,force:true});
  }
});
