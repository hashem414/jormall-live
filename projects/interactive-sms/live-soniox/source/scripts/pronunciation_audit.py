"""Bounded Soniox pronunciation comparisons, no chatbot/STT configuration changes."""
import io,json,time,wave,sys
from pathlib import Path
from unittest.mock import patch
from app.voice.providers import soniox
from scripts.structure_journal import ROOT,record
OUT=ROOT/'pronunciation';OUT.mkdir(exist_ok=True)
CASES=[('baseline','en','Welcome to Jor-Mall. Jor-Mall helps businesses communicate.'),('jore','en','Welcome to Jore Mall. Jore Mall helps businesses communicate.'),('djor','en','Welcome to Djor Mall. Djor Mall helps businesses communicate.'),('arabic','ar','مرحباً بكم في جُورمول. جُورمول تساعد الشركات على التواصل.')]
def main():
 for name,lang,text in CASES:
  path=OUT/(name+'.json')
  if path.exists():continue
  row={'name':name,'language':lang,'text':text,'provider':'soniox','model':'tts-rt-v2','voice':'Kayla','status':'STARTED'};path.write_text(json.dumps(row))
  try:
   start=time.monotonic();data=b''.join(soniox._stream_soniox_realtime_speech(text=text,language=lang));row['generation_seconds']=time.monotonic()-start
   assert len(data)>4800 and len(data)%2==0
   buf=io.BytesIO()
   with wave.open(buf,'wb') as f:f.setparams((1,2,24000,0,'NONE','not compressed'));f.writeframes(data)
   (OUT/(name+'.wav')).write_bytes(buf.getvalue());row['audio_seconds']=len(data)/48000
   # Remove brand hints for this diagnostic only, not the app's STT configuration.
   original=soniox.build_soniox_async_stt_config
   def config(language):
    value=original(language);value.pop('context',None);return value
   with patch.object(soniox,'build_soniox_async_stt_config',side_effect=config):
    result=soniox.transcribe_soniox_audio(buf.getvalue(),content_type='audio/wav',language=lang)
   row.update(status='GENERATED',unhinted_transcript=result.transcript,confidence=result.confidence,human_listening='PENDING')
  except Exception as e:
   row.update(status='FAIL',error=type(e).__name__);record('pronunciation-'+name,'Complete generation and unhinted ASR',type(e).__name__,provider='soniox',language=lang)
  path.write_text(json.dumps(row,ensure_ascii=False,indent=2));print(json.dumps(row,ensure_ascii=False),flush=True)
 return 0 if all(json.loads((OUT/(n+'.json')).read_text())['status']=='GENERATED' for n,_,_ in CASES) else 1
if __name__=='__main__':raise SystemExit(main())
