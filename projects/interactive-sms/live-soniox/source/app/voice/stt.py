"""Complete-recording STT boundary with explicit Soniox workflow selection."""
from app.voice.providers.soniox import transcribe_soniox_audio
from app.voice.contracts import normalize_language


def transcribe_recording(audio, *, content_type, language, client_reference_id=""):
    return transcribe_soniox_audio(
        audio,
        content_type=content_type,
        language=normalize_language(language, allow_auto=True),
        client_reference_id=client_reference_id,
    )
