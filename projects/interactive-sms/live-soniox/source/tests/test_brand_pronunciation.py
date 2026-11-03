from unittest.mock import patch
from app.voice.providers import soniox
from app.voice.tts import cache_key

def test_brand_hint_preserves_addresses_and_numbers():
    text='JorMall and Jor-Mall: info@jormall.com https://jormall.com/page jormall.com JOD 12.50; 0790000000.'
    spoken,language=soniox.prepare_soniox_speech(text=text,language='en')
    assert spoken.startswith('Djor Mall and Djor Mall:')
    for exact in ['info@jormall.com','https://jormall.com/page','jormall.com','12.50','0790000000']:assert exact in spoken
    assert language=='en' and text.startswith('JorMall')

def test_arabic_and_selected_language_preserved():
    spoken,language=soniox.prepare_soniox_speech(text='JorMall محمد info@jormall.com',language='en')
    assert language=='en' and 'محمد' in spoken and 'Djor Mall' in spoken
    spoken,language=soniox.prepare_soniox_speech(text='JorMall info@jormall.com',language='ar')
    assert spoken=='جورمول info@jormall.com' and language=='ar'

def test_pronunciation_revision_invalidates_old_audio():
    old=cache_key('tenant','JorMall','en')
    with patch.object(soniox,'TTS_TEXT_REVISION','old'):assert old!=cache_key('tenant','JorMall','en')
