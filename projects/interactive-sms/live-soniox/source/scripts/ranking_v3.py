"""Bounded v3 live checks plus reusable acceptance; reuses existing results, no paid loop."""
import hashlib,json,subprocess,sys
from pathlib import Path
from scripts import structure_live
from scripts.structure_journal import ROOT,record
from app.knowledge.retrieval import RetrievedChunk,final_ranked_chunks
OUT=ROOT/'ranking-v3';OUT.mkdir(exist_ok=True)
structure_live.ROOT=OUT
APP=Path(__file__).resolve().parents[1]
def source():return {str(p.relative_to(APP)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (APP/'app').rglob('*') if p.is_file() and '__pycache__' not in str(p)}
def compare():
 fixture=json.loads((APP/'tests/fixtures/ranking-v3-candidates.json').read_text());rows=[]
 for case in fixture['cases']:
  chunks=[RetrievedChunk(**fixture['chunks'][x['id']],similarity=x['similarity']) for x in case['candidates']]
  ids=[str(c.chunk_id) for c in final_ranked_chunks(chunks=chunks,question=case['question'],top_k=5,include_metadata_only=False)]
  row={'name':case['name'],'baseline_support':case['baseline_support'],'support':bool(set(ids)&set(case['expected'])),'baseline_ids':case['baseline_ids'],'new_ids':ids,'expected':case['expected']}
  rows.append(row)
 (OUT/'ranking-comparison.json').write_text(json.dumps(rows,indent=2))
 return 0 if len(rows)==11 and all(r['support'] for r in rows) else 1
def verify():
 code=subprocess.run([sys.executable,'-m','pytest','tests','-q','--tb=short','--junitxml='+str(OUT/'regression.xml')],cwd=APP).returncode
 code=max(code,compare())
 for filename,count in [('answers.json',15),('voice.json',2)]:
  try:
   rows=json.loads((OUT/filename).read_text());assert len(rows)==count
   assert all(r.get('status',r.get('quality'))=='PASS' for r in rows)
   if filename=='answers.json':assert all(r['saved_answer_matches'] for r in rows)
  except (OSError,ValueError,AssertionError):print('FAILED OR BLOCKED:',filename);code=1
 try:
  assert json.loads((OUT/'tested-source.json').read_text())==source()
  assert json.loads((OUT/'cross-tenant.json').read_text())['status']=='PASS'
 except (OSError,ValueError,AssertionError):print('FAILED OR BLOCKED: source/session evidence');code=1
 print('Recorded live acceptance exit:',code,'(No new paid calls in verify)')
 return code
if __name__=='__main__':
 mode=sys.argv[1]
 if mode=='answers':
  if not (OUT/'tested-source.json').exists():(OUT/'tested-source.json').write_text(json.dumps(source(),indent=2))
  raise SystemExit(structure_live.answers())
 raise SystemExit({'compare':compare,'voice':structure_live.voice,'verify':verify}[mode]())
