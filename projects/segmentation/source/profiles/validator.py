from __future__ import annotations

from typing import Dict, List

from domain.list_profile import ListProfile


def validate_profile(profile: ListProfile) -> List[str]:
    issues: List[str] = []
    if not profile.list_id or not profile.list_name:
        issues.append("missing_identity")
    if profile.age_min is not None and profile.age_max is not None and profile.age_min > profile.age_max:
        issues.append("invalid_age_range")
    if len(profile.cities) > 1 and "All Jordan" in profile.cities:
        issues.append("conflicting_locations")
    if profile.audience_role == "unknown":
        issues.append("unknown_role")
    if not profile.evidence:
        issues.append("no_evidence")
    return issues


def schema_signature(profile: ListProfile) -> Dict[str, str]:
    return {key: type(value).__name__ for key, value in profile.to_dict().items()}

