"""Validate the comprehensive eval catalogue or run safe cases against the chatbot."""

from __future__ import annotations

import argparse
import sys
import uuid
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.chatbot_eval_cases import CASES  # noqa: E402


def validate_catalogue() -> int:
    ids = [case["id"] for case in CASES]
    if len(ids) != len(set(ids)):
        duplicates = [item for item, count in Counter(ids).items() if count > 1]
        raise AssertionError(f"Duplicate case ids: {duplicates}")

    required = {"id", "category", "language", "question", "expected", "required_any", "forbidden", "safe_live"}
    for case in CASES:
        missing = required - set(case)
        if missing:
            raise AssertionError(f"{case.get('id', '?')} missing {sorted(missing)}")
        if not case["question"].strip() or not case["expected"].strip():
            raise AssertionError(f"{case['id']} has empty content")

    categories = Counter(case["category"] for case in CASES)
    safe = sum(bool(case["safe_live"]) for case in CASES)
    print(f"Validated {len(CASES)} cases ({safe} safe live cases)")
    for category, count in sorted(categories.items()):
        print(f"  {category}: {count}")
    return 0


def _matches(answer: str, values: list[str]) -> bool:
    folded = answer.casefold()
    return any(value.casefold() in folded for value in values)


def _cleanup_session(session_id: str) -> None:
    if not session_id.startswith("eval-"):
        raise ValueError("Refusing to clean a non-eval session")
    from app.db import get_conn

    with get_conn() as conn:
        conn.execute(
            "DELETE FROM conversations WHERE session_id = %s AND channel = 'eval'",
            (session_id,),
        )


def run_live(category: str | None, case_ids: list[str], limit: int | None, keep_sessions: bool) -> int:
    from app.engine import chat

    selected = [
        case for case in CASES
        if case["safe_live"]
        and (category is None or case["category"] == category)
        and (not case_ids or case["id"] in case_ids)
    ]
    if limit is not None:
        selected = selected[:limit]

    failures = 0
    run_id = uuid.uuid4().hex[:10]
    for index, case in enumerate(selected, 1):
        session_id = f"eval-{run_id}-{case['id']}"
        try:
            result = chat(
                case["question"],
                session_id=session_id,
                channel="eval",
                lang=case["language"],
            )
        finally:
            if not keep_sessions:
                _cleanup_session(session_id)
        answer = result.answer
        errors = []
        if case["required_any"] and not _matches(answer, case["required_any"]):
            errors.append(f"missing any of {case['required_any']}")
        found_forbidden = [value for value in case["forbidden"] if value.casefold() in answer.casefold()]
        if found_forbidden:
            errors.append(f"forbidden {found_forbidden}")
        stateful = {"capture_lead", "book_appointment", "cancel_appointment", "escalate", "send_email_code"}
        used = {call["name"] for call in result.tool_calls}
        if used & stateful:
            errors.append(f"unsafe tool calls {sorted(used & stateful)}")

        status = "PASS" if not errors else "FAIL"
        print(f"[{index:03d}] {status} {case['id']}")
        if errors:
            failures += 1
            print("      " + "; ".join(errors))
            print("      " + answer.replace("\n", " ")[:300])

    print(f"Live result: {len(selected) - failures}/{len(selected)} passed")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Run safe cases through the real chatbot")
    parser.add_argument("--category")
    parser.add_argument("--case", action="append", default=[], dest="case_ids")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--keep-sessions", action="store_true")
    args = parser.parse_args()
    validate_catalogue()
    return run_live(args.category, args.case_ids, args.limit, args.keep_sessions) if args.live else 0


if __name__ == "__main__":
    raise SystemExit(main())
