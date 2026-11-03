from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

from domain.campaign_intent import ExplicitFilters
from profiles.location_parser import normalize_area_values, normalize_city_area_values


INACTIVE_VALUES = {"", "any", "na", "none", "null"}


def normalize_filter_values(value: object) -> List[str]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    cleaned = [" ".join(str(item or "").split()) for item in values]
    return list(dict.fromkeys(item for item in cleaned if item.lower() not in INACTIVE_VALUES))


def _payload_bool(payload: Mapping[str, object], key: str, default: bool = False) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "on"}


def _payload_int(payload: Mapping[str, object], key: str, default: int = 0) -> int:
    try:
        return int(str(payload.get(key, default)).replace(",", ""))
    except (TypeError, ValueError):
        return default


def _normalize_geography(cities: Iterable[object], areas: Iterable[object]) -> Tuple[List[str], List[str]]:
    normalized_cities, city_areas = normalize_city_area_values(cities)
    normalized_areas = normalize_area_values(areas)
    return normalized_cities, list(dict.fromkeys([*city_areas, *normalized_areas]))


def normalize_explicit_filters(filters: ExplicitFilters) -> ExplicitFilters:
    cities, areas = _normalize_geography(filters.cities, filters.areas)
    return ExplicitFilters(
        cities=cities,
        areas=areas,
        gender=normalize_filter_values(filters.gender),
        classes=normalize_filter_values(filters.classes),
        categories=normalize_filter_values(filters.categories),
        age_min=filters.age_min,
        age_max=filters.age_max,
    )


@dataclass(frozen=True)
class EffectiveFilters:
    categories: List[str] = field(default_factory=list)
    genders: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    cities: List[str] = field(default_factory=list)
    areas: List[str] = field(default_factory=list)
    minimum_list_count: int = 0
    age_min: Optional[int] = None
    age_max: Optional[int] = None
    provenance: Dict[str, str] = field(default_factory=dict)
    manual_only: bool = False

    def to_explicit_filters(self) -> ExplicitFilters:
        return ExplicitFilters(
            cities=list(self.cities),
            areas=list(self.areas),
            gender=list(self.genders),
            classes=list(self.classes),
            categories=list(self.categories),
            age_min=self.age_min,
            age_max=self.age_max,
        )

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class FilterResolution:
    prompt: ExplicitFilters
    ui: ExplicitFilters
    effective: EffectiveFilters

    def diagnostics(self) -> Dict[str, object]:
        return {
            "prompt": asdict(self.prompt),
            "ui": asdict(self.ui),
            "effective": self.effective.to_dict(),
            "provenance": dict(self.effective.provenance),
        }


def _choose(
    prompt_values: List[str],
    ui_values: List[str],
    *,
    manual_only: bool,
) -> Tuple[List[str], str]:
    if ui_values:
        return list(ui_values), "ui"
    if not manual_only and prompt_values:
        return list(prompt_values), "prompt"
    return [], "none"


def resolve_effective_filters(
    prompt_filters: ExplicitFilters,
    ui_filters: Mapping[str, object],
    manual_only: bool = False,
) -> FilterResolution:
    prompt = normalize_explicit_filters(prompt_filters)
    ui_cities, ui_areas = _normalize_geography(
        normalize_filter_values(ui_filters.get("city", [])),
        normalize_filter_values(ui_filters.get("area", [])),
    )
    age_active = _payload_bool(ui_filters, "age_filter_active", False)
    ui_age_min = (_payload_int(ui_filters, "age_min", 0) or None) if age_active else None
    ui_age_max = (_payload_int(ui_filters, "age_max", 0) or None) if age_active else None
    ui = ExplicitFilters(
        cities=ui_cities,
        areas=ui_areas,
        gender=normalize_filter_values(ui_filters.get("gender", [])),
        classes=normalize_filter_values(ui_filters.get("class", [])),
        categories=normalize_filter_values(ui_filters.get("category", [])),
        age_min=ui_age_min,
        age_max=ui_age_max,
    )

    categories, category_source = _choose(prompt.categories, ui.categories, manual_only=manual_only)
    genders, gender_source = _choose(prompt.gender, ui.gender, manual_only=manual_only)
    classes, class_source = _choose(prompt.classes, ui.classes, manual_only=manual_only)
    cities, city_source = _choose(prompt.cities, ui.cities, manual_only=manual_only)
    areas, area_source = _choose(prompt.areas, ui.areas, manual_only=manual_only)
    if age_active:
        age_min, age_max, age_source = ui.age_min, ui.age_max, "ui"
    elif not manual_only and (prompt.age_min is not None or prompt.age_max is not None):
        age_min, age_max, age_source = prompt.age_min, prompt.age_max, "prompt"
    else:
        age_min, age_max, age_source = None, None, "none"

    minimum = max(0, _payload_int(ui_filters, "min_quantity", 0))
    provenance = {
        "category": category_source,
        "gender": gender_source,
        "class": class_source,
        "city": city_source,
        "area": area_source,
        "age": age_source,
        "minimum_list_count": "ui" if minimum else "none",
    }
    effective = EffectiveFilters(
        categories=categories,
        genders=genders,
        classes=classes,
        cities=cities,
        areas=areas,
        minimum_list_count=minimum,
        age_min=age_min,
        age_max=age_max,
        provenance=provenance,
        manual_only=manual_only,
    )
    return FilterResolution(prompt=prompt, ui=ui, effective=effective)
