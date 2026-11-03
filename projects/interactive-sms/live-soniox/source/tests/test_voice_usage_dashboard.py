from decimal import Decimal
from types import SimpleNamespace

from app.voice.providers.soniox import build_soniox_stt_config, build_soniox_tts_config
from app.voice.usage_sync import _costs, _items
from app.api.voice_usage import _budget, _voice_allowance


def test_client_reference_id_is_sent_to_soniox_stt_and_tts():
    reference = "jm:tenant:tts:00000000-0000-0000-0000-000000000000"
    assert build_soniox_stt_config("auto", reference)["client_reference_id"] == reference
    assert build_soniox_tts_config("ar", reference)["client_reference_id"] == reference


def test_client_reference_id_is_omitted_when_absent():
    assert "client_reference_id" not in build_soniox_stt_config("en")
    assert "client_reference_id" not in build_soniox_tts_config("en")


def test_usage_log_payload_and_cost_variants_are_parsed():
    assert _items({"usage_logs": [{"uuid": "one"}]}) == [{"uuid": "one"}]
    total, input_cost, output_cost = _costs({
        "costs": {"input_audio_cost_usd": "0.01", "output_audio_cost_usd": "0.02"}
    })
    assert total == Decimal("0.03")
    assert input_cost == Decimal("0.01")
    assert output_cost == Decimal("0.02")


def test_budget_alert_thresholds_are_explicit():
    assert _budget(0.0, 0.0)["status"] == "disabled"
    assert _budget(7.9, 10.0)["status"] == "ok"
    assert _budget(8.0, 10.0)["status"] == "warning"
    assert _budget(10.0, 10.0)["status"] == "exceeded"


def test_monthly_voice_allowance_uses_separate_input_and_output_durations():
    rows = [
        SimpleNamespace(operation="stt", input_audio_duration_ms=250 * 60000, output_audio_duration_ms=0),
        SimpleNamespace(operation="tts", input_audio_duration_ms=0, output_audio_duration_ms=270 * 60000),
    ]
    voice_input = _voice_allowance(rows, "stt", 300)
    voice_output = _voice_allowance(rows, "tts", 300)
    assert voice_input == {"used_minutes": 250, "limit_minutes": 300, "remaining_minutes": 50, "status": "yellow"}
    assert voice_output == {"used_minutes": 270, "limit_minutes": 300, "remaining_minutes": 30, "status": "red"}
    assert _voice_allowance([], "stt", 300)["status"] == "green"
    assert _voice_allowance([SimpleNamespace(operation="stt", input_audio_duration_ms=360 * 60000)], "stt", 300)["remaining_minutes"] == 0
