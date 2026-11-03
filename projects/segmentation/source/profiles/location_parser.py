from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Dict, Iterable, List, Sequence, Tuple

from config import GEOGRAPHY_PATH
from intent.text_normalization import normalize_text
from profiles.raw_parser import split_dash_outside_parentheses


@lru_cache(maxsize=1)
def geography_config() -> Dict[str, object]:
    return json.loads(GEOGRAPHY_PATH.read_text(encoding="utf-8"))


def _unique(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(value for value in values if value))


@lru_cache(maxsize=1)
def _geography_index() -> Dict[str, object]:
    config = geography_config()
    return {
        "national": {normalize_text(str(value)) for value in config["national_aliases"]},
        "directions": {
            normalize_text(str(alias)): str(direction["name"])
            for direction in config["amman_directions"]
            for alias in direction["aliases"]
        },
        "areas": {
            normalize_text(str(area)): str(area)
            for area in config["amman_areas"]
        },
        "cities": {
            normalize_text(str(alias)): str(item["name"])
            for item in config["governorates"]
            for alias in item["aliases"]
        },
    }


def _marker_variants(normalized: str) -> List[str]:
    variants = [normalized]
    for marker in ("city", "governorate", "branch", "coverage", "area"):
        prefix = f"{marker} "
        suffix = f" {marker}"
        if normalized.startswith(prefix):
            variants.append(normalized[len(prefix):].strip())
        if normalized.endswith(suffix):
            variants.append(normalized[:-len(suffix)].strip())
    return _unique(variants)


def _segment_geography(segment: str) -> Dict[str, object] | None:
    normalized = normalize_text(segment)
    if not normalized:
        return None
    index = _geography_index()
    variants = _marker_variants(normalized)

    if any(value in index["national"] for value in variants):
        return {"kind": "national", "cities": [], "areas": [], "evidence": segment}

    if re.fullmatch(r"(?:amman\s+)?(?:west/east|east/west)(?:\s+amman)?", normalized):
        return {"kind": "area", "cities": ["Amman"], "areas": ["West", "East"], "evidence": segment}

    for value in variants:
        if value in index["directions"]:
            return {
                "kind": "area",
                "cities": ["Amman"],
                "areas": [str(index["directions"][value])],
                "evidence": segment,
            }

    for value in variants:
        if value in index["areas"]:
            return {"kind": "area", "cities": ["Amman"], "areas": [str(index["areas"][value])], "evidence": segment}

    for value in variants:
        if value in index["cities"]:
            return {"kind": "city", "cities": [str(index["cities"][value])], "areas": [], "evidence": segment}
    return None


def _terminal_geography(segments: Sequence[str]) -> Tuple[List[Dict[str, object]], str, float]:
    if not segments:
        return [], "none", 0.0

    matches: List[Dict[str, object]] = []
    for index in range(len(segments) - 1, -1, -1):
        match = _segment_geography(segments[index])
        if match is None:
            if matches:
                break
            continue
        if matches and any(item["kind"] == "area" for item in matches):
            match_cities = list(match.get("cities", []))
            if match["kind"] == "city" and match_cities != ["Amman"]:
                break
        matches.append(match)
        if match["kind"] == "national":
            break

    if not matches:
        return [], "none", 0.0
    terminal = _segment_geography(segments[-1]) is not None
    return matches, "terminal_segment" if terminal else "structured_segment", 0.99 if terminal else 0.90


def parse_location(location_hint: str) -> Dict[str, object]:
    raw = " ".join(str(location_hint or "").split())
    segments = split_dash_outside_parentheses(raw) or ([raw] if raw else [])
    matches, source, confidence = _terminal_geography(segments)
    if not matches:
        return {
            "country": "Jordan",
            "cities": [],
            "governorates": [],
            "areas": [],
            "coverage_type": "unknown",
            "source": "none",
            "confidence": 0.0,
            "evidence": "",
        }

    if any(match["kind"] == "national" for match in matches):
        evidence = " | ".join(str(match["evidence"]) for match in reversed(matches))
        return {
            "country": "Jordan",
            "cities": [],
            "governorates": ["All Jordan"],
            "areas": [],
            "coverage_type": "all_jordan",
            "source": source,
            "confidence": confidence,
            "evidence": evidence,
        }

    areas = _unique(
        str(area)
        for match in reversed(matches)
        for area in match.get("areas", [])
    )
    cities = _unique(
        str(city)
        for match in reversed(matches)
        for city in match.get("cities", [])
    )
    if areas:
        cities = ["Amman"]
    evidence = " | ".join(str(match["evidence"]) for match in reversed(matches))
    return {
        "country": "Jordan",
        "cities": cities,
        "governorates": list(cities),
        "areas": areas,
        "coverage_type": "specific" if cities else "unknown",
        "source": source,
        "confidence": confidence if cities else 0.0,
        "evidence": evidence,
    }


def normalize_city_area_values(values: Iterable[object]) -> Tuple[List[str], List[str]]:
    cities: List[str] = []
    areas: List[str] = []
    for value in values:
        raw = " ".join(str(value or "").split())
        if not raw or raw.lower() in {"any", "na", "none", "null"}:
            continue
        location = parse_location(raw)
        if location["coverage_type"] == "all_jordan":
            cities.append("All Jordan")
            continue
        cities.extend(str(item) for item in location["cities"])
        areas.extend(str(item) for item in location["areas"])
        if not location["cities"]:
            cities.append(raw)
    return _unique(cities), _unique(areas)


def normalize_area_values(values: Iterable[object]) -> List[str]:
    normalized: List[str] = []
    for value in values:
        raw = " ".join(str(value or "").split())
        if not raw or raw.lower() in {"any", "na", "none", "null"}:
            continue
        location = parse_location(raw)
        if location["areas"]:
            normalized.extend(str(item) for item in location["areas"])
        else:
            normalized.append(raw)
    return _unique(normalized)


def explicit_geography_terms(cities: Iterable[str], areas: Iterable[str]) -> List[str]:
    config = geography_config()
    requested_cities = {str(value) for value in cities}
    requested_areas = {str(value) for value in areas}
    terms: List[str] = []
    if "All Jordan" in requested_cities:
        terms.extend(str(value) for value in config["national_aliases"])
    for item in config["governorates"]:
        if str(item["name"]) in requested_cities:
            terms.extend(str(value) for value in item["aliases"])
    for direction in config["amman_directions"]:
        if str(direction["name"]) in requested_areas:
            terms.extend(str(value) for value in direction["aliases"])
    for area in config["amman_areas"]:
        if str(area) in requested_areas:
            terms.append(str(area))
    terms.extend(requested_cities)
    terms.extend(requested_areas)
    return sorted(_unique(terms), key=len, reverse=True)
