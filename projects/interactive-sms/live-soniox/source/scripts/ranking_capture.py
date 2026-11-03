"""Capture immutable candidates once per bounded approved-data query, before ranking changes."""
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch
from app.knowledge import retrieval as r
from app.answers.orchestration import expand_retrieval_query
from app.core.database import SessionLocal
from scripts.structure_journal import ROOT
H='ac035405-cdac-53e7-b7c0-c4d80ec867a8';S='ad1f684e-b936-5416-af97-23b92be777b7'
CASES=[('hosting-en','What are the chatbot hosting packages and prices?',[H]),('hosting-expanded',expand_retrieval_query('What are the chatbot hosting packages and prices?'),[H]),('hosting-ar','ما أسعار باقات استضافة الشات بوت؟',[H]),('hosting-12-en','How much does 12 months of chatbot hosting cost?',[H]),('hosting-12-ar','كم سعر استضافة الشات بوت لمدة 12 شهراً؟',[H]),('setup-fee','What is the chatbot creation fee in the offer summary?',[S,'48e0abfb-e27b-5f40-8839-28b19b76e3d5']),('creation-period','What creation period is listed in the offer summary?',[S,'bd894e61-de18-563a-a290-879664fd5b40']),('workflow-table','List the stages of how the interactive SMS service works.',['5f13ce87-37b1-5155-a727-3e8a95d2f53e']),('benefit-table','List the business benefits of interactive SMS.',['02fb0249-432c-5f72-949f-37458593061b']),('otp-control','What is OTP and Financial SMS Messaging used for?',['11cc6c6d-23c3-5c42-891c-166e965505e7']),('contact-control','What is the contact email for JorMall?',['0f54b652-6c12-50c7-928a-389a41be5a0f'])]
def main():
 folder=ROOT/'ranking-v3';folder.mkdir(exist_ok=True);p=folder/'candidates.json'
 result=json.loads(p.read_text()) if p.exists() else {'chunks':{},'cases':[]}
 for name,q,expected in CASES:
  if any(c['name']==name for c in result['cases']):continue
  case={'name':name,'question':q,'expected':expected,'status':'STARTED'};result['cases'].append(case);p.write_text(json.dumps(result))
  captured=[];old=r.final_ranked_chunks
  def rank(**kwargs):captured.extend(kwargs['chunks']);return old(**kwargs)
  with SessionLocal() as db,patch.object(r,'final_ranked_chunks',side_effect=rank):found=r.retrieve_client_chunks(question=q,db=db,top_k=5,client_slug='central-e-commerce-co-ltd')
  case.update(status='CAPTURED',baseline_ids=[str(c.chunk_id) for c in found.results],candidates=[{'id':str(c.chunk_id),'similarity':c.similarity} for c in captured],embedding_tokens=found.total_tokens)
  case['baseline_support']=bool(set(expected)&set(case['baseline_ids']))
  for c in captured:
   d=asdict(c);d['chunk_id']=str(d['chunk_id']);d['document_id']=str(d['document_id']);d.pop('similarity');result['chunks'][str(c.chunk_id)]=d
  p.write_text(json.dumps(result,ensure_ascii=False,indent=2));print(name,case['baseline_support'],flush=True)
if __name__=='__main__':main()
