from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from config import DOCUMENTS_JSONL_PATH
from domain.list_profile import ListProfile


def build_document(profile: ListProfile) -> Dict[str, object]:
    evidence_snippets = [
        f"{atom.family} {atom.subtype} {atom.source_text}"
        for atom in profile.evidence
        if atom.family != "exclusion"
    ]
    fields = {
        "original_row_text": profile.original_row_text,
        "represented_entity": profile.represented_entity,
        "list_name": profile.list_name,
        "source_owner": profile.source_owner,
        "source_industry": profile.source_industry,
        "category_group": profile.category_group,
        "category_facets": profile.category_facets,
        "business_contexts": profile.business_contexts,
        "audience_role": profile.audience_role,
        "audience_roles": profile.audience_roles,
        "interests": profile.interests,
        "product_affinities": profile.product_affinities,
        "professional_subtypes": profile.professional_subtypes,
        "finance_subtypes": profile.finance_subtypes,
        "cities": profile.cities,
        "governorates": profile.governorates,
        "areas": profile.areas,
        "evidence_snippets": evidence_snippets,
    }
    def line(label: str, value: object) -> str:
        values = value if isinstance(value, list) else [value]
        rendered = "; ".join(str(item) for item in values if item)
        return f"{label}: {rendered}" if rendered else ""

    text = "\n".join(filter(None, [
        line("Original list", profile.list_name),
        line("Raw catalogue row", profile.original_row_text),
        line("Source company", profile.source_owner),
        line("Represented entity", profile.represented_entity),
        line("Original category", profile.original_category),
        line("Derived category group", profile.category_group),
        line("Source industry", profile.source_industry),
        line("Audience roles", profile.audience_roles or [profile.audience_role]),
        line("Business and consumer contexts", profile.business_contexts),
        line("Interests", profile.interests),
        line("Product affinities", profile.product_affinities),
        line("Professional clues", profile.professional_subtypes),
        line("Finance clues", profile.finance_subtypes),
        line("Category facets", profile.category_facets),
        line("Cities", profile.cities),
        line("Governorates", profile.governorates),
        line("Areas", profile.areas),
        line("Evidence", evidence_snippets),
    ]))
    document_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"list_id": profile.list_id, "document_hash": document_hash, "text": text, **fields}


def build_documents(profiles: List[ListProfile], output_path: Path = DOCUMENTS_JSONL_PATH) -> Dict[str, object]:
    documents = [build_document(profile) for profile in profiles if profile.eligible]
    documents.sort(key=lambda item: str(item["list_id"]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="\n") as handle:
        for document in documents:
            handle.write(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return {"documents": len(documents), "sha256": digest, "path": str(output_path)}


def load_documents(path: Path = DOCUMENTS_JSONL_PATH) -> List[Dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]
