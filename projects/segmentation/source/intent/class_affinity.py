from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Iterable, Mapping

from config import CLASS_AFFINITY_POLICY_PATH
from domain.campaign_intent import ProductAttributes


@lru_cache(maxsize=1)
def _policy() -> dict[str, object]:
    return json.loads(CLASS_AFFINITY_POLICY_PATH.read_text(encoding="utf-8"))


def canonical_class_order() -> tuple[str, ...]:
    return tuple(str(value) for value in _policy()["canonical_order"])


def canonical_class_name(value: str) -> str:
    compact = " ".join(str(value or "").replace("_", " ").split()).lower()
    if compact in {"allclasses", "all classes"}:
        return str(_policy()["neutral_class"])
    return next((name for name in canonical_class_order() if name.lower() == compact), "")


def _strength_levels() -> dict[str, int]:
    return {str(name): int(level) for name, level in dict(_policy()["strength_levels"]).items()}


def _clean_strength(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in _strength_levels() else "none"


def _raw_mapping(values: Mapping[str, str] | Iterable[str] | object) -> dict[str, str]:
    if hasattr(values, "model_dump"):
        values = values.model_dump(mode="json")
    pairs: list[tuple[str, str]] = []
    if isinstance(values, Mapping):
        pairs = [(str(name), str(strength)) for name, strength in values.items()]
    elif values:
        for item in values:  # type: ignore[union-attr]
            name, separator, strength = str(item).partition(":")
            if separator:
                pairs.append((name, strength))
    levels = _strength_levels()
    result: dict[str, str] = {}
    for raw_name, raw_strength in pairs:
        name = canonical_class_name(raw_name)
        strength = _clean_strength(raw_strength)
        if not name or name == _policy()["neutral_class"]:
            continue
        if levels[strength] > levels.get(result.get(name, "none"), 0):
            result[name] = strength
    return result


@dataclass(frozen=True)
class NormalizedClassPositioning:
    explicit: bool
    broad_market: bool
    primary_class: str
    affinity: dict[str, str]
    source: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_class_positioning(
    affinity: Mapping[str, str] | Iterable[str] | object,
    *,
    primary_class: str = "",
    broad_market: bool = False,
    explicit_classes: Iterable[str] = (),
    source: str = "inferred",
) -> NormalizedClassPositioning:
    order = canonical_class_order()
    raw = _raw_mapping(affinity)
    explicit = [canonical_class_name(value) for value in explicit_classes]
    explicit = list(dict.fromkeys(value for value in explicit if value in order))
    primary = explicit[0] if explicit else canonical_class_name(primary_class)
    if not primary and raw:
        levels = _strength_levels()
        primary = max(order, key=lambda name: (levels.get(raw.get(name, "none"), 0), -order.index(name)))
        if raw.get(primary, "none") == "none":
            primary = ""

    if explicit:
        broad_market = False
        source = "explicit_ui" if source == "explicit_ui" else "explicit_prompt"

    if broad_market and not explicit:
        normalized = {name: raw.get(name, "none") for name in order}
        if primary and normalized[primary] == "none":
            normalized[primary] = "strong"
    elif primary:
        decay = {int(distance): str(strength) for distance, strength in dict(_policy()["focused_distance_affinity"]).items()}
        centers = explicit or [primary]
        normalized = {
            name: decay.get(min(abs(order.index(name) - order.index(center)) for center in centers), "none")
            for name in order
        }
    else:
        normalized = {name: "none" for name in order}
        source = "none"

    return NormalizedClassPositioning(
        explicit=bool(explicit),
        broad_market=bool(broad_market),
        primary_class=primary,
        affinity=normalized,
        source=source,
    )


def infer_class_positioning(attributes: ProductAttributes) -> NormalizedClassPositioning:
    if attributes.campaign_type == "b2b" or attributes.professional_use:
        return normalize_class_positioning({}, source="legacy_inference")
    if attributes.price_band == "premium":
        return normalize_class_positioning({}, primary_class="Upper", source="legacy_inference")
    if attributes.price_band == "mass_market":
        return normalize_class_positioning(
            {
                "Economy": "strong",
                "Economy Plus": "strong",
                "Middle": "strong",
                "Middle Plus": "moderate",
                "Upper": "weak",
            },
            primary_class="Middle",
            broad_market=True,
            source="legacy_inference",
        )
    if attributes.price_band == "middle":
        return normalize_class_positioning({}, primary_class="Middle", source="legacy_inference")
    return normalize_class_positioning({}, source="legacy_inference")


def infer_class_affinity(attributes: ProductAttributes) -> dict[str, str]:
    return infer_class_positioning(attributes).affinity


def affinity_strength(class_affinity: Mapping[str, str] | Iterable[str], economic_class: str) -> str:
    canonical = canonical_class_name(economic_class)
    if canonical == _policy()["neutral_class"]:
        return "neutral"
    return _raw_mapping(class_affinity).get(canonical, "none") if canonical else "none"


def class_distance(first: str, second: str) -> int | None:
    order = canonical_class_order()
    left = canonical_class_name(first)
    right = canonical_class_name(second)
    if left not in order or right not in order:
        return None
    return abs(order.index(left) - order.index(right))
