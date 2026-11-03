"""Isolated lifecycle and verification. Offline mode never makes provider requests."""
import hashlib,json,socket,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
COMPOSE=['docker','--context','colima-pocket5005','compose','-f','docker-compose.soniox5005.yml','-p','interactive-sms-pocket5005']
ART=ROOT/'artifacts/soniox-5005/structure-implementation'
def run(args):return subprocess.run(args,cwd=ROOT).returncode
def main(mode):
 if mode=='start':
  # An occupied port may be this app; Compose will never kill its owner.
  with socket.socket() as s:
   if s.connect_ex(('127.0.0.1',5005))==0:
    running=subprocess.check_output(COMPOSE+['ps','--format','json'],cwd=ROOT,text=True)
    if '127.0.0.1' not in running or '5005' not in running:raise SystemExit('Port 5005 occupied by an unrelated listener; left untouched.')
  return run(COMPOSE+['up','-d','--build'])
 if mode=='stop':return run(COMPOSE+['stop'])
 if mode=='rollback':return run(COMPOSE+['-f','deployment/soniox-baseline-rollback.yml','up','-d','--no-build','chatbot'])
 if mode in ('offline','verify'):
  code=run(COMPOSE+['exec','-T','chatbot','python','-m','pytest','tests','-q','--tb=short','--junitxml=/app/artifacts/soniox-5005/structure-implementation/regression-final.xml'])
  code=max(code,run(['node','tests/test_voice_protocol.js']))
  if mode=='offline':print('OFFLINE REGRESSION ONLY; no live acceptance claim');return code
  try:
   manifest=json.loads((ART/'tested-source.json').read_text())
   assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in manifest.items())
  except (OSError,ValueError,AssertionError):print('BLOCKED: source differs from recorded verification');code=1
  required={'answers.json':15,'voice.json':2,'recordings.json':2}
  for file,count in required.items():
   try:
    rows=json.loads((ART/file).read_text());assert len(rows)==count
    assert all(r.get('status',r.get('quality'))=='PASS' for r in rows)
   except (OSError,ValueError,AssertionError):print('FAILED OR BLOCKED:',file);code=1
  for name in ('chromium','webkit'):
   try:assert json.loads((ART/('browser-'+name+'.json')).read_text())['status']=='PASS'
   except (OSError,ValueError,AssertionError):print('FAILED OR BLOCKED: browser',name);code=1
  try:
   approval=json.loads((ART/'human-approval.json').read_text())
   assert approval.get('approved') is True and approval.get('reviewer') and approval.get('date')
  except (OSError,ValueError,AssertionError):
   print('HUMAN VOICE-QUALITY APPROVAL: PENDING; deployment acceptance remains incomplete');code=1
  return code
 raise SystemExit('Use start, stop, offline, verify, rollback. Live tests: python -m scripts.structure_live <answers|voice|recordings> inside container.')
if __name__=='__main__':raise SystemExit(main(sys.argv[1]))
