from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MULTIPLIERS = {
    "": 1,
    "k": 1_000,
    "thousand": 1_000,
    "ألف": 1_000,
    "الف": 1_000,
    "m": 1_000_000,
    "million": 1_000_000,
    "مليون": 1_000_000,
}


def normalize_requested_count(value: Any) -> int:
    """Normalize an already role-classified reach/UI value; never infer its role."""
    if value is None or isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return int(value) if value > 0 and value.is_integer() else 0
    text = str(value).strip().translate(_ARABIC_DIGITS).lower()
    text = text.replace(",", "").replace("٬", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(k|m|thousand|million|ألف|الف|مليون)?", text, re.IGNORECASE)
    if not match:
        return 0
    try:
        quantity = Decimal(match.group(1)) * _MULTIPLIERS[match.group(2) or ""]
    except (InvalidOperation, KeyError):
        return 0
    integral = quantity.to_integral_value()
    return int(integral) if quantity == integral and integral > 0 else 0


@dataclass(frozen=True)
class EffectiveTarget:
    prompt_target_count: int
    ui_target_count: int
    effective_target_count: int
    source: str
    manual_only: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def resolve_effective_target(
    ui_target: Any,
    prompt_target: Any,
    *,
    manual_only: bool = False,
) -> EffectiveTarget:
    """Apply the one canonical UI > prompt > none target precedence."""
    ui_count = normalize_requested_count(ui_target)
    prompt_count = normalize_requested_count(prompt_target)
    if ui_count > 0:
        return EffectiveTarget(prompt_count, ui_count, ui_count, "ui", manual_only)
    if not manual_only and prompt_count > 0:
        return EffectiveTarget(prompt_count, 0, prompt_count, "prompt", manual_only)
    return EffectiveTarget(prompt_count, 0, 0, "none", manual_only)
