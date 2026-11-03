from __future__ import annotations

import re
from collections import Counter
from typing import List, Tuple

from domain.list_profile import ListProfile
from domain.recommendation_candidate import RecommendationCandidate


def _normalize_name(value: str) -> str:
    value = re.sub(r"\(\d{1,2}/\d{1,2}/\d{4}\)", " ", value)
    value = re.sub(r"\b(mixed|male|female|upper|middle plus|middle|economy plus|economy|all ?classes)\b", " ", value, flags=re.I)
    value = re.sub(r"\(\d{1,3}\s*-\s*\d{1,3}\)", " ", value)
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def diversity_signature(profile: ListProfile, candidate: RecommendationCandidate) -> str:
    return "|".join([
        profile.source_owner.lower(),
        profile.represented_entity.lower(),
        _normalize_name(profile.list_name),
        profile.audience_role,
        candidate.tier,
        ",".join(sorted(candidate.evidence_families)),
        ",".join(sorted(profile.cities + profile.areas)),
    ])


def apply_diversity(rows: List[Tuple[ListProfile, RecommendationCandidate]]) -> List[Tuple[ListProfile, RecommendationCandidate]]:
    seen: Counter[str] = Counter()
    seen_core: Counter[str] = Counter()
    for profile, candidate in rows:
        signature = diversity_signature(profile, candidate)
        candidate.diversity_signature = signature
        occurrence = seen[signature]
        if occurrence:
            candidate.score -= min(30.0, 8.0 * occurrence)
        seen[signature] += 1
        core_signature = "|".join([
            profile.source_owner.lower(),
            profile.represented_entity.lower(),
            profile.audience_role,
            candidate.tier,
            ",".join(sorted(candidate.evidence_families)),
        ])
        core_occurrence = seen_core[core_signature]
        if core_occurrence:
            candidate.score -= min(18.0, 2.5 * core_occurrence)
        seen_core[core_signature] += 1
    return sorted(rows, key=lambda item: (-item[1].score, item[0].list_id))
