#!/usr/bin/env python3
"""Upload the three JorMall reference documents and index them once."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests


BACKEND_ROOT = Path(__file__).resolve().parent
DOCUMENTS = (
    {
        "filename": "TRC_SMS_Regulations_2024_Reference_AR.docx",
        "attributes": {
            "language": "ar",
            "document_type": "regulation",
            "document_group": "trc_bulk_sms_2024",
            "source_label": "TRC Arabic",
            "version": "2024",
            "authority_rank": 1,
        },
    },
    {
        "filename": "TRC_SMS_Regulations_2024_Reference_EN.docx",
        "attributes": {
            "language": "en",
            "document_type": "regulation_translation",
            "document_group": "trc_bulk_sms_2024",
            "source_label": "TRC English",
            "version": "2024",
            "authority_rank": 2,
        },
    },
    {
        "filename": "Platform_User_Manual_2025_+_ALT.docx",
        "attributes": {
            "language": "en",
            "document_type": "platform_manual",
            "document_group": "jormall_platform_manual",
            "source_label": "Platform User Manual",
            "version": "2025",
            "authority_rank": 3,
        },
    },
)


WORKSPACE_ROOT = (
    BACKEND_ROOT
    if all((BACKEND_ROOT / spec["filename"]).is_file() for spec in DOCUMENTS)
    else BACKEND_ROOT.parent
)


class IngestionError(RuntimeError):
    pass


class OpenAIIngestionClient:
    def __init__(self, api_key: str, base_url: str, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_key}"})

    def _json_response(self, response: requests.Response) -> dict[str, Any]:
        if not response.ok:
            try:
                detail = response.json().get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                detail = response.text[:300]
            raise IngestionError(f"OpenAI returned HTTP {response.status_code}: {detail}")
        try:
            return response.json()
        except ValueError as exc:
            raise IngestionError("OpenAI returned invalid JSON during ingestion.") from exc

    def create_vector_store(self) -> str:
        response = self.session.post(
            f"{self.base_url}/vector_stores",
            json={"name": "JorMall SMA Knowledge Base"},
            timeout=self.timeout,
        )
        return str(self._json_response(response).get("id") or "")

    def upload_file(self, path: Path) -> str:
        with path.open("rb") as handle:
            response = self.session.post(
                f"{self.base_url}/files",
                data={"purpose": "assistants"},
                files={"file": (path.name, handle, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                timeout=self.timeout,
            )
        return str(self._json_response(response).get("id") or "")

    def attach_file(self, vector_store_id: str, file_id: str, attributes: dict[str, Any]) -> None:
        is_arabic = attributes.get("language") == "ar"
        max_chunk_tokens = 800 if is_arabic else 600
        overlap_tokens = 200 if is_arabic else 120
        response = self.session.post(
            f"{self.base_url}/vector_stores/{vector_store_id}/files",
            json={
                "file_id": file_id,
                "attributes": attributes,
                "chunking_strategy": {
                    "type": "static",
                    "static": {
                        "max_chunk_size_tokens": max_chunk_tokens,
                        "chunk_overlap_tokens": overlap_tokens,
                    },
                },
            },
            timeout=self.timeout,
        )
        self._json_response(response)

    def vector_file_status(self, vector_store_id: str, file_id: str) -> dict[str, Any]:
        response = self.session.get(
            f"{self.base_url}/vector_stores/{vector_store_id}/files/{file_id}",
            timeout=self.timeout,
        )
        return self._json_response(response)


def validate_documents(document_root: Path) -> list[tuple[Path, dict[str, Any]]]:
    resolved = []
    for spec in DOCUMENTS:
        path = document_root / spec["filename"]
        if not path.is_file():
            raise IngestionError(f"Missing document: {path}")
        if path.stat().st_size <= 0:
            raise IngestionError(f"Document is empty: {path}")
        resolved.append((path, dict(spec["attributes"])))
    return resolved


def wait_until_ready(
    client: OpenAIIngestionClient,
    vector_store_id: str,
    file_id: str,
    deadline_seconds: int,
) -> dict[str, Any]:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        status = client.vector_file_status(vector_store_id, file_id)
        state = str(status.get("status") or "")
        if state == "completed":
            return status
        if state in {"failed", "cancelled"}:
            raise IngestionError(f"Vector indexing {state} for {file_id}: {status.get('last_error')}")
        time.sleep(3)
    raise IngestionError(f"Timed out waiting for vector indexing of {file_id}.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--document-root", type=Path, default=WORKSPACE_ROOT)
    parser.add_argument("--vector-store-id", default=os.getenv("OPENAI_VECTOR_STORE_ID", ""))
    parser.add_argument("--manifest", type=Path, default=BACKEND_ROOT / "vector_store_manifest.json")
    parser.add_argument("--base-url", default=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        documents = validate_documents(args.document_root.resolve())
        if args.dry_run:
            print(json.dumps({"ok": True, "documents": [str(path) for path, _ in documents]}, indent=2))
            return 0
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise IngestionError("OPENAI_API_KEY is required.")
        client = OpenAIIngestionClient(api_key, args.base_url)
        vector_store_id = str(args.vector_store_id or "").strip() or client.create_vector_store()
        if not vector_store_id:
            raise IngestionError("OpenAI did not return a vector-store ID.")
        manifest: dict[str, Any] = {
            "vector_store_id": vector_store_id,
            "created_at": int(time.time()),
            "documents": [],
        }
        for path, attributes in documents:
            print(f"Uploading {path.name}...", file=sys.stderr)
            file_id = client.upload_file(path)
            if not file_id:
                raise IngestionError(f"OpenAI did not return a file ID for {path.name}.")
            client.attach_file(vector_store_id, file_id, attributes)
            wait_until_ready(client, vector_store_id, file_id, args.wait_seconds)
            manifest["documents"].append({
                "filename": path.name,
                "file_id": file_id,
                "attributes": attributes,
            })
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        print(f"Manifest saved to {args.manifest}", file=sys.stderr)
        return 0
    except (IngestionError, requests.RequestException, OSError) as exc:
        print(f"Ingestion failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
