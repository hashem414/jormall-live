from __future__ import annotations

import json

from app.api import live_stt


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self, _maximum: int) -> bytes:
        return json.dumps(
            {
                "session": {"id": "live_test"},
                "transport": {"type": "webrtc", "sdp": "v=0\r\n"},
            }
        ).encode()


def test_webrtc_payload_preserves_sdp_terminating_crlf():
    offer = "v=0\r\na=group:BUNDLE 0\r\n"
    payload = live_stt.WebRTCSessionPayload(
        sdp=offer,
        lead_session_id=" lead-session ",
        language="en",
    )
    assert payload.sdp == offer
    assert payload.lead_session_id == "lead-session"


def test_live_sdp_exchange_uses_client_delegation_and_server_key(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(live_stt, "_openai_key", lambda: "server-only-test-key")
    monkeypatch.setattr(live_stt.urllib.request, "urlopen", fake_urlopen)
    payload = live_stt.WebRTCSessionPayload(
        sdp="v=0\r\n",
        lead_session_id="lead-session",
        language="ar",
    )
    result = live_stt._exchange_live_sdp(payload)
    request_body = json.loads(captured["request"].data)

    assert result["session"]["id"] == "live_test"
    assert request_body["transport"]["sdp"] == "v=0\r\n"
    assert request_body["session"]["model"] == "gpt-live-1"
    assert request_body["session"]["delegation"] == {"type": "client"}
    assert request_body["session"]["audio"]["output"]["voice"] == "marin"
    assert "server-only-test-key" not in json.dumps(request_body)
    assert captured["request"].get_header("Authorization") == "Bearer server-only-test-key"
    assert captured["timeout"] == 20
