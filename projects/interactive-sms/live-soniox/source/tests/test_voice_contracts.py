import asyncio
import io
import json
import struct
import threading
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from app.voice import tts
from app.voice.contracts import SpeechRequest,normalize_language
from app.voice.protocol import pcm_frame,completion_frame,error_frame,read_frames
from app.api import voice


@pytest.mark.parametrize('value,expected',[('en','en'),('en-US','en'),('ar','ar'),('ar-JO','ar'),('EN-us','en')])
def test_explicit_language(value,expected):assert normalize_language(value)==expected


def test_automatic_language_is_accepted_only_for_automatic_contracts():
    assert normalize_language('auto',allow_auto=True)=='auto'
    with pytest.raises(ValueError):normalize_language('auto')

@pytest.mark.parametrize('value',['', 'fr','english','en_US',' ar','en<script>'])
def test_invalid_language(value):
    with pytest.raises(ValueError):normalize_language(value)


def test_fragmented_protocol_and_explicit_error():
    class OneByte(io.BytesIO):
        def read(self,size=-1):return super().read(min(size,1) if size>=0 else 1)
    assert b''.join(read_frames(OneByte(pcm_frame(b'\x01\x02')+completion_frame())))==b'\x01\x02'
    for data in [pcm_frame(b'\x01\x02'),pcm_frame(b'\x01\x02')+error_frame(),completion_frame()+b'x',struct.pack('<I',3)+b'abc']:
        with pytest.raises(ValueError):list(read_frames(OneByte(data)))


def test_text_preparation_preserves_facts_and_mixed_names():
    source='**JorMall** — محمد: JOD 12.50, 07/09/2026, 09:30; ref AB-001.\n- Call 0790000000.'
    text=tts.prepare_text(source)
    for part in ['محمد','12.50','07/09/2026','09:30','AB-001','0790000000']:assert part in text
    assert '**' not in text
    assert normalize_language('en')=='en'


def test_long_saved_answer_gets_deterministic_spoken_summary_without_mutation():
    source=(
        'JorMall provides the following communication services:\n'
        '- Client-based SMS Messages: Promotional and transactional campaigns for customer lists.\n'
        '- Smart Reach SMS: Targeted campaigns using approved audience segments.\n'
        '- Premium Messages: Campaign planning and message preparation.\n'
        '- Interactive SMS: Mobile pages, surveys, and customer actions.\n'
        '- International SMS: Messaging to supported countries and operators.\n'
        + ('Additional approved service information. ' * 20)
    )
    original=source
    with patch.object(tts.settings,'voice_speech_summary_max_characters',300):
        speech=tts.speech_text_for_saved_answer(source,'en')
    assert source==original
    assert speech.compacted is True
    assert speech.speech_characters<=300
    assert speech.source_characters>speech.speech_characters
    assert 'Client-based SMS Messages' in speech.text
    assert 'Smart Reach SMS' in speech.text
    assert 'written answer' in speech.text


def test_short_factual_speech_preserves_numbers_and_contact_details():
    source='Email info@jormall.com, phone +962 77 9937272, price JOD 12.50.'
    speech=tts.speech_text_for_saved_answer(source,'en')
    assert speech.text==source
    assert speech.compacted is False


def test_speech_request_defaults_to_automatic_language():
    payload=SpeechRequest(session_id='chat',lead_session_id='lead',message_id=uuid4())
    assert payload.language=='auto'


def test_cache_identity_and_eviction():
    a=tts.cache_key('tenant-a','hello','en')
    assert a!=tts.cache_key('tenant-b','hello','en')
    assert a!=tts.cache_key('tenant-a','hello','ar')
    with patch.object(tts.settings,'soniox_tts_voice','other'):assert a!=tts.cache_key('tenant-a','hello','en')
    with patch.object(tts.settings,'soniox_tts_model','other'):assert a!=tts.cache_key('tenant-a','hello','en')
    cache=tts.AudioCache(limit=4);cache.put('a',b'ab');cache.put('b',b'cde')
    assert cache.get('a') is None and cache.get('b')==b'cde'


def test_success_cache_replay_and_incomplete_not_cached():
    with patch.object(tts,'cache',tts.AudioCache()),patch.object(tts.soniox,'_stream_soniox_realtime_speech',return_value=iter([b'\x01',b'\x02\x03\x04'])) as provider:
        job=tts.SpeechJob(tenant='test',text='Hello.',language='en')
        assert job.read()==b'\x01\x02\x03\x04';assert job.read() is None
        assert job.finished.wait(1)
        replay=tts.SpeechJob(tenant='test',text='Hello.',language='en');assert replay.read()==b'\x01\x02\x03\x04';assert provider.call_count==1
    def broken(**kwargs):
        yield b'\x01\x02';raise RuntimeError('Injected')
    with patch.object(tts,'cache',tts.AudioCache()),patch.object(tts.soniox,'_stream_soniox_realtime_speech',side_effect=broken):
        job=tts.SpeechJob(tenant='test',text='Hello.',language='en');assert job.read()==b'\x01\x02'
        with pytest.raises(tts.VoiceFailure):job.read()
        assert job.finished.wait(1);assert tts.cache.get(job.key) is None


def test_bounded_generation_and_cancellation_cleanup():
    connections=[]
    def waiting(**kwargs):
        event=threading.Event();connection=SimpleNamespace(shutdown=event.set);connections.append(event)
        kwargs['on_connection'](connection,'test');event.wait(2)
        if not kwargs['cancel_event'].is_set():yield b'\x01\x02'
    with patch.object(tts,'cache',tts.AudioCache()),patch.object(tts,'slots',threading.BoundedSemaphore(2)),patch.object(tts.soniox,'_stream_soniox_realtime_speech',side_effect=waiting):
        jobs=[tts.SpeechJob(tenant='test',text=f'Answer {i}.',language='en') for i in range(2)]
        try:
            with pytest.raises(tts.VoiceOverloaded):tts.SpeechJob(tenant='test',text='Overload.',language='ar')
        finally:
            for job in jobs:job.cancel()
        for job in jobs:assert job.finished.wait(2)
        assert tts.slots.acquire(False);assert tts.slots.acquire(False)
        assert not tts.active_jobs


def test_provider_completion_required():
    from app.voice.providers import soniox
    connection=SimpleNamespace(send=lambda x:None,recv=iter([json.dumps({'audio':'AQI='}),json.dumps({'terminated':True})]).__next__,close=lambda:None)
    with patch.object(soniox,'_connect_soniox_websocket',return_value=connection),patch.object(soniox,'soniox_api_key',return_value='test'):
        with pytest.raises(soniox.SonioxSpeechError):list(soniox._stream_soniox_realtime_speech(text='Hello',language='en'))


def test_route_completion_error_and_cancellation():
    message=SimpleNamespace(id=uuid4(),content='Answer A.')
    payload=SpeechRequest(session_id='chat',lead_session_id='lead',message_id=message.id,language='en')
    class Job:
        cached=None
        def __init__(self,**kwargs):self.values=iter([b'\x01\x02',None]);self.cancelled=False
        def read(self):return next(self.values)
        def cancel(self):self.cancelled=True
    async def run():
        with patch.object(voice,'guard'),patch.object(voice,'assistant_message_for_speech',return_value=message):
            job=Job()
            with patch.object(voice,'SpeechJob',return_value=job):
                response=await voice.speak_client_answer('tenant',payload,None)
                assert response.headers['x-voice-compacted']=='false'
                assert response.headers['x-voice-source-characters']=='9'
                assert response.headers['x-voice-speech-characters']=='9'
                assert float(response.headers['x-voice-first-audio-ms'])>=0
                data=b''.join([x async for x in response.body_iterator])
                assert b''.join(read_frames(io.BytesIO(data)))==b'\x01\x02';assert job.cancelled
            job=Job()
            with patch.object(voice,'SpeechJob',return_value=job):
                response=await voice.speak_client_answer('tenant',payload,None)
                await response.body_iterator.__anext__();await response.body_iterator.aclose();assert job.cancelled
            job=Job()
            def read():
                value=next(job.values)
                if value is None:raise tts.VoiceFailure('Injected')
                return value
            job.read=read
            with patch.object(voice,'SpeechJob',return_value=job):
                response=await voice.speak_client_answer('tenant',payload,None)
                data=b''.join([x async for x in response.body_iterator])
                with pytest.raises(ValueError,match='voice_generation_failed'):list(read_frames(io.BytesIO(data)))
        with patch.object(voice,'guard'),patch.object(voice,'assistant_message_for_speech',return_value=None),patch.object(voice,'SpeechJob') as provider:
            with pytest.raises(HTTPException) as error:await voice.speak_client_answer('tenant',payload,None)
            assert error.value.status_code==404;provider.assert_not_called()
    asyncio.run(run())

@pytest.mark.parametrize('failure,status',[(tts.VoiceFailure('Injected'),503),(tts.VoiceOverloaded('Injected'),429),(asyncio.TimeoutError(),503)])
def test_route_initial_failure_and_timeout(failure,status):
    message=SimpleNamespace(id=uuid4(),content='Test answer')
    payload=SpeechRequest(session_id='test',lead_session_id='lead',message_id=message.id,language='ar')
    async def run():
        with patch.object(voice,'guard'),patch.object(voice,'assistant_message_for_speech',return_value=message),patch.object(voice,'SpeechJob',side_effect=failure):
            with pytest.raises(HTTPException) as error:await voice.speak_client_answer('tenant',payload,None)
            assert error.value.status_code==status
    asyncio.run(run())


def test_bounded_bursts_no_audio_mixing():
    from concurrent.futures import ThreadPoolExecutor
    def generate(**kwargs):
        value=kwargs['text'].encode('utf-16-le')
        yield value[:2];yield value[2:]
    def one(i):
        try:job=tts.SpeechJob(tenant='burst',text=f'Number {i}',language='en')
        except tts.VoiceOverloaded:return 'overload'
        result=b''
        try:
            while True:
                chunk=job.read()
                if chunk is None:break
                result+=chunk
            assert result==f'Number {i}'.encode('utf-16-le')
        finally:job.cancel();assert job.finished.wait(2)
        return 'complete'
    with patch.object(tts,'cache',tts.AudioCache()),patch.object(tts.soniox,'_stream_soniox_realtime_speech',side_effect=generate):
        rows=[]
        for count in (1,2,4):
            with ThreadPoolExecutor(max_workers=count) as pool:rows.extend(pool.map(one,range(count*8)))
        assert 'complete' in rows and not tts.active_jobs
        assert tts.cache.size<=tts.cache.limit
