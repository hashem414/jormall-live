from __future__ import annotations

import hashlib
import json
import unittest

from app.source_seed_builder import MANIFEST_PATH, apply_authoritative_sources
from app.standalone_db_seed import SEED_PATH


class AuthoritativeSourceTests(unittest.TestCase):
    def test_new_sources_replace_superseded_sources_without_modification(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        original = json.loads(SEED_PATH.read_text(encoding="utf-8"))
        approved_dir = SEED_PATH.parents[1] / "clients" / original["client_slug"] / "approved"
        before = {
            filename: hashlib.sha256((approved_dir / filename).read_bytes()).hexdigest()
            for filename in manifest["authoritative_files"]
        }

        effective = apply_authoritative_sources(original)
        filenames = {item["original_filename"] for item in effective["documents"]}
        after = {
            filename: hashlib.sha256((approved_dir / filename).read_bytes()).hexdigest()
            for filename in manifest["authoritative_files"]
        }

        self.assertEqual(before, after)
        self.assertTrue(set(manifest["authoritative_files"]).issubset(filenames))
        self.assertTrue(set(manifest["superseded_files"]).isdisjoint(filenames))

    def test_effective_knowledge_contains_new_prices_and_no_conflicting_claims(self) -> None:
        effective = apply_authoritative_sources(
            json.loads(SEED_PATH.read_text(encoding="utf-8"))
        )
        authoritative_names = set(
            json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["authoritative_files"]
        )
        authoritative_ids = {
            item["id"] for item in effective["documents"]
            if item["original_filename"] in authoritative_names
        }
        text = "\n".join(
            item["content"] for item in effective["chunks"]
            if item["document_id"] in authoritative_ids
        )
        self.assertIn("JOD 150", text)
        self.assertIn("JOD 200", text)
        for old_claim in ("JOD 100", "JOD 5 plus", "30 pages", "24 to 48"):
            self.assertNotIn(old_claim, text)

    def test_effective_chunks_preserve_sms_lists_and_use_cases(self) -> None:
        effective = apply_authoritative_sources(
            json.loads(SEED_PATH.read_text(encoding="utf-8"))
        )
        sms_document = next(
            item for item in effective["documents"]
            if item["original_filename"] == "JorMall_SMS_Products_List_EN.docx"
        )
        text = "\n".join(
            item["content"] for item in effective["chunks"]
            if item["document_id"] == sms_document["id"]
        )
        for expected in (
            "Client-Based SMS Messaging",
            "Smart Reach SMS to JorMall’s Database Messaging",
            "Premium SMS Messaging",
            "OTP & Financial SMS Messaging",
            "Service SMS Messaging",
            "Interactive SMS Messaging",
            "International SMS Messaging",
            "Marketing campaigns",
            "Customer notifications",
            "Appointment reminders",
            "International event invitations and booking reminders",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, text)
