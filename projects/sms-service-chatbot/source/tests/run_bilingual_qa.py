from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
TEST_SET = ROOT / "tests" / "bilingual_qa_set.json"
BASE_URL = os.getenv("QA_BASE_URL", "http://localhost:3002/sms-service-chatbot").rstrip("/")
CLIENT_SLUG = "jormall-central-e-commerce-co-ltd"


def post_json(url: str, payload: dict) -> tuple[int, str]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=90) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def ensure_lead(session_id: str) -> None:
    status, body = post_json(
        f"{BASE_URL}/api/chat/{CLIENT_SLUG}/lead",
        {
            "session_id": session_id,
            "name": "QA Tester",
            "phone": f"078{int(time.time()) % 10000000:07d}",
            "cookie_consent_accepted": True,
            "privacy_consent_accepted": True,
        },
    )
    if status != 200:
        raise RuntimeError(f"Lead setup failed: HTTP {status}: {body[:500]}")


def stream_answer(session_id: str, question: str, language: str) -> str:
    url = f"{BASE_URL}/api/chat/{CLIENT_SLUG}/stream"
    data = json.dumps(
        {
            "message": question,
            "session_id": session_id,
            "lead_session_id": session_id,
            "language": language,
            "history": [],
            "evidence_history": [],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/x-ndjson"},
        method="POST",
    )

    answer = ""
    with request.urlopen(req, timeout=180) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "replace":
                answer = str(event.get("answer") or "")
            elif event.get("type") == "delta":
                answer += str(event.get("text") or "")
            elif event.get("type") == "error":
                raise RuntimeError(str(event.get("message") or "stream error"))
    return answer.strip()


def matches(answer: str, expected_any: list[str]) -> list[str]:
    lowered = answer.lower()
    return [term for term in expected_any if term.lower() in lowered]


def main() -> int:
    cases = json.loads(TEST_SET.read_text(encoding="utf-8"))
    session_id = f"qa-{int(time.time())}"
    ensure_lead(session_id)

    failures = []
    for case in cases:
        print(f"RUN {case['id']}: {case['question']}")
        try:
            answer = stream_answer(session_id, case["question"], case["language"])
        except (HTTPError, URLError, RuntimeError) as error:
            failures.append((case["id"], f"request failed: {error}"))
            print(f"FAIL {case['id']}: {error}")
            continue

        found = matches(answer, case["expected_any"])
        preview = " ".join(answer.split())[:240]
        print(f"FOUND {found}")
        print(f"ANSWER {preview}")
        if not found:
            failures.append((case["id"], "no expected terms found"))
            print(f"FAIL {case['id']}: no expected terms found")
        else:
            print(f"PASS {case['id']}")

    if failures:
        print("FAILURES")
        for case_id, reason in failures:
            print(f"- {case_id}: {reason}")
        return 1

    print(f"PASS all {len(cases)} bilingual QA cases")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
