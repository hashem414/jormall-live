from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import PROFILES_JSONL_PATH
from profiles.profile_builder import load_profiles
from retrieval.document_builder import build_documents, load_documents
from retrieval.lexical_index import build_lexical_index
from retrieval.provider_factory import create_semantic_provider


def main() -> None:
    started = time.perf_counter()
    profiles = load_profiles()
    document_report = build_documents(profiles)
    documents = load_documents()
    source_hash = hashlib.sha256(PROFILES_JSONL_PATH.read_bytes()).hexdigest()
    lexical_report = build_lexical_index(documents, source_hash=source_hash)
    try:
        semantic_report = create_semantic_provider().build(documents, source_hash)
        semantic_status = "PASS"
    except Exception as exc:
        semantic_report = {"provider": "unavailable", "error": str(exc)}
        semantic_status = "PARTIAL"
    report = {
        "documents": document_report,
        "lexical": lexical_report,
        "semantic": semantic_report,
        "semantic_status": semantic_status,
        "total_build_ms": int((time.perf_counter() - started) * 1000),
    }
    (ROOT / "reports" / "index_build_report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
