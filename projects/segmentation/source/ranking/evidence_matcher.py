from __future__ import annotations

from typing import Dict, List, Set

from domain.campaign_intent import CampaignIntent
from domain.list_profile import ListProfile
from intent.product_taxonomy import TAXONOMY_BY_FAMILY
from intent.open_vocabulary import relationship_config
from .product_relationship import evaluate_product_relationship


def match_evidence(intent: CampaignIntent, profile: ListProfile) -> Dict[str, object]:
    profile_values: Set[str] = set(profile.product_affinities) | set(profile.interests) | set(profile.professional_subtypes) | set(profile.finance_subtypes) | set(profile.category_facets)
    direct: Set[str] = set()
    adjacent: Set[str] = set()
    support: Set[str] = set()
    supported_families: Set[str] = set()
    matched_atoms: List[Dict[str, object]] = []

    # Known taxonomy metadata is an additive ontology lookup. All families use
    # this same set relationship; there are no family-specific code branches.
    for family in intent.known_product_families or intent.product_families:
        rule = TAXONOMY_BY_FAMILY.get(family)
        if not rule:
            continue
        conflicts = relationship_config().get("evidence_category_conflicts", {})
        direct_hits = {
            value for value in profile_values & {family, *rule.direct_evidence}
            if profile.category_group not in conflicts.get(value, [])
        }
        adjacent_hits = {
            value for value in profile_values & (set(rule.adjacent_evidence) | set(rule.related_interests))
            if profile.category_group not in conflicts.get(value, [])
        }
        if direct_hits:
            direct.update(direct_hits)
            supported_families.add(family)
        if adjacent_hits:
            adjacent.update(adjacent_hits)
            supported_families.add(family)

    support.update(f"profession:{value}" for value in profile.professional_subtypes)
    support.update(f"finance:{value}" for value in profile.finance_subtypes)
    support.update(f"role:{value}" for value in (profile.audience_roles or ([profile.audience_role] if profile.audience_role != "unknown" else [])))
    support.update(f"context:{value}" for value in profile.business_contexts)
    if "online_shopping" in profile.interests:
        support.add("interest:online_shopping")

    matched_names = direct | adjacent
    for atom in profile.evidence:
        if atom.subtype in matched_names:
            matched_atoms.append(atom.to_dict())

    relationship = evaluate_product_relationship(intent, profile)
    if relationship["strength"] == "none" and (direct or adjacent):
        ontology_hits = sorted(direct or adjacent)
        relationship = {
            **relationship,
            "strength": "exact" if direct else "strong",
            "score": 0.85 if direct else 0.65,
            "matched_terms": ontology_hits,
            "evidence": matched_atoms,
            "ontology_enriched": True,
        }
    independent_families = set()
    if direct or adjacent:
        independent_families.add("product")
    if relationship["strength"] != "none":
        independent_families.add("open_product")
    independent_families.update(item.split(":", 1)[0] for item in support)
    return {
        "direct": sorted(direct),
        "adjacent": sorted(adjacent),
        "contextual_product": [],
        "support": sorted(support),
        "independent_families": sorted(independent_families),
        "supported_product_families": sorted(supported_families),
        "matched_atoms": matched_atoms,
        "product_relationship": relationship,
    }
