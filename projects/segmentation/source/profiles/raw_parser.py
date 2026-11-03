from __future__ import annotations

import csv
import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List


def clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\ufeff", "").split())


def stable_list_id(value: str) -> str:
    return "LST_" + hashlib.sha256(clean(value).encode("utf-8")).hexdigest()[:12]


def split_dash_outside_parentheses(value: str) -> List[str]:
    parts: List[str] = []
    buffer: List[str] = []
    depth = 0
    index = 0
    text = clean(value)
    while index < len(text):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        if depth == 0 and text[index:index + 3] == " - ":
            if buffer:
                parts.append(clean("".join(buffer)))
            buffer = []
            index += 3
            continue
        buffer.append(char)
        index += 1
    if buffer:
        parts.append(clean("".join(buffer)))
    return [part for part in parts if part]


def parse_date(value: str) -> str | None:
    matches = list(re.finditer(r"\((\d{1,2}/\d{1,2}/\d{4})\)", value))
    if not matches:
        return None
    try:
        parsed = datetime.strptime(matches[-1].group(1), "%d/%m/%Y").date()
    except ValueError:
        return None
    if parsed.year < 1990 or parsed.year > datetime.now().year + 1:
        return None
    return parsed.isoformat()


def parse_segment_name(list_name: str) -> Dict[str, Any]:
    value = clean(list_name)
    date_matches = list(re.finditer(r"\((\d{1,2}/\d{1,2}/\d{4})\)", value))
    date_match = date_matches[-1] if date_matches else None
    before = clean(value[:date_match.start()].strip(" -")) if date_match else value
    after = clean(value[date_match.end():].strip(" -")) if date_match else value
    before_parts = split_dash_outside_parentheses(before)
    source_owner = before_parts[0] if before_parts else ""
    location_hint = " - ".join(before_parts[1:]) if len(before_parts) > 1 else ""

    gender = ""
    for candidate in ("Mixed", "Female", "Male"):
        if re.search(rf"\b{candidate}\b", after, re.I):
            gender = candidate
            break
    class_match = re.search(r"\b(All\s*Classes|Economy Plus|Middle Plus|Upper|Middle|Economy)\b", after, re.I)
    economic_class = clean(class_match.group(1)).replace(" ", "") if class_match and class_match.group(1).lower().startswith("all") else (clean(class_match.group(1)).title() if class_match else "")
    age_match = re.search(r"\((\d{1,3})\s*-\s*(\d{1,3})\)", after)
    age_min = age_max = None
    if age_match:
        age_min, age_max = sorted((int(age_match.group(1)), int(age_match.group(2))))
        if age_min < 10 or age_max > 100:
            age_min = age_max = None

    original_category = ""
    if age_match:
        original_category = clean(after[age_match.end():].lstrip(" -"))
    if not original_category:
        parts = split_dash_outside_parentheses(after)
        metadata = {"mixed", "female", "male", "upper", "middle", "economy", "middle plus", "economy plus", "allclasses", "all classes"}
        remaining = [part for part in parts if part.lower() not in metadata]
        original_category = remaining[-1] if remaining else "General"

    return {
        "list_id": stable_list_id(value),
        "list_name": value,
        "source_owner": source_owner,
        "location_hint": location_hint,
        "gender": gender,
        "economic_class": economic_class,
        "age_min": age_min,
        "age_max": age_max,
        "original_category": original_category,
        "list_date": parse_date(value),
    }


def read_raw_catalogue(path: Path) -> Iterable[Dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        for source_row, values in enumerate(reader, start=1):
            values = (values + ["", "", "", ""])[:4]
            if source_row == 1 and clean(values[0]).lower() == "check":
                continue
            if not clean(values[1]):
                continue
            try:
                quantity = int(float(clean(values[2]).replace(",", "") or 0))
            except ValueError:
                quantity = 0
            try:
                needed_quantity = int(float(clean(values[3]).replace(",", "") or 0))
            except ValueError:
                needed_quantity = 0
            yield {
                "source_row": source_row,
                "checked": clean(values[0]).lower() in {"true", "1", "yes", "y"},
                "quantity": quantity,
                "needed_quantity": needed_quantity,
                "original_row_text": "\t".join(clean(value) for value in values),
                **parse_segment_name(values[1]),
            }
