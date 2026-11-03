"""Sync reviewed source into the existing isolated development container without a build."""
import subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
D=['docker','--context','colima-pocket5005']
C=D+['compose','-f','docker-compose.soniox5005.yml','-p','interactive-sms-pocket5005']
def run(args):subprocess.run(args,cwd=ROOT,check=True)
if __name__=='__main__':
    run(C+['up','-d','--no-build'])
    for src,dst in [('app/.','/app/app/'),('tests/.','/app/tests/'),('docs/baselines/.','/app/docs/baselines/'),('scripts/answer_quality_v2.py','/app/scripts/answer_quality_v2.py')]:
        run(D+['cp',src,'interactive-sms-pocket5005-chatbot-1:'+dst])
    run(C+['restart','chatbot'])
    for _ in range(45):
        try:
            if urllib.request.urlopen('http://127.0.0.1:5005/interactive-sms/',timeout=2).status==200:
                print('Local source synchronized; page ready on port 5005');break
        except OSError:pass
        time.sleep(1)
    else:raise SystemExit('Local readiness failed')
