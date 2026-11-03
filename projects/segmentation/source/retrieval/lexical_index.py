from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from config import BASE_DIR, DATA_DIR, LEXICAL_INDEX_PATH


FTS_COLUMNS = [
    "text", "source_owner", "represented_entity", "audience_role", "product_affinities",
    "professional_subtypes", "finance_subtypes", "category_group", "locations", "evidence",
]


def _join(value: object) -> str:
    return " ".join(str(item) for item in value) if isinstance(value, list) else str(value or "")


def build_lexical_index(documents: Sequence[Dict[str, object]], path: Path = LEXICAL_INDEX_PATH, source_hash: str = "") -> Dict[str, object]:
    started = time.perf_counter()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        resolved = path.resolve()
        if DATA_DIR.resolve() not in resolved.parents:
            raise ValueError(f"Refusing to replace an index outside the project data directory: {resolved}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_dir = BASE_DIR / "backups" / "generated_index_replacements" / stamp
        backup_dir.mkdir(parents=True, exist_ok=False)
        backup_path = backup_dir / path.name
        shutil.copy2(resolved, backup_path)
        log_path = BASE_DIR / "logs" / "generated_replacements.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.now(timezone.utc).isoformat()} BACKUP_BEFORE_DELETE {resolved} -> {backup_path}\n")
        path.unlink()
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE VIRTUAL TABLE documents USING fts5(list_id UNINDEXED, text, source_owner, represented_entity, audience_role, product_affinities, professional_subtypes, finance_subtypes, category_group, locations, evidence, tokenize='unicode61')")
        connection.execute("CREATE TABLE index_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        rows = []
        for document in documents:
            rows.append((
                document["list_id"], document["text"], document["source_owner"], document["represented_entity"],
                document["audience_role"], _join(document["product_affinities"]), _join(document["professional_subtypes"]),
                _join(document["finance_subtypes"]), document["category_group"],
                _join([*document["cities"], *document["areas"]]), _join(document["evidence_snippets"]),
            ))
        connection.executemany("INSERT INTO documents VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        metadata = {"provider": "sqlite_fts5", "source_hash": source_hash, "documents": str(len(rows))}
        connection.executemany("INSERT INTO index_metadata(key,value) VALUES (?,?)", metadata.items())
        connection.commit()
    finally:
        connection.close()
    return {
        "provider": "sqlite_fts5",
        "documents": len(documents),
        "source_hash": source_hash,
        "index_bytes": path.stat().st_size,
        "build_ms": int((time.perf_counter() - started) * 1000),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[\w]+", query.lower(), flags=re.UNICODE)
    tokens = [token for token in tokens if len(token) > 1][:40]
    return " OR ".join(f'"{token}"' for token in tokens)


class LexicalIndex:
    def __init__(self, path: Path = LEXICAL_INDEX_PATH):
        self.path = path

    def search(self, query: str, top_k: int = 300, allowed_ids: set[str] | None = None) -> List[Dict[str, object]]:
        match_query = _fts_query(query)
        if not match_query:
            return []
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT list_id, bm25(documents, 1.0, 2.0, 2.5, 1.2, 2.0, 1.5, 1.5, 1.0, 1.2, 1.5) AS rank FROM documents WHERE documents MATCH ? ORDER BY rank LIMIT ?",
                (match_query, max(top_k * 3, top_k)),
            ).fetchall()
        finally:
            connection.close()
        results = []
        for row in rows:
            list_id = str(row["list_id"])
            if allowed_ids is not None and list_id not in allowed_ids:
                continue
            rank = float(row["rank"])
            results.append({"list_id": list_id, "score": 1.0 / (1.0 + abs(rank))})
            if len(results) >= top_k:
                break
        return results

    def search_exhaustive(self, query: str, allowed_ids: set[str]) -> List[Dict[str, object]]:
        """Score every lexical match before applying the allowed-ID universe."""
        match_query = _fts_query(query)
        if not match_query or not allowed_ids:
            return []
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT list_id, bm25(documents, 1.0, 2.0, 2.5, 1.2, 2.0, 1.5, 1.5, 1.0, 1.2, 1.5) AS rank FROM documents WHERE documents MATCH ? ORDER BY rank",
                (match_query,),
            ).fetchall()
        finally:
            connection.close()
        return [
            {"list_id": str(row["list_id"]), "score": 1.0 / (1.0 + abs(float(row["rank"])))}
            for row in rows
            if str(row["list_id"]) in allowed_ids
        ]

    def exact_phrase(self, phrase: str, top_k: int = 20) -> List[Dict[str, object]]:
        escaped = phrase.replace('"', '""')
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT list_id, bm25(documents) AS rank FROM documents WHERE documents MATCH ? ORDER BY rank LIMIT ?",
                (f'"{escaped}"', top_k),
            ).fetchall()
        finally:
            connection.close()
        return [{"list_id": str(row["list_id"]), "score": 1.0 / (1.0 + abs(float(row["rank"])))} for row in rows]
