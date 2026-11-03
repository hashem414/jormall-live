from app.language_detection import detect_supported_language, detected_token_language


def test_dominant_language_ignores_a_single_foreign_name():
    assert detect_supported_language("What services are available for محمد today?") == "en"
    assert detect_supported_language("ما هي خدمات JorMall المتوفرة اليوم؟") == "ar"


def test_short_mixed_text_uses_the_first_language_bearing_word_on_a_tie():
    assert detect_supported_language("مرحبا JorMall") == "ar"
    assert detect_supported_language("Hello محمد") == "en"


def test_nonlinguistic_text_uses_a_safe_fallback():
    assert detect_supported_language("1234", fallback="ar") == "ar"
    assert detect_supported_language("1234", fallback="unknown") == "en"


def test_contact_addresses_do_not_outvote_the_surrounding_language():
    assert detect_supported_language("البريد الإلكتروني: info@jormall.com") == "ar"
    assert detect_supported_language("Email: info@jormall.com") == "en"
    assert detect_supported_language("تفضل بزيارة https://jormallapp.com/help") == "ar"


def test_provider_token_language_is_authoritative_when_available():
    tokens = [
        {"text": "Tell ", "language": "en"},
        {"text": "me ", "language": "en"},
        {"text": "محمد", "language": "en"},
    ]
    assert detected_token_language(tokens, transcript="Tell me محمد") == "en"
    assert detected_token_language([], transcript="ما هي الأسعار؟") == "ar"
