"""Experimental bounded provider-selectable TTS; copied outside the core tree."""
from collections import OrderedDict
from dataclasses import dataclass
import hashlib
import json
import logging
import queue
import re
import threading
import time
from app.core.config import settings
from app.voice.providers import soniox
from app.services.openai_speech_service import stream_assistant_speech
from app.voice.contracts import normalize_language
from app.voice.protocol import FORMAT


class VoiceFailure(RuntimeError): pass
class VoiceOverloaded(VoiceFailure): pass
class VoiceCancelled(VoiceFailure): pass


@dataclass(frozen=True, slots=True)
class SpeechText:
    text: str
    source_characters: int
    speech_characters: int
    compacted: bool


def _clean_speech_markup(value: str) -> str:
    value=re.sub(r'\[\[(?:image|video):[^\]]*\]\]|\[\[sales_callback_action\]\]','',value,flags=re.I)
    value=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'\1 (\2)',value)
    value=re.sub(r'\*\*|__|`','',value)
    return value.strip()


def _fit_complete_text(value: str, limit: int) -> str:
    value=re.sub(r'\s+',' ',value).strip()
    if len(value)<=limit:return value
    sentences=re.split(r'(?<=[.!?؟])\s+',value)
    selected=[]
    for sentence in sentences:
        candidate=' '.join([*selected,sentence]).strip()
        if not selected and len(candidate)>limit:
            break
        if selected and len(candidate)>limit:break
        selected.append(sentence)
    if selected:return ' '.join(selected).strip()
    boundary=max(value.rfind(' ',0,limit),value.rfind('،',0,limit),value.rfind(',',0,limit))
    if boundary<limit//2:boundary=limit
    return value[:boundary].rstrip(' ،,;:')


def speech_text_for_saved_answer(value: str, language: str) -> SpeechText:
    """Build a concise, deterministic spoken view without changing saved text."""
    clean_language=normalize_language(language)
    source=_clean_speech_markup(value)
    plain=re.sub(r'^\s{0,3}(?:#{1,6}|[-*•]|\d+[.)])\s+','',source,flags=re.M)
    plain=re.sub(r'\s+',' ',plain).strip()
    if not plain:raise VoiceFailure('The saved answer is empty for speech.')
    limit=settings.voice_speech_summary_max_characters
    if len(plain)<=limit:
        return SpeechText(plain,len(plain),len(plain),False)

    lines=[line.strip() for line in source.splitlines() if line.strip()]
    intro=''
    labels=[]
    bullet_pattern=re.compile(r'^\s*(?:[-*•]|\d+[.)])\s+(.+)$')
    for line in lines:
        match=bullet_pattern.match(line)
        if match:
            item=re.sub(r'\s+',' ',match.group(1)).strip()
            label=re.split(r'\s*(?::|：|—|–)\s*',item,maxsplit=1)[0].strip(' .؛;')
            if label and len(label)<=90 and label.casefold() not in {item.casefold() for item in labels}:
                labels.append(label)
        elif not intro:
            intro=re.sub(r'^#{1,6}\s*','',line).strip()

    tail=(
        'التفاصيل الكاملة موجودة في الإجابة المكتوبة.'
        if clean_language=='ar'
        else 'The complete details are shown in the written answer.'
    )
    if labels:
        lead=_fit_complete_text(intro,120).rstrip(' :؛;,.') if intro else (
            'أبرز النقاط' if clean_language=='ar' else 'The main points'
        )
        chosen=[]
        for label in labels:
            separator='؛ ' if clean_language=='ar' else '; '
            listing=separator.join([*chosen,label])
            candidate=f'{lead}: {listing}. {tail}'
            if len(candidate)>limit:break
            chosen.append(label)
        if chosen:
            text=f"{lead}: {('؛ ' if clean_language=='ar' else '; ').join(chosen)}. {tail}"
            return SpeechText(text,len(plain),len(text),True)

    body_limit=max(1,limit-len(tail)-1)
    body=_fit_complete_text(plain,body_limit).rstrip()
    text=f'{body} {tail}'.strip()
    return SpeechText(text,len(plain),len(text),True)


def prepare_text(value):
    # Strip presentation markers only. Keep numbers, qualifiers, names and URLs.
    value=_clean_speech_markup(value)
    value=re.sub(r'^\s{0,3}(?:#{1,6}|[-*•])\s+','',value,flags=re.M)
    value=re.sub(r'\*\*|__|`','',value)
    value=re.sub(r'\s+',' ',value).strip()
    if not value or len(value)>settings.voice_tts_max_characters:
        raise VoiceFailure('The saved answer is empty or too long for speech.')
    return value


def identity():
    if settings.voice_tts_provider == 'openai':
        return {'provider':'openai','model':settings.openai_tts_model,'voice':settings.openai_tts_voice,'format':FORMAT}
    return {'provider':'soniox','model':settings.soniox_tts_model,'voice':settings.soniox_tts_voice,'format':FORMAT}


def cache_key(tenant,text,language):
    data=[tenant,text,language,identity(),soniox.TTS_TEXT_REVISION,settings.soniox_tts_english_speed,settings.soniox_tts_arabic_speed,settings.soniox_tts_reduce_silence]
    return hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class AudioCache:
    def __init__(self,limit=16*1024*1024,ttl=900):
        self.limit=limit;self.ttl=ttl;self.size=0;self.items=OrderedDict();self.lock=threading.Lock()
    def get(self,key):
        with self.lock:
            item=self.items.pop(key,None)
            if item is None:return None
            stamp,data=item
            if time.monotonic()-stamp>self.ttl:self.size-=len(data);return None
            self.items[key]=item;return data
    def put(self,key,data):
        if len(data)>self.limit:return
        with self.lock:
            old=self.items.pop(key,None)
            if old:self.size-=len(old[1])
            while self.items and self.size+len(data)>self.limit:
                _,(_,removed)=self.items.popitem(last=False);self.size-=len(removed)
            self.items[key]=(time.monotonic(),data);self.size+=len(data)


cache=AudioCache()
slots=threading.BoundedSemaphore(2)
END=object()
active_jobs=set()
active_lock=threading.Lock()

def cancel_all():
    with active_lock:jobs=list(active_jobs)
    for job in jobs:job.cancel()
    for job in jobs:job.finished.wait(timeout=1)


class SpeechJob:
    def __init__(self,*,tenant,text,language,client_reference_id=""):
        if not settings.voice_enabled:raise VoiceFailure('Voice is disabled.')
        self.text=prepare_text(text);self.language=normalize_language(language)
        self.client_reference_id=client_reference_id
        self.key=cache_key(tenant,self.text,self.language)
        self.cancelled=threading.Event();self.finished=threading.Event()
        self.queue=queue.Queue(maxsize=8);self.connection=None;self.started=time.monotonic()
        self.cached=cache.get(self.key);self.offset=0;self.thread=None
        if self.cached is not None:self.finished.set()
        if self.cached is None:
            if not slots.acquire(blocking=False):raise VoiceOverloaded('Voice is busy. Please try again shortly.')
            self.thread=threading.Thread(target=self._produce,daemon=True,name='soniox-speech')
            with active_lock:active_jobs.add(self)
            self.thread.start()
    def _connection(self,connection,stream_id):
        self.connection=connection
        if self.cancelled.is_set():connection.shutdown()
    def _put(self,value):
        while not self.cancelled.is_set():
            try:self.queue.put(value,timeout=.1);return
            except queue.Full:
                if time.monotonic()-self.started>settings.voice_generation_timeout_seconds:
                    raise VoiceFailure('Voice generation timed out.')
        raise VoiceCancelled('Voice cancelled.')
    def _produce(self):
        stream=None;complete=bytearray();pending=b''
        try:
            if settings.voice_tts_provider == 'openai':
                stream=stream_assistant_speech(text=self.text,language=self.language)
            else:
                spoken_text, language = soniox.prepare_soniox_speech(text=self.text, language=self.language)
                stream=soniox._stream_soniox_realtime_speech(text=spoken_text,language=language,
                    client_reference_id=self.client_reference_id,cancel_event=self.cancelled,on_connection=self._connection)
            for chunk in stream:
                if self.cancelled.is_set():raise VoiceCancelled('Voice cancelled.')
                if time.monotonic()-self.started>settings.voice_generation_timeout_seconds:
                    raise VoiceFailure('Voice generation timed out.')
                pending+=chunk;count=len(pending)//2*2
                if count:
                    data,pending=pending[:count],pending[count:];complete.extend(data)
                    if len(complete)>16*1024*1024:raise VoiceFailure('Voice output too large.')
                    self._put(data)
            if pending or not complete:raise VoiceFailure('Incomplete or empty audio.')
            if self.cancelled.is_set():raise VoiceCancelled('Voice cancelled.')
            cache.put(self.key,bytes(complete));self._put(END)
        except Exception as error:
            if not self.cancelled.is_set():
                logging.getLogger(__name__).warning('voice_failure provider=%s language=%s type=%s request_id=%s',
                    settings.voice_tts_provider,self.language,type(error).__name__,getattr(error,'request_id',''))
                try:self._put(VoiceFailure('Voice generation failed; the written answer remains available.'))
                except (VoiceCancelled,VoiceFailure):pass
        finally:
            try:
                close = getattr(stream, "close", None)
                if close is not None:close()
            finally:
                self.connection=None;slots.release()
                with active_lock:active_jobs.discard(self)
                self.finished.set()
    def read(self):
        if self.cancelled.is_set():raise VoiceCancelled('Voice cancelled.')
        if self.cached is not None:
            data=self.cached[self.offset:self.offset+8192];self.offset+=len(data)
            return data or None
        while not self.cancelled.is_set():
            try:
                value=self.queue.get(timeout=.1)
                if value is END:return None
                if isinstance(value,Exception):raise value
                return value
            except queue.Empty:
                if time.monotonic()-self.started>settings.voice_generation_timeout_seconds:
                    raise VoiceFailure('Voice generation timed out.')
                if self.finished.is_set():raise VoiceFailure('Voice stream ended unexpectedly.')
        raise VoiceCancelled('Voice cancelled.')
    def cancel(self):
        self.cancelled.set()
        connection=self.connection
        if connection is not None:
            # Interrupt blocked recv without another provider request or event-loop wait.
            try:connection.shutdown()
            except (OSError,AttributeError):pass
