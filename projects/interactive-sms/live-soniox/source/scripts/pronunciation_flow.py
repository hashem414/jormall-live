"""Two authorized saved-answer generations after the pronunciation repair."""
import io,json,math,array,time,wave
from unittest.mock import patch
from scripts.structure_live import request
from scripts.structure_journal import ROOT,record
from app.voice.protocol import read_frames
from app.voice.providers import soniox
OUT=ROOT/'pronunciation'
def main():
 rows=[]
 for answer in json.loads((ROOT/'response-quality-new.json').read_text()):
  if answer['index'] not in [0,7]:continue
  lang=answer['language'];p=OUT/('app-'+lang+'.json')
  if p.exists():rows.append(json.loads(p.read_text()));continue
  row={'language':lang,'status':'STARTED','message_id':answer['message_id'],'answer':answer['answer']};p.write_text(json.dumps(row))
  try:
   payload={**answer['session'],'message_id':answer['message_id'],'language':lang};start=time.monotonic()
   with request('/speak',payload) as r:
    assert r.headers['X-Voice-Provider']=='soniox' and r.headers['X-Assistant-Message-ID']==answer['message_id']
    row['cache']=r.headers['X-Voice-Cache'];parts=[]
    for b in read_frames(r):
     if not parts:row['first_audio_seconds']=time.monotonic()-start
     parts.append(b)
   data=b''.join(parts);row['generation_seconds']=time.monotonic()-start
   buf=io.BytesIO()
   with wave.open(buf,'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(data)
   (OUT/('app-'+lang+'.wav')).write_bytes(buf.getvalue());samples=array.array('h',data)
   row['audio_seconds']=len(data)/48000;row['rms']=math.sqrt(sum((x/32768)**2 for x in samples)/len(samples));row['clipped_fraction']=sum(abs(x)>=32760 for x in samples)/len(samples)
   assert row['rms']>.001 and row['clipped_fraction']<.01
   with request('/speak',payload) as r:assert r.headers['X-Voice-Cache']=='hit' and b''.join(read_frames(r))==data
   original=soniox.build_soniox_async_stt_config
   def config(language):
    value=original(language);value.pop('context',None);return value
   with patch.object(soniox,'build_soniox_async_stt_config',side_effect=config):
    asr=soniox.transcribe_soniox_audio(buf.getvalue(),content_type='audio/wav',language=lang)
   row.update(status='PASS',unhinted_transcript=asr.transcript,prepared_text=soniox.prepare_soniox_speech(text=answer['answer'],language=lang)[0],replay='PASS',human_listening='PENDING')
   row['email_asr_check']='PASS' if 'info@jormall.com' not in answer['answer'].lower() or 'info@jormall.com' in asr.transcript.lower() else 'UNRESOLVED_MISMATCH'
   row['transport_audio_checks']='PASS'
   if row['email_asr_check']!='PASS':
    row['status']='PARTIAL';record('pronunciation-email-asr','Exact email intelligibility','Unhinted ASR email mismatch',cause='Speech versus recognition cause not established',retest='Human review required',provider='soniox',language=lang)
  except Exception as e:row.update(status='FAIL',error=type(e).__name__);record('pronunciation-app-'+lang,'Complete authorized speech with replay',type(e).__name__,provider='soniox',language=lang)
  rows.append(row);p.write_text(json.dumps(row,ensure_ascii=False,indent=2));print(json.dumps(row,ensure_ascii=False),flush=True)
 return 0 if len(rows)==2 and all(x['status']=='PASS' for x in rows) else 1
if __name__=='__main__':raise SystemExit(main())
