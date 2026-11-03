"""Bounded live smoke: two greetings and two Soniox TTS calls, local isolated app only."""
import array
import json
import math
import time
import urllib.request
import wave
from pathlib import Path
from uuid import uuid4

from app.core.database import SessionLocal
from app.services.conversation_store import latest_assistant_message_for_session

BASE = 'http://127.0.0.1:8000/interactive-sms/api/chat/central-e-commerce-co-ltd'
ART = Path('/tmp/soniox-5005')
ART.mkdir(exist_ok=True)

def request(path, payload):
    return urllib.request.urlopen(urllib.request.Request(BASE + path,
        data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'}), timeout=90)

results = []
for language, greeting in [('en', 'Hello'), ('ar', 'مرحبا')]:
    ids = {'session_id': 'soniox-smoke-' + uuid4().hex, 'lead_session_id': 'soniox-lead-' + uuid4().hex}
    with request('/lead', {'session_id': ids['lead_session_id'], 'chat_session_id': ids['session_id'],
        'name': 'Local Tester', 'phone': '0790000000', 'cookie_notice_opened': True, 'privacy_notice_opened': True}) as response:
        assert json.load(response)['success']
    with request('/stream', {**ids, 'message': greeting}) as response:
        events = [json.loads(line) for line in response.read().decode().splitlines() if line.strip()]
    with SessionLocal() as db:
        saved = latest_assistant_message_for_session(db=db, client_slug='central-e-commerce-co-ltd', session_id=ids['session_id'])
    assert saved and any(event.get('answer') == saved for event in events), 'Saved answer mismatch'
    start = time.monotonic()
    with request('/speak', {**ids, 'language': language}) as response:
        provider = response.headers['X-Voice-Provider']
        assert provider == 'soniox-tts-rt-v2', provider
        assert response.headers['X-Voice-Voice'] == 'Kayla'
        assert 'audio/l16' in response.headers['Content-Type'].lower()
        first = response.read(2)
        ttfa = time.monotonic() - start
        audio = first + response.read()
    samples = array.array('h', audio)
    rms = math.sqrt(sum((v / 32768) ** 2 for v in samples) / len(samples))
    assert len(audio) % 2 == 0 and len(samples) > 2400 and rms > .001
    with wave.open(str(ART / f'{language}.wav'), 'wb') as output:
        output.setparams((1, 2, 24000, 0, 'NONE', 'not compressed')); output.writeframes(audio)
    results.append({'language': language, 'provider': provider, 'model': 'tts-rt-v2', 'voice': 'Kayla',
        'saved_answer_matches': True, 'audio_seconds': len(samples) / 24000, 'rms': rms,
        'first_audio_seconds': ttfa, 'total_seconds': time.monotonic() - start, 'status': 'PASS'})
    print(json.dumps(results[-1]), flush=True)
(ART / 'live-results.json').write_text(json.dumps(results, indent=2))
