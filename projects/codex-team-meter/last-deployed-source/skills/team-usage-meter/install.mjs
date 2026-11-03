import * as fs from 'node:fs/promises';
import { homedir, platform } from 'node:os';
import { resolve,join,dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'node:crypto';
import { createInterface } from 'node:readline/promises';
import { spawnSync } from 'node:child_process';
import { atomicJSON,syncOnce } from './scripts/agent.mjs';
const source=dirname(fileURLToPath(import.meta.url));
const stateHome=resolve(process.env.CTM_HOME??join(homedir(),'.codex-team-meter'));
const destination=join(homedir(),'.agents','skills','team-usage-meter');
const args=process.argv.slice(2);
function option(name){const i=args.indexOf(name);return i<0?null:args[i+1];}
const io=createInterface({input:process.stdin,output:process.stdout});
const xml=s=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
function command(bin,params){const r=spawnSync(bin,params,{encoding:'utf8',windowsHide:true});if(r.status!==0)throw new Error('Automatic startup installation failed. Run agent.mjs watch manually; see README_AR.md.');}
async function autoStart(agent){
  if(platform()==='win32'){
    // Runs visibly named, as this user, every minute. No admin-level service or hidden persistence.
    // Executable paths only; the token is read from the private local config file.
    const action=`"${process.execPath}" "${agent}" once`;
    command('schtasks.exe',['/Create','/TN','CodexTeamMeter','/SC','MINUTE','/MO','1','/TR',action,'/F']);
    console.log('Windows scheduled task created: CodexTeamMeter (every minute).');
  }else if(platform()==='darwin'){
    const file=join(homedir(),'Library','LaunchAgents','local.codex-team-meter.plist');await fs.mkdir(dirname(file),{recursive:true});
    const value=`<?xml version="1.0" encoding="UTF-8"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Label</key><string>local.codex-team-meter</string><key>ProgramArguments</key><array><string>${xml(process.execPath)}</string><string>${xml(agent)}</string><string>once</string></array><key>StartInterval</key><integer>60</integer><key>RunAtLoad</key><true/></dict></plist>`;
    await fs.writeFile(file,value,{mode:0o600});
    spawnSync('launchctl',['bootout',`gui/${process.getuid()}`,file],{stdio:'ignore'});
    command('launchctl',['bootstrap',`gui/${process.getuid()}`,file]);console.log('macOS LaunchAgent installed (every minute while logged in).');
  }else{
    const dir=join(homedir(),'.config','systemd','user');await fs.mkdir(dir,{recursive:true});
    const quote=s=>'"'+s.replaceAll('\\','\\\\').replaceAll('"','\\"').replaceAll('%','%%')+'"';
    await fs.writeFile(join(dir,'codex-team-meter.service'),`[Unit]\nDescription=Numeric-only Codex team usage sync\n[Service]\nType=oneshot\nExecStart=${quote(process.execPath)} ${quote(agent)} once\nTimeoutStartSec=180\nUMask=0077\n`,{mode:0o600});
    await fs.writeFile(join(dir,'codex-team-meter.timer'),'[Unit]\nDescription=Sync Codex numeric usage every minute\n[Timer]\nOnStartupSec=15\nOnUnitActiveSec=60\nAccuracySec=5\n[Install]\nWantedBy=timers.target\n',{mode:0o600});
    command('systemctl',['--user','daemon-reload']);command('systemctl',['--user','enable','--now','codex-team-meter.timer']);
    console.log('Linux user timer installed. It normally runs while your user session is active.');
  }
}
async function run(){
  const version=Number(process.versions.node.split('.')[0]);if(version<20)throw new Error('Agent requires Node.js 20 or newer.');
  console.log('\nCodex Team Meter — local numeric-only collector\n');
  console.log('Reads local Codex rollout files to extract counters. It does NOT send prompts, responses, code, paths, email, or OpenAI credentials.');
  console.log('It sends numerical tokens, timestamps, anonymous event/device IDs, and optional account-limit snapshots.');
  console.log('Team members can see aggregate usage by display name. This is NOT an official per-person Pro quota meter.\n');
  const profilePath=option('--profile')??await io.question('Path to your member-profile.json: ');
  const profile=JSON.parse(await fs.readFile(resolve(profilePath.trim()),'utf8'));
  if(typeof profile.server!=='string'||typeof profile.token!=='string'||!/^ctm_[A-Za-z0-9_-]{40,100}$/.test(profile.token))throw new Error('Invalid member profile. Obtain your private profile from the dashboard admin.');
  const url=new URL(profile.server);
  if(!['https:','http:'].includes(url.protocol)||url.username||url.password||url.search||url.hash||url.pathname!=='/')throw new Error('Invalid dashboard origin.');
  if(url.protocol!=='https:'&&!['localhost','127.0.0.1','[::1]'].includes(url.hostname))throw new Error('HTTPS is required for a remote server.');
  console.log(`Destination: ${url.origin}`);
  if(!args.includes('--accept')){const answer=await io.question('Do you consent to this numeric-only collection? Type YES: ');if(answer.trim()!=='YES')throw new Error('Canceled. Nothing installed.');}
  await fs.mkdir(stateHome,{recursive:true,mode:0o700});
  const configFile=join(stateHome,'config.json');let old=null;
  try{old=JSON.parse(await fs.readFile(configFile,'utf8'));}catch(e){if(e.code!=='ENOENT')throw e;}
  if(old&&(old.server!==url.origin||old.token!==profile.token))throw new Error('This OS user is already linked to another member/server. Use separate OS users; do not mix their attribution.');
  const codexHome=resolve(option('--codex-home')??process.env.CODEX_HOME??join(homedir(),'.codex'));
  if(old&&old.codexHome!==codexHome)throw new Error('Existing Codex home differs. Do not silently change accounting source. See README.');
  if(resolve(source)!==resolve(destination)){
    for (const relative of ['SKILL.md','README_AR.md','install.mjs','uninstall.mjs','scripts/agent.mjs','scripts/parser.mjs','agents/openai.yaml']) {
      const target=join(destination,relative);await fs.mkdir(dirname(target),{recursive:true});
      await fs.copyFile(join(source,relative),target);
    }
  }
  const config=old??{server:url.origin,token:profile.token,deviceId:randomUUID(),startedAt:new Date().toISOString(),codexHome};
  await atomicJSON(configFile,config);
  if(platform()==='win32'){
    // Restrict local credentials to this signed-in OS user. Do not print token values.
    const who=spawnSync('whoami',[],{encoding:'utf8',windowsHide:true});
    if(who.status===0){const acl=spawnSync('icacls.exe',[stateHome,'/inheritance:r','/grant:r',`${who.stdout.trim()}:(OI)(CI)F`],{encoding:'utf8',windowsHide:true});if(acl.status!==0)console.warn('Could not restrict Windows ACL automatically. Protect your .codex-team-meter folder manually.');}
  }
  console.log(`Installed skill: ${destination}`);
  console.log(`Measurement starts at ${config.startedAt}; old history is NOT imported.`);
  let installAuto=args.includes('--autostart');
  if(!installAuto&&!args.includes('--accept'))installAuto=(await io.question('Enable automatic minute-by-minute sync? Type YES: ')).trim()==='YES';
  if(installAuto){try{await autoStart(join(destination,'scripts','agent.mjs'));}catch(e){console.warn(e.message);}}
  try{const s=await syncOnce({home:stateHome});console.log('Initial sync:',JSON.stringify(s));}catch(e){console.warn(e.message);}
  console.log('\nOpen your dashboard URL. To check locally:');
  console.log(`node "${join(destination,'scripts','agent.mjs')}" status`);
  console.log('Open a new Codex session to discover $team-usage-meter. Scheduled sync does not require invoking the skill.');
}
run().catch(e=>{console.error(e.message);process.exitCode=1;}).finally(()=>io.close());
