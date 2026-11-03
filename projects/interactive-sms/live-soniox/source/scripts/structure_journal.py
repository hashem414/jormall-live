import json
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('/app/artifacts/soniox-5005/structure-implementation') if Path('/app/app').exists() else Path(__file__).resolve().parents[1]/'artifacts/soniox-5005/structure-implementation'

def record(test,expected,actual,*,cause='',fix='',retest='PENDING',impact='',provider='local',language='en/ar'):
    ROOT.mkdir(parents=True,exist_ok=True)
    row={'timestamp':datetime.now(timezone.utc).isoformat(),'test':test,'provider':provider,'language':language,'expected':expected,'actual':actual,'cause':cause,'fix':fix,'retest':retest,'impact':impact}
    with (ROOT/'failures.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
