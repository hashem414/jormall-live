from __future__ import annotations

from typing import Dict

from domain.list_profile import ListProfile


DIRECT_ROLES = {
    "customers_or_prospects", "companies", "owners", "decision_makers", "procurement",
    "professionals", "students", "graduates", "parents", "members", "investors",
    "patients", "subscribers", "retail_shoppers", "business_contacts",
}


def assign_tier(profile: ListProfile, evidence: Dict[str, object]) -> str:
    direct = list(evidence["direct"])
    adjacent = list(evidence["adjacent"])
    support = list(evidence["support"])
    independent = set(evidence["independent_families"])
    relationship_strength = dict(evidence.get("product_relationship", {})).get("strength", "none")
    role_is_compatible = profile.audience_role in DIRECT_ROLES

    if (direct or relationship_strength == "exact") and role_is_compatible:
        return "direct"
    if direct or adjacent or relationship_strength == "strong":
        return "adjacent"
    if relationship_strength == "weak" and support and len(independent) >= 2:
        return "contextual"
    if relationship_strength == "weak":
        return "fallback"
    return "rejected"
