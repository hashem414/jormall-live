from __future__ import annotations

import re

from domain.campaign_intent import ExplicitFilters


def parse_explicit_filters(prompt: str) -> ExplicitFilters:
    text = prompt.lower()
    cities = []
    for canonical, pattern in [
        ("Amman - West", r"amman west|west amman"),
        ("Amman - East", r"amman east|east amman"),
        ("Irbid", r"\birbid\b"),
        ("Zarqa", r"\bzarqa\b"),
        ("Aqaba", r"\baqaba\b"),
        ("All Jordan", r"all (?:over )?jordan"),
    ]:
        if re.search(pattern, text):
            cities.append(canonical)
    gender = [name for name in ("Female", "Male", "Mixed") if re.search(rf"\b{name.lower()}\b", text)]
    classes = [name for name in ("Upper", "Middle Plus", "Middle", "Economy Plus", "Economy") if name.lower() in text]
    age_min = age_max = None
    age_range = re.search(r"\bage\s*(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\b", text)
    if age_range:
        age_min, age_max = sorted((int(age_range.group(1)), int(age_range.group(2))))
    else:
        age_plus = re.search(r"\bage\s*(\d{1,2})\s*\+", text)
        if age_plus:
            age_min = int(age_plus.group(1))
    return ExplicitFilters(cities=cities, gender=gender, classes=classes, age_min=age_min, age_max=age_max)

