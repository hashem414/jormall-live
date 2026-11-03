from __future__ import annotations

from functools import lru_cache
from typing import Dict, List, Set, Tuple

from domain.campaign_intent import CampaignIntent
from domain.list_profile import ListProfile
from intent.open_vocabulary import relationship_config
from intent.text_normalization import normalize_text, tokenize


def _profile_fields(profile: ListProfile) -> Dict[str, str]:
    return {
        "original_row_text": profile.original_row_text,
        "list_name": profile.list_name,
        "source_owner": profile.source_owner,
        "represented_entity": profile.represented_entity,
        "source_industry": profile.source_industry,
        "category_group": profile.category_group,
        "category_facets": " ".join(profile.category_facets),
        "business_contexts": " ".join(profile.business_contexts),
        "original_category": profile.original_category,
        "interests": " ".join(profile.interests),
        "product_affinities": " ".join(profile.product_affinities),
        "professional_subtypes": " ".join(profile.professional_subtypes),
        "finance_subtypes": " ".join(profile.finance_subtypes),
        "evidence": " ".join(atom.source_text for atom in profile.evidence),
    }


@lru_cache(maxsize=20000)
def _profile_blob(items: Tuple[Tuple[str, str], ...]) -> Tuple[str, frozenset[str], frozenset[str]]:
    combined = normalize_text(" ".join(value for _name, value in items))
    literal = normalize_text(" ".join(value for name, value in items if name not in {"category_group", "category_facets", "business_contexts"}))
    return combined, frozenset(tokenize(combined)), frozenset(tokenize(literal))


@lru_cache(maxsize=20000)
def _evidence_fields(items: Tuple[Tuple[str, str], ...]) -> Tuple[Tuple[str, str, frozenset[str]], ...]:
    return tuple((name, normalized, frozenset(tokenize(normalized))) for name, value in items for normalized in [normalize_text(value)])


@lru_cache(maxsize=256)
def _groups_for_request(request_text: str) -> Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...]], ...]:
    request_tokens = set(tokenize(request_text))
    groups = []
    for group in relationship_config().get("concept_groups", []):
        seeds = [normalize_text(str(term)) for term in group.get("seed_terms", [])]
        if any((seed in request_text if " " in seed else seed in request_tokens) for seed in seeds if seed):
            groups.append((
                str(group["id"]),
                tuple(normalize_text(str(term)) for term in group.get("evidence_terms", [])),
                tuple(str(category) for category in group.get("categories", [])),
            ))
    return tuple(groups)


def _present(phrase: str, normalized_text: str, tokens: Set[str]) -> bool:
    normalized = normalize_text(phrase)
    if not normalized:
        return False
    return normalized in normalized_text if " " in normalized else normalized in tokens


def evaluate_product_relationship(intent: CampaignIntent, profile: ListProfile) -> Dict[str, object]:
    fields = _profile_fields(profile)
    profile_text, cached_tokens, literal_tokens = _profile_blob(tuple(fields.items()))
    profile_tokens = set(cached_tokens)
    requested_phrases = [*intent.raw_product_phrases, *intent.open_product_terms]
    generic_terms = {normalize_text(str(term)) for term in relationship_config().get("generic_relationship_terms", [])}
    requested_tokens = {
        token for value in requested_phrases for token in tokenize(value)
        if token not in generic_terms and len(token) >= 3
    }

    negated_hits = [term for term in intent.negated_terms if _present(term, profile_text, profile_tokens)]
    exact_hits = sorted(term for term in requested_tokens if term in profile_tokens)
    if negated_hits and not exact_hits:
        return {"strength": "none", "score": 0.0, "concept_groups": [], "matched_terms": [], "evidence_fields": [], "category_support": [], "negated_hits": negated_hits, "semantic_score": 0.0, "evidence": []}

    matched_groups: List[str] = []
    group_evidence: Set[str] = set()
    category_support: Set[str] = set()
    request_text = normalize_text(" ".join(requested_phrases))
    for group_id, evidence_terms, categories in _groups_for_request(request_text):
        matched_groups.append(group_id)
        for term in evidence_terms:
            if _present(term, profile_text, profile_tokens):
                group_evidence.add(term)
        if profile.category_group in categories:
            category_support.add(profile.category_group)

    # Literal overlap is direct only when it comes from row-level content, not a
    # generic category label. Configured concept bridges establish adjacency.
    literal_hit = any(term in literal_tokens for term in exact_hits)
    if literal_hit and exact_hits:
        strength = "exact"
        score = min(1.0, 0.72 + 0.08 * len(exact_hits))
    elif matched_groups and group_evidence and (category_support or len(group_evidence) >= 2):
        strength = "strong"
        score = min(0.79, 0.48 + 0.05 * len(group_evidence) + (0.05 if category_support else 0.0))
    elif exact_hits or (matched_groups and category_support):
        strength = "weak"
        score = min(0.49, 0.25 + 0.04 * len(exact_hits) + 0.05 * len(category_support))
    else:
        strength = "none"
        score = 0.0
    evidence = []
    literal_fields = []
    if strength != "none":
        for field_name, field_text, cached_field_tokens in _evidence_fields(tuple(fields.items())):
            source_text = fields[field_name]
            field_tokens = set(cached_field_tokens)
            matched = sorted(term for term in set(exact_hits) | group_evidence if _present(term, field_text, field_tokens))
            if matched:
                literal_fields.append(field_name)
                evidence.append({"source_field": field_name, "source_text": source_text[:500], "matched_terms": matched})
    return {
        "strength": strength,
        "score": round(score, 4),
        "concept_groups": sorted(matched_groups),
        "matched_terms": sorted(set(exact_hits) | group_evidence),
        "evidence_fields": literal_fields,
        "category_support": sorted(category_support),
        "negated_hits": negated_hits,
        "semantic_score": 0.0,
        "evidence": evidence,
    }
