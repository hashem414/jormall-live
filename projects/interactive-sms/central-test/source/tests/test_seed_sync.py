from __future__ import annotations

import copy
import hashlib
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.core.db_init import initialize_database
from app.models.document import Document, DocumentChunk, KnowledgeSeedState
from app.standalone_db_seed import seed_payload_hash, sync_seed_payload


class SeedSynchronizationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        initialize_database()

    def setUp(self) -> None:
        self.client_slug = f"seed-test-{uuid4().hex[:12]}"
        self.document_id = uuid4()
        self.chunk_ids = [uuid4(), uuid4()]
        self.payload = self._payload()

    def tearDown(self) -> None:
        with SessionLocal() as db:
            db.execute(delete(KnowledgeSeedState).where(KnowledgeSeedState.client_slug == self.client_slug))
            db.execute(delete(Document).where(Document.client_slug == self.client_slug))
            db.commit()

    def _payload(self) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "client_slug": self.client_slug,
            "generated_at": "2026-08-30T00:00:00+00:00",
            "superseded_files": ["retired.docx"],
            "documents": [{
                "id": str(self.document_id), "title": "Managed V1",
                "client_slug": self.client_slug, "original_filename": "managed.docx",
                "source_path": "/seed/managed.docx", "language": "bilingual",
                "document_type": "general", "status": "active", "visibility": "client",
                "content_hash": hashlib.sha256(b"managed-v1").hexdigest(),
                "raw_text": "approved seed content", "created_at": now, "updated_at": now,
            }],
            "chunks": [{
                "id": str(chunk_id), "document_id": str(self.document_id),
                "chunk_index": index, "content": f"approved chunk {index}",
                "chunk_metadata": {}, "embedding_model": "test-embedding",
                "embedding": [1.0 if position == index else 0.0 for position in range(3072)],
                "created_at": now, "client_slug": self.client_slug,
            } for index, chunk_id in enumerate(self.chunk_ids)],
        }

    def test_same_hash_is_noop_and_changed_hash_preserves_runtime_rows(self) -> None:
        with SessionLocal() as db:
            first = sync_seed_payload(self.payload, db)
            self.assertEqual(first["status"], "upserted")
            db.get(Document, self.document_id).title = "Runtime edit"
            runtime_document = Document(
                title="Runtime knowledge", client_slug=self.client_slug,
                original_filename="runtime.docx", source_path="/runtime/runtime.docx",
                language="en", document_type="runtime", status="active", visibility="client",
                content_hash=hashlib.sha256(b"runtime").hexdigest(), raw_text="must survive",
            )
            db.add(runtime_document)
            retired_document = Document(
                title="Retired knowledge", client_slug=self.client_slug,
                original_filename="retired.docx", source_path="/runtime/retired.docx",
                language="en", document_type="runtime", status="active", visibility="client",
                content_hash=hashlib.sha256(b"retired").hexdigest(), raw_text="must be removed",
            )
            db.add(retired_document)
            db.flush()
            retired_id = retired_document.id
            db.add(DocumentChunk(
                document_id=retired_id, chunk_index=0, content="superseded price",
                chunk_metadata={}, client_slug=self.client_slug,
            ))
            db.commit()
            runtime_id = runtime_document.id

        with SessionLocal() as db:
            unchanged = sync_seed_payload(self.payload, db)
            self.assertEqual(unchanged["status"], "unchanged")
            self.assertEqual(unchanged["superseded_documents_removed"], 1)
            self.assertEqual(unchanged["superseded_chunks_removed"], 1)
            self.assertEqual(db.get(Document, self.document_id).title, "Runtime edit")
            self.assertIsNotNone(db.get(Document, runtime_id))
            self.assertIsNone(db.get(Document, retired_id))

        changed = copy.deepcopy(self.payload)
        changed["generated_at"] = "2026-08-31T00:00:00+00:00"
        changed["documents"][0]["title"] = "Managed V2"
        changed["chunks"] = changed["chunks"][:1]
        with SessionLocal() as db:
            updated = sync_seed_payload(changed, db, seed_hash=seed_payload_hash(changed))
            self.assertEqual(updated["status"], "upserted")
            self.assertEqual(updated["stale_chunks_removed"], 1)
            self.assertEqual(db.get(Document, self.document_id).title, "Managed V2")
            self.assertIsNotNone(db.get(Document, runtime_id))
            remaining = db.scalars(
                select(DocumentChunk).where(DocumentChunk.client_slug == self.client_slug)
            ).all()
            self.assertEqual(len(remaining), 1)
