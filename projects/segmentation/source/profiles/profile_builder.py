from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from dataclasses import fields
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from config import CLASSIFICATION_VERSION, PROFILES_CSV_PATH, PROFILES_JSONL_PATH, RAW_CATALOGUE_PATH
from domain.evidence import EvidenceAtom
from domain.list_profile import ListProfile
from .audience_roles import classify_audience_roles
from .entity_parser import parse_entities
from .exclusions import exclusion_reasons
from .finance_subtypes import classify_finance_subtypes
from .interests import category_facets, classify_category_group, classify_profile_facets, row_evidence_fields
from .location_parser import parse_location
from .professional_subtypes import classify_professional_subtypes
from .raw_parser import read_raw_catalogue
from .validator import schema_signature, validate_profile


def _evidence(family: str, subtype: str, source_field: str, source_text: str, confidence: float, rule_id: str) -> EvidenceAtom:
    return EvidenceAtom(family=family, subtype=subtype, source_field=source_field, source_text=source_text[:500], confidence=confidence, rule_id=rule_id)


def build_profile(row: Dict[str, object]) -> ListProfile:
    entities = parse_entities(
        str(row["source_owner"]),
        str(row["list_name"]),
        str(row["location_hint"]),
        str(row["original_category"]),
    )
    location = parse_location(str(row["location_hint"]))
    evidence_fields = row_evidence_fields(
        str(row["list_name"]),
        str(entities["source_owner"]),
        str(row["original_category"]),
        str(entities["represented_entity"]),
    )
    role_values, role_confidence, role_matches = classify_audience_roles(evidence_fields)
    role = role_values[0] if role_values else "unknown"
    facet_matches = classify_profile_facets(evidence_fields)
    interests = sorted({str(match["concept"]) for match in facet_matches})
    products = sorted({str(match["concept"]) for match in facet_matches if match.get("product_affinity")})
    professions = classify_professional_subtypes(evidence_fields)
    finance = classify_finance_subtypes(evidence_fields)
    exclusions = exclusion_reasons(row)
    atoms: List[EvidenceAtom] = []
    for match in role_matches:
        atoms.append(_evidence("audience_role", str(match["role"]), str(match["source_field"]), str(evidence_fields.get(str(match["source_field"]), "")), float(match["confidence"]), str(match["rule_id"])))
    for match in facet_matches:
        atoms.append(_evidence("interest", str(match["concept"]), str(match["source_field"]), str(match["source_text"]), float(match["confidence"]), str(match["rule_id"])))
        if match.get("product_affinity"):
            atoms.append(_evidence("product_affinity", str(match["concept"]), str(match["source_field"]), str(match["source_text"]), float(match["confidence"]), str(match["rule_id"])))
    atoms.extend(_evidence("profession", name, "list_name+original_category", " ".join(evidence_fields.values()), 0.9, rule_id) for name, rule_id in professions)
    atoms.extend(_evidence("finance", name, "list_name+original_category", " ".join(evidence_fields.values()), 0.9, rule_id) for name, rule_id in finance)
    for reason in exclusions:
        atoms.append(_evidence("exclusion", reason, "list_name+source_fields", " ".join(evidence_fields.values()), 1.0, f"exclusion.{reason}"))
    source_industry = str(row["original_category"])
    category_group = classify_category_group(facet_matches)
    contexts = []
    if set(role_values) & {"companies", "owners", "decision_makers", "procurement", "professionals", "business_contacts"}:
        contexts.append("b2b")
    if set(role_values) & {"customers_or_prospects", "parents", "patients", "subscribers", "retail_shoppers", "students", "graduates"}:
        contexts.append("consumer_or_individual")
    return ListProfile(
        list_id=str(row["list_id"]),
        list_name=str(row["list_name"]),
        source_owner=entities["source_owner"],
        represented_entity=entities["represented_entity"],
        represented_entity_confidence=float(entities["represented_entity_confidence"]),
        represented_entity_evidence=list(entities["represented_entity_evidence"]),
        source_industry=source_industry,
        category_group=category_group,
        category_facets=category_facets(facet_matches),
        business_contexts=contexts,
        original_category=str(row["original_category"]),
        original_row_text=str(row.get("original_row_text", row["list_name"])),
        audience_role=role,
        audience_role_confidence=role_confidence,
        audience_roles=role_values,
        audience_role_evidence=role_matches,
        interests=interests,
        product_affinities=products,
        professional_subtypes=sorted({name for name, _ in professions}),
        finance_subtypes=sorted({name for name, _ in finance}),
        gender=str(row["gender"]),
        economic_class=str(row["economic_class"]),
        age_min=row["age_min"],
        age_max=row["age_max"],
        cities=list(location["cities"]),
        governorates=list(location["governorates"]),
        areas=list(location["areas"]),
        coverage_type=str(location["coverage_type"]),
        country=str(location["country"]),
        location_source=str(location["source"]),
        location_confidence=float(location["confidence"]),
        location_evidence=str(location["evidence"]),
        quantity=int(row["quantity"]),
        list_date=row["list_date"],
        eligible=not exclusions,
        exclusion_reasons=exclusions,
        evidence=atoms,
        classification_version=CLASSIFICATION_VERSION,
    )


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_profiles(profiles: List[ListProfile], jsonl_path: Path, csv_path: Path) -> None:
    jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    with jsonl_path.open("w", encoding="utf-8", newline="\n") as handle:
        for profile in profiles:
            handle.write(json.dumps(profile.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    columns = [field.name for field in fields(ListProfile)]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for profile in profiles:
            row = profile.to_dict()
            for key, value in row.items():
                if isinstance(value, (list, dict)):
                    row[key] = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            writer.writerow(row)


def build_profiles(raw_path: Path = RAW_CATALOGUE_PATH, jsonl_path: Path = PROFILES_JSONL_PATH, csv_path: Path = PROFILES_CSV_PATH) -> Dict[str, object]:
    started = time.perf_counter()
    raw_rows = list(read_raw_catalogue(raw_path))
    unique_rows: Dict[str, Dict[str, object]] = {}
    duplicate_rows = 0
    for row in raw_rows:
        list_id = str(row["list_id"])
        if list_id in unique_rows:
            duplicate_rows += 1
            continue
        unique_rows[list_id] = row
    profiles = sorted((build_profile(row) for row in unique_rows.values()), key=lambda item: item.list_id)
    _write_profiles(profiles, jsonl_path, csv_path)
    issues = Counter(issue for profile in profiles for issue in validate_profile(profile))
    roles = Counter(profile.audience_role for profile in profiles)
    categories = Counter(profile.category_group for profile in profiles)
    exclusions = Counter(reason for profile in profiles for reason in profile.exclusion_reasons)
    eligible = [profile for profile in profiles if profile.eligible]
    report = {
        "raw_rows": len(raw_rows),
        "parsed_profiles": len(profiles),
        "duplicate_raw_rows_suppressed": duplicate_rows,
        "eligible_rows": len(eligible),
        "excluded_rows": len(profiles) - len(eligible),
        "role_distribution": dict(sorted(roles.items())),
        "category_distribution": dict(sorted(categories.items())),
        "interest_coverage": sum(bool(profile.interests) for profile in profiles) / max(1, len(profiles)),
        "product_affinity_coverage": sum(bool(profile.product_affinities) for profile in profiles) / max(1, len(profiles)),
        "professional_subtype_coverage": sum(bool(profile.professional_subtypes) for profile in profiles) / max(1, len(profiles)),
        "finance_subtype_coverage": sum(bool(profile.finance_subtypes) for profile in profiles) / max(1, len(profiles)),
        "rows_with_no_evidence": issues.get("no_evidence", 0),
        "rows_with_conflicting_locations": issues.get("conflicting_locations", 0),
        "rows_with_unknown_roles": issues.get("unknown_role", 0),
        "high_confidence_roles": sum(profile.audience_role != "unknown" and profile.audience_role_confidence >= 0.9 for profile in profiles),
        "medium_confidence_roles": sum(profile.audience_role != "unknown" and 0.7 <= profile.audience_role_confidence < 0.9 for profile in profiles),
        "low_confidence_roles": sum(profile.audience_role != "unknown" and profile.audience_role_confidence < 0.7 for profile in profiles),
        "represented_entity_rows": sum(bool(profile.represented_entity) for profile in profiles),
        "category_facet_coverage": sum(bool(profile.category_facets) for profile in profiles) / max(1, len(profiles)),
        "exclusion_reason_distribution": dict(sorted(exclusions.items())),
        "schema": schema_signature(profiles[0]) if profiles else {},
        "jsonl_sha256": _hash(jsonl_path),
        "csv_sha256": _hash(csv_path),
        "build_ms": int((time.perf_counter() - started) * 1000),
    }
    return report


def load_profiles(path: Path = PROFILES_JSONL_PATH) -> List[ListProfile]:
    with path.open("r", encoding="utf-8") as handle:
        return [ListProfile.from_dict(json.loads(line)) for line in handle if line.strip()]
