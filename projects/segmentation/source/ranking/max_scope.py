from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from domain.list_profile import ListProfile
from domain.recommendation_candidate import RecommendationCandidate


SCOPE_TIERS: Dict[str, Tuple[str, ...]] = {
    "direct_only": ("direct",),
    "direct_adjacent": ("direct", "adjacent"),
    "direct_adjacent_contextual": ("direct", "adjacent", "contextual"),
    "allow_fallback": ("direct", "adjacent", "contextual", "fallback"),
}


def normalize_scope(value: str) -> str:
    aliases = {"direct": "direct_only", "fallback": "allow_fallback"}
    normalized = aliases.get(str(value or "").strip().lower(), str(value or "").strip().lower())
    return normalized if normalized in SCOPE_TIERS else "direct_adjacent_contextual"


def scope_rows(rows: Sequence[Tuple[ListProfile, RecommendationCandidate]], scope: str) -> List[Tuple[ListProfile, RecommendationCandidate]]:
    allowed = SCOPE_TIERS[normalize_scope(scope)]
    return [row for row in rows if row[1].tier in allowed]


@dataclass(frozen=True)
class TargetSelectionResult:
    rows: List[Tuple[ListProfile, RecommendationCandidate]]
    gross_selected_quantity: int
    reached: bool | None
    overshoot: int
    shortage: int
    status: str
    selection_mode: str
    list_limit_applied: bool


def select_ranked_for_target(
    rows: Sequence[Tuple[ListProfile, RecommendationCandidate]],
    *,
    target_count: int,
    max_lists: int,
    max_mode: bool,
) -> TargetSelectionResult:
    """Select a ranked prefix; target and list count never influence relevance."""
    target = max(0, int(target_count))
    list_limit = max(0, int(max_lists))
    selected: List[Tuple[ListProfile, RecommendationCandidate]] = []
    gross_quantity = 0
    for row in rows:
        if not max_mode and len(selected) >= list_limit:
            break
        selected.append(row)
        gross_quantity += max(0, int(row[0].quantity))
        if target > 0 and gross_quantity >= target:
            break

    if target <= 0:
        reached = None
        overshoot = 0
        shortage = 0
        status = "none"
        selection_mode = "all_qualified" if max_mode else "maximum_lists"
    elif gross_quantity >= target:
        reached = True
        overshoot = gross_quantity - target
        shortage = 0
        status = "reached"
        selection_mode = "ranked_until_target"
    else:
        reached = False
        overshoot = 0
        shortage = target - gross_quantity
        status = "short"
        selection_mode = "ranked_until_target" if max_mode else "ranked_until_target_or_list_cap"
    return TargetSelectionResult(
        rows=selected,
        gross_selected_quantity=gross_quantity,
        reached=reached,
        overshoot=overshoot,
        shortage=shortage,
        status=status,
        selection_mode=selection_mode,
        list_limit_applied=not max_mode,
    )


def apply_max(rows: Sequence[Tuple[ListProfile, RecommendationCandidate]], max_lists: int, max_mode: bool) -> List[Tuple[ListProfile, RecommendationCandidate]]:
    return select_ranked_for_target(
        rows,
        target_count=0,
        max_lists=max_lists,
        max_mode=max_mode,
    ).rows
