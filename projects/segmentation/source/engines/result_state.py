from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Set, Tuple

from domain.list_profile import ListProfile
from domain.recommendation_candidate import RecommendationCandidate
from ranking.max_scope import TargetSelectionResult, select_ranked_for_target


RankedRow = Tuple[ListProfile, RecommendationCandidate]


@dataclass(frozen=True)
class DerivedResultState:
    active_rows: List[RankedRow]
    selected_rows: List[RankedRow]
    excluded_rows: List[RankedRow]
    selected_ids: Set[str]
    excluded_ids: Set[str]
    active_ids: Set[str]
    revision: int
    target_selection: TargetSelectionResult
    summary: Dict[str, object]
    category_groups: List[Dict[str, object]]
    class_distribution: List[Dict[str, object]]
    tier_distribution: List[Dict[str, object]]


def _distribution(rows: Sequence[RankedRow], value: str) -> List[Dict[str, object]]:
    if value == "class":
        labels = [profile.economic_class or "Unknown" for profile, _candidate in rows]
    else:
        labels = [candidate.tier or "unknown" for _profile, candidate in rows]
    counts = Counter(labels)
    return [{"label": label, "value": count} for label, count in counts.most_common()]


def _category_groups(rows: Sequence[RankedRow]) -> List[Dict[str, object]]:
    counts = Counter(profile.category_group for profile, _candidate in rows)
    return [
        {
            "group": category,
            "recommended_lists": count,
            "recommended_quantity": sum(
                max(0, int(profile.quantity))
                for profile, _candidate in rows
                if profile.category_group == category
            ),
        }
        for category, count in counts.most_common()
    ]


def derive_result_state(
    ranked_qualified_candidates: Sequence[RankedRow],
    *,
    excluded_ids: Iterable[str] = (),
    selected_ids: Iterable[str] | None = None,
    previous_active_ids: Iterable[str] = (),
    previous_excluded_ids: Iterable[str] = (),
    target_count: int,
    max_lists: int,
    max_mode: bool,
    revision: int,
    auto_select_replacements: bool = True,
) -> DerivedResultState:
    pool_ids = {profile.list_id for profile, _candidate in ranked_qualified_candidates}
    excluded = {str(value) for value in excluded_ids if str(value) in pool_ids}
    available = [row for row in ranked_qualified_candidates if row[0].list_id not in excluded]
    target_selection = select_ranked_for_target(
        available,
        target_count=target_count,
        max_lists=max_lists,
        max_mode=max_mode,
    )
    active_rows = list(target_selection.rows)
    active = {profile.list_id for profile, _candidate in active_rows}
    previous_active = {str(value) for value in previous_active_ids}
    previous_excluded = {str(value) for value in previous_excluded_ids}

    selection_memory = set(active) if selected_ids is None else {
        str(value) for value in selected_ids if str(value) in pool_ids
    }
    newly_excluded = excluded - previous_excluded
    if auto_select_replacements and newly_excluded & selection_memory:
        selection_memory.update(active - previous_active)

    selected_rows = [row for row in active_rows if row[0].list_id in selection_memory]
    excluded_rows = [row for row in ranked_qualified_candidates if row[0].list_id in excluded]
    active_quantity = sum(max(0, int(profile.quantity)) for profile, _candidate in active_rows)
    selected_quantity = sum(max(0, int(profile.quantity)) for profile, _candidate in selected_rows)
    excluded_quantity = sum(max(0, int(profile.quantity)) for profile, _candidate in excluded_rows)
    target = max(0, int(target_count))
    summary = {
        "active_recommendation_list_count": len(active_rows),
        "active_recommended_quantity": active_quantity,
        "selected_list_count": len(selected_rows),
        "selected_quantity": selected_quantity,
        "excluded_list_count": len(excluded_rows),
        "excluded_quantity": excluded_quantity,
        "target_count": target,
        "target_reached": target_selection.reached,
        "target_met": target_selection.reached,
        "target_overshoot": target_selection.overshoot,
        "target_shortage": target_selection.shortage,
        "target_difference": active_quantity - target if target else 0,
        "available_recommendable_lists": len(available),
    }
    return DerivedResultState(
        active_rows=active_rows,
        selected_rows=selected_rows,
        excluded_rows=excluded_rows,
        selected_ids=selection_memory,
        excluded_ids=excluded,
        active_ids=active,
        revision=max(0, int(revision)),
        target_selection=target_selection,
        summary=summary,
        category_groups=_category_groups(active_rows),
        class_distribution=_distribution(active_rows, "class"),
        tier_distribution=_distribution(active_rows, "tier"),
    )
