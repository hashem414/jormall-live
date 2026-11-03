from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from docx import Document as DocxDocument
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from app.services.client_config_service import DATA_DIR
from app.services.public_branding_service import canonicalize_company_aliases


MANIFEST_PATH = DATA_DIR / "runtime" / "authoritative_sources.json"
MAX_CHUNK_CHARACTERS = 1800
SOURCE_TRANSFORM_REVISION = "jormall-public-brand-v1"


def _document_blocks(path: Path) -> list[tuple[str, str]]:
    document = DocxDocument(path)
    blocks: list[tuple[str, str]] = []
    for child in document.element.body.iterchildren():
        if child.tag.endswith("}p"):
            paragraph = Paragraph(child, document)
            text = paragraph.text.strip()
            if text:
                style = str(paragraph.style.name or "") if paragraph.style else ""
                kind = "heading" if style.lower().startswith("heading") else "paragraph"
                blocks.append((kind, text))
        elif child.tag.endswith("}tbl"):
            table = Table(child, document)
            for row in table.rows:
                cells = [re.sub(r"\s+", " ", cell.text).strip() for cell in row.cells]
                text = " | ".join(cell for cell in cells if cell)
                if text:
                    blocks.append(("table", text))
    return blocks


def _pdf_blocks(path: Path) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []
    for page in PdfReader(str(path)).pages:
        text = (page.extract_text() or "").strip()
        for paragraph in re.split(r"\n{2,}", text):
            cleaned = re.sub(r"[ \t]+", " ", paragraph).strip()
            if cleaned:
                blocks.append(("paragraph", cleaned))
    return blocks


def _approved_source_blocks(path: Path) -> list[tuple[str, str]]:
    if path.suffix.casefold() == ".docx":
        blocks = _document_blocks(path)
    elif path.suffix.casefold() == ".pdf":
        blocks = _pdf_blocks(path)
    else:
        raise ValueError(f"Unsupported approved source type: {path.suffix}")
    return [
        (kind, canonicalize_company_aliases(text))
        for kind, text in blocks
    ]


def _looks_like_section_title(text: str) -> bool:
    return bool(
        len(text) <= 90
        and (
            re.match(r"^\d+(?:\.\d+)*\.\s+", text)
            or text.startswith("Product Name:")
            or text in {"Commercial Offer", "All Prices are Subject to Sales Tax."}
        )
    )


def _chunk_blocks(blocks: list[tuple[str, str]]) -> list[dict[str, str | int]]:
    chunks: list[dict[str, str | int]] = []
    section = "Commercial Offer"
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        chunks.append(
            {
                "chunk_index": len(chunks),
                "section_title": section,
                "content": "\n".join(buffer).strip(),
            }
        )
        buffer.clear()

    for kind, text in blocks:
        if kind == "heading" or _looks_like_section_title(text):
            flush()
            section = text
            buffer.append(text)
            continue
        projected = len("\n".join(buffer)) + len(text) + 1
        if buffer and projected > MAX_CHUNK_CHARACTERS:
            flush()
        buffer.append(text)
    flush()
    return chunks


def apply_authoritative_sources(payload: dict[str, Any]) -> dict[str, Any]:
    """Build the runtime seed from every current approved source.

    The packaged seed is retained as a metadata inventory, but chunks are
    rebuilt from the actual approved files. This prevents short bullet/list
    paragraphs from disappearing during an older seed-generation pass.
    """

    if not MANIFEST_PATH.exists():
        return payload
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    client_slug = str(payload["client_slug"])
    approved_dir = DATA_DIR / "clients" / client_slug / "approved"
    superseded = set(manifest.get("superseded_files") or [])
    authoritative = list(manifest.get("authoritative_files") or [])
    packaged_documents = {
        str(item.get("original_filename")): item
        for item in payload.get("documents") or []
        if item.get("original_filename")
    }
    retained_filenames = [
        filename
        for filename in packaged_documents
        if filename not in superseded and filename not in authoritative
    ]
    active_filenames = retained_filenames + authoritative
    documents: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    source_hashes: list[str] = []

    for filename in active_filenames:
        path = approved_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Approved authoritative source is missing: {path}")
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        source_hashes.append(content_hash)
        source_timestamp = datetime.fromtimestamp(
            path.stat().st_mtime, timezone.utc
        ).isoformat()
        document_id = uuid5(NAMESPACE_URL, f"{client_slug}:{filename}:{content_hash}")
        blocks = _approved_source_blocks(path)
        raw_text = "\n\n".join(text for _, text in blocks)
        packaged = packaged_documents.get(filename) or {}
        document_type = str(
            packaged.get("document_type")
            or ("commercial_offer" if filename in authoritative else "approved_document")
        )
        documents.append(
            {
                **packaged,
                "id": str(document_id),
                "title": str(packaged.get("title") or path.stem),
                "client_slug": client_slug,
                "original_filename": filename,
                "source_path": str(path.relative_to(DATA_DIR.parent)),
                "language": str(packaged.get("language") or "en"),
                "document_type": document_type,
                "status": "active",
                "visibility": "client",
                "content_hash": content_hash,
                "raw_text": raw_text,
                "created_at": source_timestamp,
                "updated_at": source_timestamp,
            }
        )
        for item in _chunk_blocks(blocks):
            content = str(item["content"])
            chunk_id = uuid5(
                NAMESPACE_URL,
                f"{document_id}:{item['chunk_index']}:{hashlib.sha256(content.encode()).hexdigest()}",
            )
            chunks.append(
                {
                    "id": str(chunk_id),
                    "document_id": str(document_id),
                    "chunk_index": int(item["chunk_index"]),
                    "content": content,
                    "section_title": str(item["section_title"]),
                    "source_reference": filename,
                    "token_count": None,
                    "chunk_metadata": {
                        "source_type": document_type,
                        "document_type": document_type,
                        "source_filename": filename,
                        "visibility": "client",
                    },
                    "embedding_model": None,
                    "embedding": None,
                    "created_at": source_timestamp,
                    "client_slug": client_slug,
                }
            )

    source_version = hashlib.sha256(
        ":".join([*source_hashes, SOURCE_TRANSFORM_REVISION]).encode()
    ).hexdigest()[:16]
    return {
        **payload,
        "source_version": f"approved-{source_version}",
        "superseded_files": sorted(superseded),
        "documents": documents,
        "chunks": chunks,
    }
