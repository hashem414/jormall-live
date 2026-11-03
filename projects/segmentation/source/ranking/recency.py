from __future__ import annotations

from datetime import date


def recency_factor(list_date: str | None, today: date | None = None) -> float:
    if not list_date:
        return 0.15
    today = today or date.today()
    try:
        parsed = date.fromisoformat(list_date)
    except ValueError:
        return 0.15
    age = max(0, today.year - parsed.year - ((today.month, today.day) < (parsed.month, parsed.day)))
    if age <= 2:
        return 1.0
    if age <= 5:
        return 0.8
    if age <= 8:
        return 0.55
    if age <= 11:
        return 0.30
    return 0.15

