"""Bounded local acceptance. Modes: answers, voice, recordings. Reuses stored results.
Never targets the remote deployment. Audio fixtures and knowledge remain isolated.
"""
import array,io,json,math,re,sys,time,urllib.request,urllib.error,wave
from pathlib import Path
from uuid import UUID,uuid4
from app.core.database import SessionLocal
from app.core.config import settings
from app.knowledge.retrieval import retrieve_client_chunks
from app.answers.orchestration import expand_retrieval_query
from app.conversations.store import assistant_message_for_speech
from app.voice.protocol import read_frames
from scripts.structure_journal import ROOT,record

BASE='http://127.0.0.1:8000/interactive-sms/api/chat/central-e-commerce-co-ltd'
ROOT.mkdir(parents=True,exist_ok=True)


def usage(kind,cap):
    p=ROOT/'usage.json';d=json.loads(p.read_text()) if p.exists() else {}
    if d.get(kind,0)>=cap:raise RuntimeError('Live test cap reached for '+kind)
    d[kind]=d.get(kind,0)+1;p.write_text(json.dumps(d,indent=2))


def request(path,payload):
    return urllib.request.urlopen(urllib.request.Request(BASE+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'}),timeout=120)


def session():
    ids={'session_id':'structure-chat-'+uuid4().hex,'lead_session_id':'structure-lead-'+uuid4().hex}
    with request('/lead',{'session_id':ids['lead_session_id'],'chat_session_id':ids['session_id'],'name':'Local Structure Test','phone':'0790000000','cookie_notice_opened':True,'privacy_notice_opened':True}) as r:assert json.load(r)['success']
    return ids


def normalize(text):return re.sub(r'\s+',' ',text).strip().lower()


def supported(index,answer):
    a=normalize(answer)
    if index in [0,6]:return '150' in a and ('tax' in a or 'ضريب' in a)
    if index in [1,7]:return all(n in a for n in ['30','75','140','200'])
    if index==2:return 'one working day' in a and ('approv' in a or 'material' in a)
    if index==8:return 'يوم عمل' in a and ('موافق' in a or 'معلوم' in a or 'محتوى' in a)
    if index==3:return 'month' in a and 'hosting' in a
    if index==9:return 'شهر' in a and 'استضاف' in a
    if index==4:return 'otp' in a and ('transaction' in a or 'account' in a)
    if index==10:return ('otp' in a or 'التحقق' in a) and ('حساب' in a or 'معامل' in a or 'مالي' in a)
    if index in [5,11]:return 'info@jormall.com' in a
    if index==12:return any(t in a for t in ["don't have",'do not have','no information','not available','not in our','not offer'])
    if index==13:return ('؟' in a or '?' in a) and any(t in a for t in ['تقصد','أي','توضح','حدد'])
    if index==14:return not re.search(r'jod\s*1(?!\d)',a) and '150' in a
    return False


def answers():
    p=ROOT/'answers.json';rows=json.loads(p.read_text()) if p.exists() else []
    baseline={r['index']:r for r in json.loads(Path('/app/docs/baselines/answer-results.json').read_text())}
    for case in json.loads(Path('/app/tests/structure_cases.json').read_text()):
        if any(r['index']==case['index'] for r in rows):continue
        row=dict(case)
        try:
            usage('embedding_queries',16)
            with SessionLocal() as db:found=retrieve_client_chunks(question=expand_retrieval_query(case['question']),db=db,top_k=settings.retrieval_top_k,client_slug='central-e-commerce-co-ltd')
            row['retrieved']=[{'id':str(c.chunk_id),'source':c.original_filename,'similarity':c.similarity} for c in found.results]
            row['expected_support_retrieved']=bool(set(case['expected_chunk_ids'])&{c['id'] for c in row['retrieved']}) if case['expected_chunk_ids'] else None
            ids=session();usage('chat_requests',16)
            with request('/stream',{**ids,'message':case['question']}) as r:events=[json.loads(line) for line in r if line.strip()]
            answer=''
            for e in events:
                if e.get('type')=='delta':answer+=e.get('text','')
                if e.get('type')=='replace':answer=e.get('answer','')
            mid=next((e['message_id'] for e in events if e.get('type')=='saved'),None)
            assert mid and answer,'Answer or committed message ID missing'
            with SessionLocal() as db:message=assistant_message_for_speech(db=db,client_slug='central-e-commerce-co-ltd',**ids,message_id=UUID(mid));assert message and message.content==answer.strip()
            row.update(answer=answer,message_id=mid,session=ids,saved_answer_matches=True,model_called=any(e.get('model_called') for e in events),events=events)
            row['answer_evidence_chunk_ids']=[i.get('chunk_id') for e in events if e.get('type')=='sources' for i in e.get('evidence_bundle',{}).get('items',[])]
            row['expected_support_in_answer_evidence']=bool(set(row['answer_evidence_chunk_ids'])&set(case['expected_chunk_ids'])) if case['expected_chunk_ids'] else None
            row['required_facts_present']=supported(case['index'],answer)
            old=baseline.get(case['index'],{})
            row['exact_baseline_answer_match']=normalize(answer)==normalize(old.get('answer',''))
            row['baseline_required_facts_present']=supported(case['index'],old.get('answer',''))
            row['mechanics']='PASS'
            if not row['required_facts_present'] or row['expected_support_retrieved'] is False:
                row['quality']='KNOWN_BASELINE_FAILURE' if not row['baseline_required_facts_present'] or old.get('expected_support_retrieved') is False else 'FAIL'
                record('answer-'+str(case['index']),'Expected facts/support retrieved',row['quality'],cause='Frozen baseline answer/retrieval behavior; see source trace',fix='No retrieval/model changes',retest=row['quality'],provider='chat/retrieval',language=case['language'])
            else:row['quality']='PASS'
        except Exception as error:
            row['mechanics']='FAIL';row['error']=type(error).__name__;record('answer-'+str(case['index']),'Complete grounded answer with saved ID',row['error'],provider='chat/retrieval',language=case['language'])
        rows.append(row);p.write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(case['index'],row.get('mechanics'),row.get('quality'),flush=True)
    try:
        urllib.request.urlopen(urllib.request.Request(BASE.rsplit('/',1)[0]+'/other-tenant/stream',data=b'{"message":"Hello"}',headers={'Content-Type':'application/json'}),timeout=10)
        cross='FAIL'
    except urllib.error.HTTPError as error:cross='PASS' if error.code==404 else 'FAIL'
    (ROOT/'cross-tenant.json').write_text(json.dumps({'status':cross}))
    return 0 if all(r.get('mechanics')=='PASS' and r.get('quality')=='PASS' for r in rows) and cross=='PASS' else 1


def voice():
    p=ROOT/'voice.json'
    if p.exists():
        previous=json.loads(p.read_text())
        return 0 if len(previous)==2 and all(r.get('status')=='PASS' for r in previous) else 1
    selected=[r for r in json.loads((ROOT/'answers.json').read_text()) if r['index'] in [5,11]];rows=[]
    for answer in selected:
        row={'language':answer['language'],'message_id':answer['message_id']}
        try:
            usage('speech_http_requests',6);start=time.monotonic()
            with request('/speak',{**answer['session'],'message_id':answer['message_id'],'language':answer['language']}) as response:
                assert response.headers['X-Voice-Provider']=='soniox'
                assert response.headers['X-Voice-Model']=='tts-rt-v2' and response.headers['X-Voice-Voice']=='Kayla'
                assert response.headers['X-Assistant-Message-ID']==answer['message_id']
                data=bytearray();first=None
                for chunk in read_frames(response):
                    if first is None:first=time.monotonic()-start
                    data.extend(chunk)
            elapsed=time.monotonic()-start;samples=array.array('h',data)
            duration=len(samples)/24000;rms=math.sqrt(sum((x/32768)**2 for x in samples)/len(samples));clipping=sum(abs(x)>=32760 for x in samples)/len(samples)
            assert duration>.1 and rms>.001 and clipping<.01
            with wave.open(str(ROOT/('soniox-'+answer['language']+'.wav')),'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(data)
            usage('speech_http_requests',6)
            with request('/speak',{**answer['session'],'message_id':answer['message_id'],'language':answer['language']}) as replay:
                assert replay.headers['X-Voice-Cache']=='hit';assert b''.join(read_frames(replay))==data
            row.update(status='PASS',provider='soniox',model='tts-rt-v2',voice='Kayla',first_audio_seconds=first,generation_seconds=elapsed,audio_seconds=duration,rtf=elapsed/duration,rms=rms,clipped_fraction=clipping,replay='PASS',completion='PASS')
        except Exception as error:row.update(status='FAIL',error=type(error).__name__);record('voice-live','Complete Soniox stream with saved ID and cache replay',type(error).__name__,provider='soniox',language=row['language'])
        rows.append(row);p.write_text(json.dumps(rows,indent=2));print(json.dumps(row),flush=True)
    return 0 if len(rows)==2 and all(r['status']=='PASS' for r in rows) else 1


def recordings():
    p=ROOT/'recordings.json'
    if p.exists():
        previous=json.loads(p.read_text())
        return 0 if len(previous)==2 and all(r.get('status')=='PASS' for r in previous) else 1
    rows=[]
    for fixture in json.loads(Path('/app/docs/baselines/recordings.json').read_text()):
        row={'name':fixture['name'],'language':fixture['language'],'baseline_transcript':fixture['transcript']}
        try:
            ids=session();boundary='structure-'+uuid4().hex
            fields={'language':fixture['language'],'lead_session_id':ids['lead_session_id']}
            body=b''.join((f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n').encode() for k,v in fields.items())
            body+=(f'--{boundary}\r\nContent-Disposition: form-data; name="audio"; filename="fixture.wav"\r\nContent-Type: audio/wav\r\n\r\n').encode()+Path(fixture['path']).read_bytes()+f'\r\n--{boundary}--\r\n'.encode()
            usage('stt_requests',4);start=time.monotonic()
            with urllib.request.urlopen(urllib.request.Request(BASE+'/transcribe',data=body,headers={'Content-Type':'multipart/form-data; boundary='+boundary}),timeout=120) as r:result=json.load(r)
            row.update(result=result,seconds=time.monotonic()-start,exact_baseline_transcript_match=normalize(result['transcript'])==normalize(fixture['transcript']))
            numbers=re.findall(r'\d+',fixture['transcript']);row['important_numbers_preserved']=all(n in result['transcript'] for n in numbers)
            row['email_preserved']='info@jormall.com' not in fixture['transcript'] or 'info@jormall.com' in result['transcript']
            row['status']='PASS' if result['language']==fixture['language'] and row['important_numbers_preserved'] and row['email_preserved'] else 'FAIL'
        except Exception as error:row.update(status='FAIL',error=type(error).__name__)
        if row['status']!='PASS':record('recording-'+fixture['name'],'Baseline meaning/numbers preserved',row.get('error','ASR mismatch'),provider='soniox-stt',language=row['language'])
        rows.append(row);p.write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(row['name'],row['status'],flush=True)
    return 0 if len(rows)==2 and all(r['status']=='PASS' for r in rows) else 1

if __name__=='__main__':raise SystemExit({'answers':answers,'voice':voice,'recordings':recordings}[sys.argv[1]]())
