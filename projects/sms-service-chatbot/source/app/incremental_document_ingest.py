from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

from docx import Document as DocxDocument
from openpyxl import load_workbook
from pypdf import PdfReader
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.models.document import ChatConversation, ChatbotLead, Document, DocumentChunk, SalesCallbackRequest
from app.services.client_config_service import client_data_dir
from app.services.embedding_service import create_embeddings


CLIENT_SLUG = "jormall-central-e-commerce-co-ltd"
SUPPORTED_SUFFIXES = {".txt", ".md", ".docx", ".pdf", ".xlsx"}
IGNORED_FILENAMES = {"readme.md"}
DEFAULT_SOURCE_DIR = client_data_dir(CLIENT_SLUG) / "approved" / "uploaded"


@dataclass
class IngestionSummary:
    added_documents: int = 0
    updated_documents: int = 0
    skipped_documents: int = 0
    added_chunks: int = 0
    added_embeddings: int = 0
    errors: list[str] = field(default_factory=list)
    preserved_records: dict[str, int] = field(default_factory=dict)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def clean_text(value: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", value.replace("\r\n", "\n").replace("\r", "\n")).strip()


def extract_docx(path: Path) -> str:
    doc = DocxDocument(path)
    parts = [paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                parts.append(" | ".join(cells))
    return clean_text("\n".join(parts))


def extract_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    parts = []
    for index, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(f"PDF Page {index}\n{text}")
    return clean_text("\n\n".join(parts))


def extract_xlsx(path: Path) -> str:
    workbook = load_workbook(path, read_only=True, data_only=True)
    parts = []
    for sheet in workbook.worksheets:
        parts.append(f"Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            values = [str(value).strip() for value in row if value is not None and str(value).strip()]
            if values:
                parts.append(" | ".join(values))
    workbook.close()
    return clean_text("\n".join(parts))


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return clean_text(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".docx":
        return extract_docx(path)
    if suffix == ".pdf":
        return extract_pdf(path)
    if suffix == ".xlsx":
        return extract_xlsx(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def document_type(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    return f"uploaded_{suffix or 'document'}"


def document_title(path: Path) -> str:
    return re.sub(r"[_-]+", " ", path.stem).strip().title() or path.name


def chunk_text(text: str, *, max_chars: int = 1800, overlap: int = 180) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = paragraph
        while len(current) > max_chars:
            chunks.append(current[:max_chars].strip())
            current = current[max(0, max_chars - overlap):].strip()
    if current:
        chunks.append(current)
    return chunks


def source_path_for(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def preservation_counts(db) -> dict[str, int]:
    return {
        "documents": int(db.scalar(select(func.count()).select_from(Document).where(Document.client_slug == CLIENT_SLUG)) or 0),
        "chunks": int(db.scalar(select(func.count()).select_from(DocumentChunk).where(DocumentChunk.client_slug == CLIENT_SLUG)) or 0),
        "embeddings": int(
            db.scalar(
                select(func.count(DocumentChunk.embedding))
                .select_from(DocumentChunk)
                .where(DocumentChunk.client_slug == CLIENT_SLUG)
            )
            or 0
        ),
        "leads": int(db.scalar(select(func.count()).select_from(ChatbotLead).where(ChatbotLead.client_slug == CLIENT_SLUG)) or 0),
        "callbacks": int(db.scalar(select(func.count()).select_from(SalesCallbackRequest).where(SalesCallbackRequest.client_slug == CLIENT_SLUG)) or 0),
        "conversations": int(db.scalar(select(func.count()).select_from(ChatConversation).where(ChatConversation.client_slug == CLIENT_SLUG)) or 0),
    }


def ingest_file(path: Path, *, dry_run: bool, skip_embeddings: bool, summary: IngestionSummary) -> None:
    content_hash = file_sha256(path)
    text = extract_text(path)
    if not text:
        summary.skipped_documents += 1
        return

    chunks = chunk_text(text)
    if not chunks:
        summary.skipped_documents += 1
        return

    with SessionLocal() as db:
        summary.preserved_records = preservation_counts(db)
        duplicate = db.scalar(
            select(Document).where(
                Document.client_slug == CLIENT_SLUG,
                Document.content_hash == content_hash,
            )
        )
        if duplicate is not None:
            summary.skipped_documents += 1
            db.rollback()
            return

        rel_source_path = source_path_for(path)
        existing = db.scalar(
            select(Document).where(
                Document.client_slug == CLIENT_SLUG,
                Document.original_filename == path.name,
            )
        )
        action = "updated" if existing is not None else "added"

        if dry_run:
            if action == "updated":
                summary.updated_documents += 1
            else:
                summary.added_documents += 1
            summary.added_chunks += len(chunks)
            summary.added_embeddings += 0 if skip_embeddings else len(chunks)
            db.rollback()
            return

        embeddings = []
        embedding_model = None
        if not skip_embeddings:
            batch = create_embeddings(chunks)
            embeddings = batch.embeddings
            embedding_model = batch.model
        else:
            embeddings = [None] * len(chunks)

        if existing is None:
            document = Document(
                id=uuid4(),
                title=document_title(path),
                client_slug=CLIENT_SLUG,
                original_filename=path.name,
                source_path=rel_source_path,
                language="mixed",
                document_type=document_type(path),
                status="active",
                visibility="client",
                content_hash=content_hash,
                raw_text=text,
            )
            db.add(document)
            db.flush()
            summary.added_documents += 1
        else:
            document = existing
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
            document.title = document_title(path)
            document.source_path = rel_source_path
            document.language = "mixed"
            document.document_type = document_type(path)
            document.status = "active"
            document.visibility = "client"
            document.content_hash = content_hash
            document.raw_text = text
            document.updated_at = func.now()
            db.flush()
            summary.updated_documents += 1

        for index, (content, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            db.add(
                DocumentChunk(
                    id=uuid4(),
                    document_id=document.id,
                    chunk_index=index,
                    content=content,
                    section_title=document.title,
                    source_reference=path.name,
                    token_count=None,
                    chunk_metadata={
                        "source_type": document_type(path),
                        "document_type": document_type(path),
                        "original_filename": path.name,
                        "content_hash": content_hash,
                        "chunk_category": "section",
                    },
                    embedding_model=embedding_model,
                    embedding=embedding,
                    client_slug=CLIENT_SLUG,
                )
            )
        summary.added_chunks += len(chunks)
        summary.added_embeddings += sum(1 for value in embeddings if value is not None)
        db.commit()


def source_files(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.iterdir()
        if (
            path.is_file()
            and path.name.lower() not in IGNORED_FILENAMES
            and path.suffix.lower() in SUPPORTED_SUFFIXES
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Incrementally ingest JorMall client documents.")
    parser.add_argument("--source-dir", default=str(DEFAULT_SOURCE_DIR))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-embeddings", action="store_true")
    args = parser.parse_args(argv)

    source_dir = Path(args.source_dir)
    summary = IngestionSummary()

    try:
        if not source_dir.is_dir():
            raise FileNotFoundError(f"Source directory does not exist: {source_dir}")

        files = source_files(source_dir)
        if not files:
            raise FileNotFoundError(f"No supported documents found in: {source_dir}")

        for path in files:
            try:
                ingest_file(
                    path,
                    dry_run=bool(args.dry_run),
                    skip_embeddings=bool(args.skip_embeddings),
                    summary=summary,
                )
            except Exception as error:
                summary.errors.append(f"{path.name}: {type(error).__name__}: {error}")

        if summary.errors:
            print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
            return 1

        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
        return 0
    except Exception as error:
        summary.errors.append(f"{type(error).__name__}: {error}")
        print(json.dumps(asdict(summary), ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    sys.exit(main())
