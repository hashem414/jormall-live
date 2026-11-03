import { platform,homedir } from 'node:os';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';
import { rm } from 'node:fs/promises';
import { createInterface } from 'node:readline/promises';
const run=(bin,args)=>spawnSync(bin,args,{stdio:'ignore',windowsHide:true});
if(platform()==='win32')run('schtasks.exe',['/Delete','/TN','CodexTeamMeter','/F']);
else if(platform()==='darwin'){const file=join(homedir(),'Library','LaunchAgents','local.codex-team-meter.plist');run('launchctl',['bootout',`gui/${process.getuid()}`,file]);await rm(file,{force:true});}
else{run('systemctl',['--user','disable','--now','codex-team-meter.timer']);for(const file of ['codex-team-meter.timer','codex-team-meter.service'])await rm(join(homedir(),'.config','systemd','user',file),{force:true});run('systemctl',['--user','daemon-reload']);}
console.log('Automatic sync removed. Close any manually started agent.mjs watch process as well.');
const io=createInterface({input:process.stdin,output:process.stdout});
const answer=await io.question('Also delete local meter configuration, numeric queue and skill? Type DELETE: ');io.close();
if(answer==='DELETE'){await rm(join(homedir(),'.codex-team-meter'),{recursive:true,force:true});await rm(join(homedir(),'.agents','skills','team-usage-meter'),{recursive:true,force:true});console.log('Meter files removed. No Codex files were changed or deleted.');}
console.log('Server usage remains until retention expiry. Ask the dashboard administrator to revoke the member key.');
