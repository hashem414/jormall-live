"""Eight bounded fresh local answers. Preserve chatbot model and retrieval policy."""
import json
from scripts.structure_live import request,session
from scripts.structure_journal import ROOT,record
CASES=[('en','How long does it take to create the campaign chatbot?','One working day after complete materials and approval'),('ar','كم يستغرق إنشاء شات بوت الحملة؟','يوم عمل بعد المعلومات الكاملة والموافقة'),('en','What are the chatbot hosting packages and prices?','JOD 30/75/140/200 for 1/3/6/12 months'),('ar','ما أسعار باقات استضافة الشات بوت؟','30/75/140/200 لأشهر 1/3/6/12'),('en','What is the exact price of your Mars delivery service?','Explicitly acknowledge no approved information'),('ar','كم سعره؟','Ask which service'),('en','What is the contact email for JorMall?','info@jormall.com, concise answer'),('ar','ما البريد الإلكتروني للتواصل مع جورمول؟','info@jormall.com, concise answer')]
def main():
 p=ROOT/'response-quality-new.json';rows=json.loads(p.read_text()) if p.exists() else []
 for i,(lang,q,expect) in enumerate(CASES):
  if any(x['index']==i for x in rows):continue
  row={'index':i,'language':lang,'question':q,'expected':expect,'status':'STARTED'};rows.append(row);p.write_text(json.dumps(rows))
  try:
   ids=session()
   with request('/stream',{**ids,'message':q}) as r:events=[json.loads(l) for l in r if l.strip()]
   answer=''
   for e in events:
    if e.get('type')=='delta':answer+=e.get('text','')
    if e.get('type')=='replace':answer=e.get('answer','')
   mid=next((e['message_id'] for e in events if e.get('type')=='saved'),None)
   assert mid and answer
   row.update(status='ANSWERED',answer=answer,message_id=mid,session=ids,events=events,model_called=any(e.get('model_called') for e in events),words=len(answer.split()))
  except Exception as e:row.update(status='FAIL',error=type(e).__name__);record('quality-new-'+str(i),'Saved answer',type(e).__name__,provider='chat',language=lang)
  p.write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(i,row['status'],row.get('answer'),flush=True)
 return 0 if len(rows)==8 and all(r['status']=='ANSWERED' for r in rows) else 1
if __name__=='__main__':raise SystemExit(main())
