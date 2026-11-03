from __future__ import annotations

from typing import Dict, List, Tuple

from config import STRICT_EXPLICIT_GEOGRAPHY
from domain.campaign_intent import CampaignIntent
from domain.list_profile import ListProfile


BLOCKED_ROLES = {"employees", "invalid_or_avoid", "enquiry_or_operational"}


def static_profile_eligibility(profile: ListProfile) -> Tuple[bool, List[str]]:
    failures = list(profile.exclusion_reasons)
    if not profile.eligible:
        failures.append("static_profile_ineligible")
    if profile.audience_role in BLOCKED_ROLES:
        failures.append(f"blocked_role:{profile.audience_role}")
    return not failures, list(dict.fromkeys(failures))


def geography_filter_match(filters: object, profile: ListProfile) -> Tuple[bool, Dict[str, bool], List[str]]:
    matches: Dict[str, bool] = {}
    failures: List[str] = []
    requested_cities = {str(value) for value in getattr(filters, "cities", []) if value}
    requested_areas = {str(value).lower() for value in getattr(filters, "areas", []) if value}
    specific_cities = requested_cities - {"All Jordan"}

    profile_cities = set(profile.cities)
    profile_areas = {str(value).lower() for value in profile.areas}
    if "Amman - West/East" in profile_cities:
        profile_cities.add("Amman")
        profile_areas.update({"west", "east"})

    if specific_cities:
        specifically_locatable = bool(profile_cities) and profile.coverage_type not in {
            "unknown", "national", "all_jordan"
        }
        city_match = bool(specific_cities & profile_cities)
        if STRICT_EXPLICIT_GEOGRAPHY:
            city_match = city_match and specifically_locatable
        matches["cities"] = city_match
        if not city_match:
            failures.append("city_filter_mismatch")

    if requested_areas:
        area_match = bool(requested_areas & profile_areas)
        matches["areas"] = area_match
        if not area_match:
            failures.append("area_filter_mismatch")
    return not failures, matches, failures


def explicit_filter_match(intent: CampaignIntent, profile: ListProfile) -> Tuple[bool, Dict[str, object], List[str]]:
    filters = intent.explicit_filters
    geography_ok, matches, failures = geography_filter_match(filters, profile)
    if filters.gender:
        gender_match = profile.gender == "Mixed" or profile.gender in filters.gender
        matches["gender"] = gender_match
        if not gender_match:
            failures.append("gender_filter_mismatch")
    if filters.classes:
        class_match = profile.economic_class == "AllClasses" or profile.economic_class in filters.classes
        matches["classes"] = class_match
        if not class_match:
            failures.append("class_filter_mismatch")
    if filters.categories:
        category_match = profile.category_group in filters.categories
        matches["categories"] = category_match
        if not category_match:
            failures.append("category_filter_mismatch")
    if filters.age_min is not None or filters.age_max is not None:
        age_match = (
            profile.age_min is not None
            and profile.age_max is not None
            and (filters.age_min is None or profile.age_max >= filters.age_min)
            and (filters.age_max is None or profile.age_min <= filters.age_max)
        )
        matches["age"] = age_match
        if not age_match:
            failures.append("age_filter_mismatch")
    return geography_ok and not failures, matches, failures


def hard_eligibility(intent: CampaignIntent, profile: ListProfile) -> Tuple[bool, Dict[str, object], List[str]]:
    static_ok, failures = static_profile_eligibility(profile)
    filter_ok, filter_matches, filter_failures = explicit_filter_match(intent, profile)
    failures.extend(filter_failures)
    return static_ok and not failures and filter_ok, filter_matches, list(dict.fromkeys(failures))
