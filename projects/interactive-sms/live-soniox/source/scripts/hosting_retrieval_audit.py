"""Read-only hosting retrieval trace. Three bounded query embeddings; no tuning."""
import json
from unittest.mock import patch
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.document import DocumentChunk,Document
from app.knowledge import retrieval
from app.answers.orchestration import expand_retrieval_query
from scripts.structure_journal import ROOT
TARGET='ac035405-cdac-53e7-b7c0-c4d80ec867a8'
def main():
 p=ROOT/'answer-quality-v2/hosting-trace.json';p.parent.mkdir(exist_ok=True)
 if p.exists():return
 rows=[]
 for q in ['What are the chatbot hosting packages and prices?',expand_retrieval_query('What are the chatbot hosting packages and prices?'),'ما أسعار باقات استضافة الشات بوت؟']:
  captured=[];original=retrieval.create_embeddings
  def embed(*args,**kwargs):
   result=original(*args,**kwargs);captured.append(result);return result
  with SessionLocal() as db,patch.object(retrieval,'create_embeddings',side_effect=embed):
   result=retrieval.retrieve_client_chunks(question=q,db=db,top_k=5,client_slug='central-e-commerce-co-ltd')
   dist=DocumentChunk.embedding.cosine_distance(captured[0].embeddings[0])
   ranked=db.execute(select(DocumentChunk.id,DocumentChunk.content,dist).join(Document,Document.id==DocumentChunk.document_id).where(DocumentChunk.client_slug=='central-e-commerce-co-ltd',Document.client_slug=='central-e-commerce-co-ltd',Document.status=='active',Document.visibility=='client',DocumentChunk.embedding.is_not(None)).order_by(dist)).all()
   target=next(({'vector_rank':i+1,'similarity':1-float(d),'content':c} for i,(id,c,d) in enumerate(ranked) if str(id)==TARGET),None)
   rows.append({'query':q,'target':target,'top5':[{'id':str(c.chunk_id),'similarity':c.similarity,'lexical_bonus':retrieval.table_lexical_score(question=q,chunk=c),'content':c.content} for c in result.results],'target_in_final':any(str(c.chunk_id)==TARGET for c in result.results),'vector_candidate_limit':20,'embedding_tokens':result.total_tokens})
  p.write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps({'query':q,'target':{k:v for k,v in (target or {}).items() if k!='content'},'target_in_final':rows[-1]['target_in_final']}),flush=True)
if __name__=='__main__':main()
